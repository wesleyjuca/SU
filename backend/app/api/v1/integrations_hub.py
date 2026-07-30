"""Hub de integrações — conectar/desconectar provedores externos por escritório.

Ver e status: qualquer colaborador. Conectar/desconectar: ADMIN (credenciais
valem para o escritório inteiro). Webhooks: router público separado (os
provedores chamam sem JWT).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.config import settings
from app.db.base import get_db
from app.dependencies import get_current_user, require_role
from app.models.user import User
from app.services import integration_hub

log = structlog.get_logger()

router = APIRouter(prefix="/integrations/hub", tags=["integrations-hub"])
webhooks_router = APIRouter(prefix="/integrations/webhooks", tags=["integrations-webhooks"])


def _frontend_base_url() -> str:
    """URL absoluta do frontend — o backend/frontend vivem em domínios
    separados, então um redirect relativo (ver google_integration.py) cai no
    domínio errado. Mesmo fallback de payment_gateway.py::_base_url()."""
    if settings.PUBLIC_BASE_URL:
        return settings.PUBLIC_BASE_URL.rstrip("/")
    if settings.CORS_ORIGINS:
        return settings.CORS_ORIGINS[0].rstrip("/")
    return "http://localhost:3000"


@router.get("")
async def hub_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Todos os provedores do hub com o estado de conexão do escritório."""
    return {"integracoes": await integration_hub.list_status(db, current_user.tenant_id)}


class ConnectBody(BaseModel):
    credentials: dict[str, str]


@router.post("/{provider}/connect")
async def hub_connect(
    provider: str,
    body: ConnectBody,
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Salva as credenciais do provedor (cifradas) e marca como conectada."""
    integ = await integration_hub.save_credentials(
        db, current_user.tenant_id, provider, body.credentials, connected_by=current_user.id,
    )
    meta = integration_hub.PROVIDERS[provider]
    return {
        "message": f"{meta['nome']} conectada. Os recursos desta integração "
                   "são ativados na fase correspondente do roadmap.",
        "provider": provider,
        "status": integ.status,
    }


@router.post("/{provider}/test")
async def hub_test(
    provider: str,
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Testa a credencial conectada e atualiza o status (CONECTADA/ERRO).
    Disponível para as fontes credenciadas (PJe/PDPJ, Escavador, Judit)."""
    r = await integration_hub.testar_conexao(db, current_user.tenant_id, provider)
    await db.commit()
    return r


@router.delete("/{provider}")
async def hub_disconnect(
    provider: str,
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    removed = await integration_hub.disconnect(db, current_user.tenant_id, provider)
    return {"message": "Integração desconectada." if removed else "Integração já estava desconectada."}


# ─── OAuth "Conectar conta" — Fase 117 (Stripe Connect, Mercado Pago) ─────────
@router.get("/{provider}/oauth/connect")
async def hub_oauth_connect(
    provider: str,
    current_user: User = Depends(require_role("ADMIN")),
):
    """Gera a URL de login delegado ("conectar sua conta") do provedor —
    alternativa em 1 clique ao form de colar chave, quando disponível."""
    meta = integration_hub.PROVIDERS.get(provider)
    if not meta or not meta.get("oauth_disponivel"):
        raise HTTPException(status_code=422, detail="Login por conta não disponível para este provedor.")
    if not integration_hub.is_oauth_configured(provider):
        raise HTTPException(
            status_code=422,
            detail=f"Login por conta do {meta['nome']} não configurado no servidor. "
                   "Use \"Colar chave manualmente\" ou peça ao administrador da plataforma "
                   "para cadastrar as credenciais OAuth.",
        )
    state = integration_hub.sign_oauth_state(str(current_user.id), provider)
    return {"auth_url": integration_hub.build_oauth_url(provider, state)}


@router.get("/{provider}/oauth/callback")
async def hub_oauth_callback(
    provider: str,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Retorno do provedor: troca o code por tokens e salva cifrado."""
    base = _frontend_base_url()
    if provider not in integration_hub.OAUTH_PROVIDERS:
        return RedirectResponse(url=f"{base}/integracoes?hub_oauth={provider}_erro")
    try:
        user_id = uuid.UUID(integration_hub.verify_oauth_state(state, provider))
    except (HTTPException, ValueError):
        return RedirectResponse(url=f"{base}/integracoes?hub_oauth={provider}_erro")

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or not user.tenant_id:
        return RedirectResponse(url=f"{base}/integracoes?hub_oauth={provider}_erro")

    try:
        tokens = await integration_hub.exchange_oauth_code(provider, code)
        await integration_hub.save_oauth_tokens(db, user.tenant_id, provider, tokens, connected_by=user.id)
        await db.commit()
    except Exception as exc:
        log.warning("hub_oauth_callback_erro", provider=provider, error=str(exc))
        return RedirectResponse(url=f"{base}/integracoes?hub_oauth={provider}_erro")

    return RedirectResponse(url=f"{base}/integracoes?hub_oauth={provider}_ok")


# ─── Receiver público de webhooks ─────────────────────────────────────────────
@webhooks_router.post("/{provider}")
async def receive_webhook(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Recebe callbacks dos provedores (sem auth — eles não têm JWT nosso).

    Segurança: o payload é tratado como DICA. Para pagamento (stripe/
    mercadopago), a confirmação real é feita consultando a API do provedor
    com as credenciais do escritório — nunca se marca uma fatura como PAGA
    só porque o POST chegou. Sempre responde 200 (evita re-tentativas)."""
    if provider not in integration_hub.PROVIDERS:
        return {"received": False, "error": "provedor desconhecido"}
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    log.info(
        "webhook_received",
        provider=provider,
        event=payload.get("type") or payload.get("event") or payload.get("action"),
        keys=sorted(payload.keys())[:10] if isinstance(payload, dict) else None,
    )
    if provider in ("stripe", "mercadopago"):
        from app.services.payment_gateway import processar_webhook_pagamento
        result = await processar_webhook_pagamento(
            db, provider, payload if isinstance(payload, dict) else {}, dict(request.query_params),
        )
        log.info("webhook_pagamento", provider=provider, **result)
        return {"received": True, **result}
    if provider == "clicksign":
        from app.services.esign import processar_webhook_assinatura
        try:
            result = await processar_webhook_assinatura(db, payload if isinstance(payload, dict) else {})
        except Exception as exc:
            log.warning("webhook_assinatura_erro", error=str(exc))
            result = {"processed": False, "reason": "erro interno"}
        log.info("webhook_assinatura", **result)
        return {"received": True, **result}
    return {"received": True}
