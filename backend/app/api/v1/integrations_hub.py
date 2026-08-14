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


# ─── Pasta de doutrina do Google Drive — Fase 138.2 ───────────────────────────
class DriveFolderBody(BaseModel):
    folder: str


@router.put("/google_drive_doutrina/folder")
async def hub_set_drive_folder(
    body: DriveFolderBody,
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Configura a pasta do Drive a sincronizar — só depois de conectado
    (a URL/ID nunca é segredo, fica em `extra_data`, não em `credentials_enc`)."""
    from app.integrations.google_drive.client import extrair_folder_id

    integ = await integration_hub.get_integration(db, current_user.tenant_id, "google_drive_doutrina")
    if not integ or not integ.credentials_enc:
        raise HTTPException(status_code=422, detail="Conecte a conta Google antes de configurar a pasta.")

    folder_id = extrair_folder_id(body.folder)
    if not folder_id:
        raise HTTPException(
            status_code=422,
            detail="Não foi possível identificar o ID da pasta — cole a URL completa da pasta do Drive ou o ID.",
        )
    integ.extra_data = {**(integ.extra_data or {}), "folder_id": folder_id}
    await db.commit()
    return {"folder_id": folder_id, "message": "Pasta configurada — a sincronização roda automaticamente todo dia."}


# ─── OAuth "Conectar conta" — Fase 117 (Stripe Connect, Mercado Pago) ─────────
async def _modulo_habilitado(db: AsyncSession, tenant_id, chave: str) -> bool:
    """Opt-in por escritório (mesmo padrão de google_integration.py::_google_enabled)."""
    from app.models.tenant import TenantConfig
    if not tenant_id:
        return False
    cfg = (await db.execute(
        select(TenantConfig).where(TenantConfig.tenant_id == tenant_id)
    )).scalar_one_or_none()
    return bool(cfg and (cfg.modules_enabled or {}).get(chave, False))


@router.get("/{provider}/oauth/connect")
async def hub_oauth_connect(
    provider: str,
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Gera a URL de login delegado ("conectar sua conta") do provedor —
    alternativa em 1 clique ao form de colar chave, quando disponível."""
    meta = integration_hub.PROVIDERS.get(provider)
    if not meta or not meta.get("oauth_disponivel"):
        raise HTTPException(status_code=422, detail="Login por conta não disponível para este provedor.")
    if provider in ("google_drive_doutrina", "google_workspace") and not await _modulo_habilitado(db, current_user.tenant_id, provider):
        raise HTTPException(
            status_code=422,
            detail=f"A integração {meta['nome']} está desabilitada para este escritório. "
                   "Habilite em Configurações > Módulos antes de conectar.",
        )
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
        integ = await integration_hub.save_oauth_tokens(db, user.tenant_id, provider, tokens, connected_by=user.id)
        if provider == "google_workspace":
            # Guarda o e-mail conectado só pra exibição (GET /integrations/google/status)
            # — nunca é usado pra autenticação, não é segredo.
            from app.services.google_workspace import fetch_user_email
            email = await fetch_user_email(tokens["access_token"])
            if email:
                integ.extra_data = {**(integ.extra_data or {}), "google_email": email}
        await db.commit()
    except Exception as exc:
        log.warning("hub_oauth_callback_erro", provider=provider, error=str(exc))
        return RedirectResponse(url=f"{base}/integracoes?hub_oauth={provider}_erro")

    return RedirectResponse(url=f"{base}/integracoes?hub_oauth={provider}_ok")


# ─── Login direto do PDPJ (Keycloak, grant_type=password) — Fase 177.1 ───────
class PdpjLoginBody(BaseModel):
    username: str
    password: str


@router.post("/pdpj/oauth/login")
async def hub_pdpj_oauth_login(
    body: PdpjLoginBody,
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Login direto com usuário/senha do CNJ Corporativo — troca por um
    access_token/refresh_token via Keycloak (grant_type=password) e salva
    cifrado, igual ao form manual. A senha em si nunca é persistida: só
    passa pela requisição, é usada 1x nesta troca e descartada."""
    if not integration_hub.is_oauth_configured("pdpj"):
        raise HTTPException(
            status_code=422,
            detail="Login com CNJ Corporativo ainda não configurado nesta plataforma. "
                   "Use \"Colar token manualmente\" ou peça ao administrador da plataforma "
                   "para cadastrar client_id/client_secret do PDPJ (obtidos com o CNJ).",
        )
    import httpx as _httpx
    try:
        tokens = await integration_hub.exchange_oauth_password("pdpj", body.username, body.password)
    except _httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 401, 403):
            raise HTTPException(status_code=422, detail="Usuário ou senha do CNJ Corporativo inválidos.")
        raise HTTPException(status_code=502, detail="CNJ/PDPJ indisponível no momento. Tente novamente em instantes.")
    except _httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Não foi possível contatar o serviço de login do CNJ. Tente novamente.")

    await integration_hub.save_oauth_tokens(db, current_user.tenant_id, "pdpj", tokens, connected_by=current_user.id)
    await db.commit()
    return {"message": "PDPJ conectado via CNJ Corporativo.", "provider": "pdpj", "status": "CONECTADA"}


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
