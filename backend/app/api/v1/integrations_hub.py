"""Hub de integrações — conectar/desconectar provedores externos por escritório.

Ver e status: qualquer colaborador. Conectar/desconectar: ADMIN (credenciais
valem para o escritório inteiro). Webhooks: router público separado (os
provedores chamam sem JWT).
"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.base import get_db
from app.dependencies import get_current_user, require_role
from app.models.user import User
from app.services import integration_hub

log = structlog.get_logger()

router = APIRouter(prefix="/integrations/hub", tags=["integrations-hub"])
webhooks_router = APIRouter(prefix="/integrations/webhooks", tags=["integrations-webhooks"])


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


@router.delete("/{provider}")
async def hub_disconnect(
    provider: str,
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    removed = await integration_hub.disconnect(db, current_user.tenant_id, provider)
    return {"message": "Integração desconectada." if removed else "Integração já estava desconectada."}


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
    return {"received": True}
