"""Pagamento online de faturas — Stripe / Mercado Pago (credenciais do hub).

Gera link de pagamento para uma fatura EMITIDA e confirma o pagamento via
webhook. Segurança do webhook: o payload do provedor é tratado como DICA —
a confirmação real é feita buscando o pagamento NA API do provedor com as
credenciais do escritório (nunca se marca PAGA só porque o POST chegou).
"""
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.financial import BillingInvoice, FinancialEntry
from app.services import integration_hub

log = structlog.get_logger()

_TIMEOUT = 20


def _base_url() -> str:
    if settings.PUBLIC_BASE_URL:
        return settings.PUBLIC_BASE_URL.rstrip("/")
    if settings.CORS_ORIGINS:
        return settings.CORS_ORIGINS[0].rstrip("/")
    return "http://localhost:3000"


# ─── Geração do link ──────────────────────────────────────────────────────────
async def criar_link_pagamento(db: AsyncSession, tenant_id, inv: BillingInvoice) -> dict:
    """Cria o link no primeiro gateway conectado (stripe > mercadopago)."""
    if inv.status != "EMITIDA":
        raise HTTPException(status_code=422, detail="Gere o link com a fatura EMITIDA (rascunho: emita primeiro).")
    if not inv.valor_total or float(inv.valor_total) <= 0:
        raise HTTPException(status_code=422, detail="Fatura sem valor.")

    stripe_creds = await integration_hub.get_credentials(db, tenant_id, "stripe")
    mp_creds = await integration_hub.get_credentials(db, tenant_id, "mercadopago")
    if not stripe_creds and not mp_creds:
        raise HTTPException(
            status_code=422,
            detail="Nenhum gateway de pagamento conectado — conecte Stripe ou Mercado Pago em Integrações.",
        )

    if stripe_creds:
        return await _stripe_checkout(stripe_creds, inv)
    return await _mp_preference(mp_creds, inv)


async def _stripe_checkout(creds: dict, inv: BillingInvoice) -> dict:
    base = _base_url()
    data = {
        "mode": "payment",
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": "brl",
        "line_items[0][price_data][unit_amount]": str(int(round(float(inv.valor_total) * 100))),
        "line_items[0][price_data][product_data][name]": f"Fatura {inv.numero or ''}".strip(),
        "metadata[invoice_id]": str(inv.id),
        "success_url": f"{base}/financeiro/faturas?pagamento=ok",
        "cancel_url": f"{base}/financeiro/faturas?pagamento=cancelado",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                "https://api.stripe.com/v1/checkout/sessions",
                data=data,
                headers={"Authorization": f"Bearer {creds['secret_key']}"},
            )
    except Exception as exc:
        log.warning("stripe_unreachable", error=str(exc))
        raise HTTPException(status_code=502, detail="Stripe inalcançável — tente novamente.")
    if resp.status_code >= 400:
        log.warning("stripe_error", status=resp.status_code, body=resp.text[:300])
        raise HTTPException(status_code=502, detail="Stripe recusou a criação do link — confira a secret key em Integrações.")
    body = resp.json()
    return {"provider": "stripe", "external_id": body["id"], "url": body["url"]}


async def _mp_preference(creds: dict, inv: BillingInvoice) -> dict:
    base = _base_url()
    payload = {
        "items": [{
            "title": f"Fatura {inv.numero or ''}".strip(),
            "quantity": 1,
            "unit_price": float(inv.valor_total),
            "currency_id": "BRL",
        }],
        "external_reference": str(inv.id),
        "back_urls": {
            "success": f"{base}/financeiro/faturas?pagamento=ok",
            "failure": f"{base}/financeiro/faturas?pagamento=erro",
            "pending": f"{base}/financeiro/faturas?pagamento=pendente",
        },
        "notification_url": f"{base}/api/v1/integrations/webhooks/mercadopago?ref={inv.id}",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                "https://api.mercadopago.com/checkout/preferences",
                json=payload,
                headers={"Authorization": f"Bearer {creds['access_token']}"},
            )
    except Exception as exc:
        log.warning("mercadopago_unreachable", error=str(exc))
        raise HTTPException(status_code=502, detail="Mercado Pago inalcançável — tente novamente.")
    if resp.status_code >= 400:
        log.warning("mercadopago_error", status=resp.status_code, body=resp.text[:300])
        raise HTTPException(status_code=502, detail="Mercado Pago recusou a criação do link — confira o access token em Integrações.")
    body = resp.json()
    return {"provider": "mercadopago", "external_id": str(body["id"]), "url": body["init_point"]}


# ─── Confirmação via webhook (verificação server-side) ────────────────────────
async def processar_webhook_pagamento(
    db: AsyncSession, provider: str, payload: dict, query: dict,
) -> dict:
    """Confirma o pagamento consultando a API do provedor. Retorna diagnóstico."""
    try:
        if provider == "stripe":
            return await _confirmar_stripe(db, payload)
        if provider == "mercadopago":
            return await _confirmar_mp(db, payload, query)
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("webhook_pagamento_erro", provider=provider, error=str(exc))
        return {"processed": False, "reason": "erro interno"}
    return {"processed": False, "reason": "provedor sem handler de pagamento"}


async def _load_invoice(db: AsyncSession, invoice_id: str) -> BillingInvoice | None:
    try:
        inv = (await db.execute(
            select(BillingInvoice).where(BillingInvoice.id == invoice_id)
        )).scalar_one_or_none()
    except Exception:
        return None
    return inv


def _criar_entrada_financeira(inv: BillingInvoice, provider: str, nota: str | None = None) -> FinancialEntry:
    """Fase 129 — conecta o pagamento confirmado ao financeiro (`FinancialEntry`)
    do escritório; sem isso a receita real nunca aparecia em `/financial/summary`
    nem `/financial/overdue` (o dashboard e as faturas viviam desconectados)."""
    descricao = f"Fatura {inv.numero or inv.id} paga via {provider}"
    if nota:
        descricao += f" — {nota}"
    return FinancialEntry(
        tipo="RECEITA",
        categoria="HONORARIOS",
        client_id=inv.client_id,
        process_id=inv.process_id,
        descricao=descricao,
        valor=inv.valor_total or Decimal("0"),
        data_pagamento=datetime.now(timezone.utc).date(),
        status="PAGO",
        tenant_id=inv.tenant_id,
    )


async def _notificar_pagamento_a_reconciliar(db: AsyncSession, inv: BillingInvoice) -> None:
    """Fase 129 — dinheiro real foi capturado pelo provedor mas a fatura não
    estava mais EMITIDA (ex.: cancelada antes do webhook chegar). Em vez de só
    logar e descartar (o pagamento sumia do sistema), avisa ADMIN/SOCIO do
    escritório pra reconciliar manualmente."""
    if not inv.tenant_id:
        return
    from app.models.user import User
    from app.models.notification import Notification
    from app.services.notification import publish_notification_ws

    user_ids = (await db.execute(
        select(User.id).where(
            User.tenant_id == inv.tenant_id,
            User.role.in_(("ADMIN", "SOCIO")),
            User.is_active == True,  # noqa: E712
        )
    )).scalars().all()
    for uid in user_ids:
        notif = Notification(
            user_id=uid,
            tenant_id=inv.tenant_id,
            tipo="SISTEMA",
            titulo="Pagamento recebido em fatura não emitida — reconciliar",
            corpo=(
                f"Fatura {inv.numero or inv.id} (R$ {float(inv.valor_total or 0):.2f}) "
                f"foi paga pelo cliente, mas o status atual é {inv.status}. "
                "Verifique manualmente em Financeiro."
            ),
            priority="HIGH",
            link="/financeiro/faturas",
        )
        db.add(notif)
        await publish_notification_ws(notif)


async def _marcar_paga(db: AsyncSession, inv: BillingInvoice, provider: str) -> dict:
    if inv.status == "PAGA":
        return {"processed": True, "reason": "já estava paga (idempotente)"}
    if inv.status != "EMITIDA":
        log.warning("webhook_pagamento_status_invalido", invoice=str(inv.id), status=inv.status)
        db.add(_criar_entrada_financeira(
            inv, provider,
            nota=f"fatura estava {inv.status} no momento do pagamento — reconciliar manualmente",
        ))
        await _notificar_pagamento_a_reconciliar(db, inv)
        await db.flush()
        return {"processed": False, "reason": f"fatura em {inv.status} — pagamento registrado pra reconciliação manual"}
    inv.status = "PAGA"
    inv.pago_em = datetime.now(timezone.utc)
    db.add(_criar_entrada_financeira(inv, provider))
    await db.flush()
    log.info("fatura_paga_via_webhook", invoice=str(inv.id), provider=provider)
    return {"processed": True, "reason": "fatura marcada como PAGA"}


async def _confirmar_stripe(db: AsyncSession, payload: dict) -> dict:
    if payload.get("type") != "checkout.session.completed":
        return {"processed": False, "reason": "evento ignorado"}
    obj = (payload.get("data") or {}).get("object") or {}
    session_id = obj.get("id")
    invoice_id = (obj.get("metadata") or {}).get("invoice_id")
    if not session_id or not invoice_id:
        return {"processed": False, "reason": "payload sem session/invoice"}

    inv = await _load_invoice(db, invoice_id)
    if not inv:
        return {"processed": False, "reason": "fatura desconhecida"}
    if inv.payment_external_id and inv.payment_external_id != session_id:
        return {"processed": False, "reason": "session não corresponde à fatura"}

    creds = await integration_hub.get_credentials(db, inv.tenant_id, "stripe")
    if not creds:
        return {"processed": False, "reason": "escritório sem Stripe conectado"}

    # Verificação REAL: buscar a session na API com a chave do escritório
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"https://api.stripe.com/v1/checkout/sessions/{session_id}",
            headers={"Authorization": f"Bearer {creds['secret_key']}"},
        )
    if resp.status_code >= 400:
        return {"processed": False, "reason": "session não encontrada no Stripe"}
    session = resp.json()
    if session.get("payment_status") != "paid":
        return {"processed": False, "reason": f"payment_status={session.get('payment_status')}"}
    if (session.get("metadata") or {}).get("invoice_id") != str(inv.id):
        return {"processed": False, "reason": "metadata da session não bate com a fatura"}
    return await _marcar_paga(db, inv, "stripe")


async def _confirmar_mp(db: AsyncSession, payload: dict, query: dict) -> dict:
    tipo = payload.get("type") or query.get("type") or query.get("topic")
    if tipo not in ("payment", "merchant_order"):
        return {"processed": False, "reason": "evento ignorado"}
    payment_id = ((payload.get("data") or {}).get("id")) or query.get("data.id") or query.get("id")
    invoice_id = query.get("ref")
    if not payment_id or not invoice_id:
        return {"processed": False, "reason": "payload sem payment/ref"}

    inv = await _load_invoice(db, invoice_id)
    if not inv:
        return {"processed": False, "reason": "fatura desconhecida"}

    creds = await integration_hub.get_credentials(db, inv.tenant_id, "mercadopago")
    if not creds:
        return {"processed": False, "reason": "escritório sem Mercado Pago conectado"}

    # Verificação REAL: buscar o pagamento na API com o token do escritório
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"https://api.mercadopago.com/v1/payments/{payment_id}",
            headers={"Authorization": f"Bearer {creds['access_token']}"},
        )
    if resp.status_code >= 400:
        return {"processed": False, "reason": "pagamento não encontrado no Mercado Pago"}
    pagamento = resp.json()
    if pagamento.get("status") != "approved":
        return {"processed": False, "reason": f"status={pagamento.get('status')}"}
    if str(pagamento.get("external_reference")) != str(inv.id):
        return {"processed": False, "reason": "external_reference não bate com a fatura"}
    return await _marcar_paga(db, inv, "mercadopago")
