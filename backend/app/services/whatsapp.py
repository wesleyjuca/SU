"""Notificações por WhatsApp — Meta Cloud API (credenciais do hub).

Mensagens iniciadas pelo negócio exigem TEMPLATE aprovado na conta Meta do
escritório: crie um template chamado `afj_notificacao` (idioma pt_BR) com um
único parâmetro no corpo ({{1}}). Se o envio por template falhar, tentamos
texto simples — que só entrega dentro da janela de 24h de atendimento.

Tudo aqui é best-effort e gracioso: sem integração conectada, sem telefone
ou com erro do provedor, apenas loga e retorna False (nunca quebra o fluxo
de notificação principal — sino/email/push continuam).
"""
import re

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import integration_hub

log = structlog.get_logger()

_TIMEOUT = 15
_GRAPH = "https://graph.facebook.com/v23.0"
TEMPLATE_NAME = "afj_notificacao"


def normalizar_telefone(telefone: str | None) -> str | None:
    """Só dígitos; prefixa 55 (Brasil) quando vier sem código do país."""
    if not telefone:
        return None
    digitos = re.sub(r"\D", "", telefone)
    if not digitos:
        return None
    if len(digitos) in (10, 11):  # DDD + número, sem país
        digitos = "55" + digitos
    return digitos if 12 <= len(digitos) <= 15 else None


async def testar_credenciais(access_token: str | None, phone_number_id: str | None) -> tuple[bool, str]:
    """Sonda leve pra validar access_token+phone_number_id (distingue
    401/403 de sucesso) — usada pelo botão "Testar conexão" do hub (Fase
    168). Não envia mensagem nenhuma, só confirma que o número responde
    com esse token."""
    if not access_token or not phone_number_id:
        return (False, "credenciais incompletas")
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{_GRAPH}/{phone_number_id}",
                params={"fields": "verified_name"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except Exception as exc:
        return (False, str(exc)[:120])
    if resp.status_code == 200:
        return (True, "ok")
    if resp.status_code in (401, 403):
        return (False, "token inválido ou expirado")
    return (False, f"HTTP {resp.status_code}: {resp.text[:200]}")


async def enviar_whatsapp(db: AsyncSession, tenant_id, telefone: str | None, texto: str) -> bool:
    """Envia `texto` via template afj_notificacao (fallback: texto simples)."""
    numero = normalizar_telefone(telefone)
    if not numero or not tenant_id:
        return False
    creds = await integration_hub.get_credentials(db, tenant_id, "whatsapp")
    if not creds:
        return False

    url = f"{_GRAPH}/{creds['phone_number_id']}/messages"
    headers = {"Authorization": f"Bearer {creds['access_token']}"}
    template_payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "template",
        "template": {
            "name": TEMPLATE_NAME,
            "language": {"code": "pt_BR"},
            "components": [{"type": "body", "parameters": [{"type": "text", "text": texto[:900]}]}],
        },
    }
    text_payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {"body": texto[:3000]},
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=template_payload, headers=headers)
            if resp.status_code < 400:
                log.info("whatsapp_enviado", via="template", to=numero[-4:])
                await integration_hub.registrar_uso(db, tenant_id, "whatsapp", sucesso=True)
                return True
            # Template ausente/não aprovado → tenta texto (janela de 24h)
            log.warning("whatsapp_template_falhou", status=resp.status_code, body=resp.text[:200])
            resp = await client.post(url, json=text_payload, headers=headers)
            if resp.status_code < 400:
                log.info("whatsapp_enviado", via="texto", to=numero[-4:])
                await integration_hub.registrar_uso(db, tenant_id, "whatsapp", sucesso=True)
                return True
            log.warning("whatsapp_texto_falhou", status=resp.status_code, body=resp.text[:200])
            await integration_hub.registrar_uso(db, tenant_id, "whatsapp", sucesso=False, detalhe=f"HTTP {resp.status_code}: {resp.text[:300]}")
    except Exception as exc:
        log.warning("whatsapp_unreachable", error=str(exc))
        await integration_hub.registrar_uso(db, tenant_id, "whatsapp", sucesso=False, detalhe=str(exc)[:400])
    return False
