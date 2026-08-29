"""Fase 248.1 — verificação de assinatura HMAC dos webhooks de pagamento.

Camada ADICIONAL sobre a re-verificação real já existente em
`payment_gateway.py` (que sempre confirma via GET autenticado na API do
provedor antes de marcar qualquer fatura como paga) — nunca a substitui.
O objetivo aqui é só filtrar, o mais cedo possível, um payload que nem
sequer veio do provedor de verdade, antes de gastar uma chamada de rede
na re-verificação.

Segredo por PLATAFORMA, não por tenant: a URL do webhook é única
(`/integrations/webhooks/{provider}`) e recebe eventos de todos os
escritórios conectados — mesmo modelo do Stripe Connect/Mercado Pago
marketplace, onde o segredo de assinatura é configurado uma vez no
dashboard da plataforma para aquele endpoint.

Verificação sempre opcional: se o segredo correspondente não estiver
configurado (`settings.STRIPE_WEBHOOK_SECRET`/`MERCADOPAGO_WEBHOOK_SECRET`
vazio), pula silenciosamente — mesmo padrão de opcionalidade já usado por
`integration_hub.is_oauth_configured`. Sem isso, o deploy quebraria o
webhook de todo tenant já conectado no instante em que o código sobe,
antes de alguém configurar o segredo na plataforma.
"""
import hashlib
import hmac
import time

import structlog

log = structlog.get_logger()

# Tolerância de replay — mesma janela que o próprio Stripe recomenda na
# doc oficial (5 minutos) pro parâmetro `t=` do header `Stripe-Signature`.
_TOLERANCIA_SEGUNDOS = 300


def verify_stripe_signature(payload: bytes, sig_header: str | None, secret: str) -> bool:
    """Verifica `Stripe-Signature: t=<ts>,v1=<hash>[,v0=...]`.

    Payload assinado é `"{timestamp}.{corpo_bruto}"`, HMAC-SHA256 com o
    webhook signing secret. Formato documentado e estável (Stripe)."""
    if not sig_header:
        return False
    partes: dict[str, list[str]] = {}
    for item in sig_header.split(","):
        if "=" not in item:
            continue
        chave, _, valor = item.partition("=")
        partes.setdefault(chave.strip(), []).append(valor.strip())
    timestamps = partes.get("t")
    assinaturas_v1 = partes.get("v1")
    if not timestamps or not assinaturas_v1:
        return False
    try:
        timestamp = int(timestamps[0])
    except ValueError:
        return False
    if abs(time.time() - timestamp) > _TOLERANCIA_SEGUNDOS:
        return False
    payload_assinado = f"{timestamp}.".encode() + payload
    esperado = hmac.new(secret.encode(), payload_assinado, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(esperado, v1) for v1 in assinaturas_v1)


def verify_mercadopago_signature(
    request_id: str | None, data_id: str | None, sig_header: str | None, secret: str,
) -> bool:
    """Verifica `x-signature: ts=<ts>,v1=<hash>` do Mercado Pago.

    Manifest assinado (formato documentado pelo MP para webhooks):
    `"id:{data_id};request-id:{request_id};ts:{ts};"`, HMAC-SHA256 com o
    secret configurado na aplicação MP. Nota de confiança: o formato exato
    já mudou de versão no passado do lado do MP — se a verificação
    rejeitar webhooks legítimos após configurar o secret, confirmar o
    formato atual na doc do Mercado Pago antes de mexer na
    re-verificação real (que continua protegendo o sistema
    independentemente disso)."""
    if not sig_header or not data_id:
        return False
    partes: dict[str, str] = {}
    for item in sig_header.split(","):
        if "=" not in item:
            continue
        chave, _, valor = item.partition("=")
        partes[chave.strip()] = valor.strip()
    timestamp = partes.get("ts")
    assinatura_v1 = partes.get("v1")
    if not timestamp or not assinatura_v1:
        return False
    manifest = f"id:{data_id};"
    if request_id:
        manifest += f"request-id:{request_id};"
    manifest += f"ts:{timestamp};"
    esperado = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, assinatura_v1)
