"""Faturamento a cliente — faturas de honorários (PDF timbrado + controle de status)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import uuid
import secrets
import structlog

from app.db.base import get_db
from app.dependencies import require_role
from app.models.user import User
from app.models.financial import BillingInvoice
from app.models.client import Client

log = structlog.get_logger()

router = APIRouter(prefix="/financial/invoices", tags=["invoices"])

_STATUS = {"RASCUNHO", "EMITIDA", "PAGA", "CANCELADA"}
# Máquina de estados: transições válidas. PAGA e CANCELADA são terminais —
# impede reverter uma fatura paga (ex.: PAGA→RASCUNHO) que corrompia o financeiro.
_TRANSICOES = {
    "RASCUNHO": {"EMITIDA", "CANCELADA"},
    "EMITIDA": {"PAGA", "CANCELADA"},
    "PAGA": set(),
    "CANCELADA": set(),
}


class InvoiceItem(BaseModel):
    descricao: str
    valor: Decimal = Field(ge=0)


class InvoiceCreate(BaseModel):
    client_id: str
    itens: list[InvoiceItem]
    descricao: str | None = None
    process_id: str | None = None
    periodo_inicio: str | None = None
    periodo_fim: str | None = None
    data_vencimento: str | None = None


class InvoicePatch(BaseModel):
    status: str


def _gerar_numero() -> str:
    return f"FAT-{datetime.now(timezone.utc).strftime('%Y%m')}-{secrets.token_hex(3).upper()}"


def _to_dict(inv: BillingInvoice, cliente_nome: str | None = None) -> dict:
    return {
        "id": str(inv.id),
        "numero": inv.numero,
        "cliente": cliente_nome,
        "client_id": str(inv.client_id) if inv.client_id else None,
        "descricao": inv.descricao,
        "itens": inv.itens or [],
        "periodo_inicio": inv.periodo_inicio.isoformat() if inv.periodo_inicio else None,
        "periodo_fim": inv.periodo_fim.isoformat() if inv.periodo_fim else None,
        "data_vencimento": inv.data_vencimento.isoformat() if inv.data_vencimento else None,
        "valor_total": float(inv.valor_total) if inv.valor_total is not None else 0.0,
        "status": inv.status,
        "emitido_em": inv.emitido_em.isoformat() if inv.emitido_em else None,
        "pago_em": inv.pago_em.isoformat() if inv.pago_em else None,
        "payment_link": inv.payment_link,
        "payment_provider": inv.payment_provider,
    }


async def _get_invoice(db: AsyncSession, invoice_id: str, tenant_id, for_update: bool = False) -> BillingInvoice:
    query = select(BillingInvoice).where(
        BillingInvoice.id == uuid.UUID(invoice_id),
        BillingInvoice.tenant_id == tenant_id,  # isolamento multi-tenant
    )
    if for_update:
        # Fase 129 — lock de linha: serializa 2 chamadas concorrentes de geração
        # de link de pagamento pra mesma fatura (a segunda espera a primeira
        # terminar/commitar e então vê o payment_link já setado, em vez de
        # criar uma segunda sessão Stripe/MP órfã).
        query = query.with_for_update()
    inv = (await db.execute(query)).scalar_one_or_none()
    if not inv:
        raise HTTPException(status_code=404, detail="Fatura não encontrada.")
    return inv


@router.get("")
async def list_invoices(
    status: str | None = Query(default=None),
    client_id: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    q = select(BillingInvoice).where(BillingInvoice.tenant_id == current_user.tenant_id)
    if status:
        q = q.where(BillingInvoice.status == status)
    if client_id:
        q = q.where(BillingInvoice.client_id == uuid.UUID(client_id))
    q = q.order_by(BillingInvoice.created_at.desc()).offset(offset).limit(limit)
    invoices = (await db.execute(q)).scalars().all()
    nomes = {}
    cids = [inv.client_id for inv in invoices if inv.client_id]
    if cids:
        for c in (await db.execute(select(Client).where(Client.id.in_(cids)))).scalars().all():
            nomes[c.id] = c.nome_completo
    return [_to_dict(inv, nomes.get(inv.client_id)) for inv in invoices]


@router.post("", status_code=201)
async def create_invoice(
    body: InvoiceCreate,
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    if not body.itens:
        raise HTTPException(status_code=422, detail="Informe ao menos um item.")
    # Cliente deve pertencer ao tenant
    cliente = (await db.execute(
        select(Client).where(Client.id == uuid.UUID(body.client_id), Client.tenant_id == current_user.tenant_id)
    )).scalar_one_or_none()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")

    total = sum((it.valor for it in body.itens), Decimal("0"))

    # Fase 129 — idempotência: bloqueia duplicata óbvia (mesmo cliente + mesmo
    # valor, fatura ainda ativa, criada há pouco) — protege contra double-click
    # ou reenvio de rede criando 2 faturas/links de pagamento pro mesmo trabalho.
    janela = datetime.now(timezone.utc) - timedelta(minutes=5)
    duplicata = (await db.execute(
        select(BillingInvoice).where(
            BillingInvoice.tenant_id == current_user.tenant_id,
            BillingInvoice.client_id == cliente.id,
            BillingInvoice.valor_total == total,
            BillingInvoice.status.in_(("RASCUNHO", "EMITIDA")),
            BillingInvoice.created_at >= janela,
        )
    )).scalar_one_or_none()
    if duplicata:
        raise HTTPException(
            status_code=409,
            detail=f"Já existe uma fatura recente ({duplicata.numero}) pro mesmo cliente e valor — "
                   "confira antes de criar outra.",
        )

    if body.data_vencimento and date.fromisoformat(body.data_vencimento) < datetime.now(timezone.utc).date():
        log.warning("fatura_vencimento_no_passado", client_id=body.client_id, data=body.data_vencimento)

    inv = BillingInvoice(
        tenant_id=current_user.tenant_id,
        client_id=cliente.id,
        process_id=uuid.UUID(body.process_id) if body.process_id else None,
        numero=_gerar_numero(),
        descricao=body.descricao,
        # Fase 129 — preserva precisão Decimal na serialização (antes gravava
        # float, divergindo em centavos de valor_total pra certos valores).
        itens=[{"descricao": it.descricao, "valor": str(it.valor)} for it in body.itens],
        periodo_inicio=date.fromisoformat(body.periodo_inicio) if body.periodo_inicio else None,
        periodo_fim=date.fromisoformat(body.periodo_fim) if body.periodo_fim else None,
        data_vencimento=date.fromisoformat(body.data_vencimento) if body.data_vencimento else None,
        valor_total=total,
        status="RASCUNHO",
        created_by=current_user.id,
    )
    db.add(inv)
    await db.commit()
    aviso = None
    if body.data_vencimento and date.fromisoformat(body.data_vencimento) < datetime.now(timezone.utc).date():
        aviso = "Atenção: a data de vencimento informada já passou."
    resposta = _to_dict(inv, cliente.nome_completo)
    if aviso:
        resposta["aviso"] = aviso
    return resposta


@router.patch("/{invoice_id}")
async def patch_invoice(
    invoice_id: str,
    body: InvoicePatch,
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    if body.status not in _STATUS:
        raise HTTPException(status_code=422, detail=f"Status inválido. Use: {', '.join(sorted(_STATUS))}")
    inv = await _get_invoice(db, invoice_id, current_user.tenant_id)
    if body.status != inv.status and body.status not in _TRANSICOES.get(inv.status, set()):
        raise HTTPException(
            status_code=422,
            detail=f"Transição inválida: {inv.status} → {body.status}. "
                   "Uma fatura paga ou cancelada não pode ser revertida.",
        )
    inv.status = body.status
    if body.status == "EMITIDA" and not inv.emitido_em:
        inv.emitido_em = datetime.now(timezone.utc)
    if body.status == "PAGA" and not inv.pago_em:
        inv.pago_em = datetime.now(timezone.utc)
    await db.commit()
    return {"message": "Fatura atualizada.", "status": inv.status}


@router.post("/{invoice_id}/payment-link")
async def gerar_link_pagamento(
    invoice_id: str,
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    """Gera o link de pagamento no gateway conectado (Stripe/Mercado Pago).

    O cliente paga pelo link; o webhook do provedor confirma e a fatura vira
    PAGA automaticamente (verificação server-side na API do provedor)."""
    from app.services.payment_gateway import criar_link_pagamento

    # Fase 129 — lock de linha: sem isso, 2 chamadas concorrentes (double-click)
    # liam payment_link=None ao mesmo tempo e criavam 2 sessões Stripe/MP
    # separadas — uma delas ficava órfã, e se o cliente pagasse por ela o
    # pagamento não batia com a fatura (rejeitado como "session não
    # corresponde"). Com FOR UPDATE, a 2ª requisição espera a 1ª terminar e
    # já encontra o payment_link setado.
    inv = await _get_invoice(db, invoice_id, current_user.tenant_id, for_update=True)
    if inv.payment_link and inv.status == "EMITIDA":
        return {"message": "Link já gerado.", "payment_link": inv.payment_link, "provider": inv.payment_provider}
    result = await criar_link_pagamento(db, current_user.tenant_id, inv)
    inv.payment_link = result["url"]
    inv.payment_provider = result["provider"]
    inv.payment_external_id = result["external_id"]
    await db.flush()

    # WhatsApp best-effort ao cliente (se conectado e com telefone cadastrado)
    whatsapp_enviado = False
    if inv.client_id:
        cliente = (await db.execute(
            select(Client).where(Client.id == inv.client_id, Client.tenant_id == current_user.tenant_id)
        )).scalar_one_or_none()
        if cliente and cliente.telefone:
            from app.services.whatsapp import enviar_whatsapp
            whatsapp_enviado = await enviar_whatsapp(
                db, current_user.tenant_id, cliente.telefone,
                f"Fatura {inv.numero or ''} no valor de R$ {float(inv.valor_total):.2f}. "
                f"Pague pelo link: {inv.payment_link}",
            )

    return {
        "message": "Link de pagamento gerado."
                   + (" Enviado ao cliente por WhatsApp." if whatsapp_enviado else ""),
        "payment_link": inv.payment_link,
        "provider": inv.payment_provider,
        "whatsapp_enviado": whatsapp_enviado,
    }


@router.delete("/{invoice_id}", status_code=204)
async def delete_invoice(
    invoice_id: str,
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    inv = await _get_invoice(db, invoice_id, current_user.tenant_id)
    if inv.status != "RASCUNHO":
        raise HTTPException(status_code=422, detail="Só rascunhos podem ser excluídos; cancele a fatura emitida.")
    await db.delete(inv)
    await db.commit()


@router.get("/{invoice_id}/pdf")
async def invoice_pdf(
    invoice_id: str,
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    from app.utils.pdf_builder import build_invoice_pdf
    from app.models.tenant import TenantConfig
    inv = await _get_invoice(db, invoice_id, current_user.tenant_id)
    cliente = (await db.execute(select(Client).where(Client.id == inv.client_id))).scalar_one_or_none()

    letterhead = None
    cfg = (await db.execute(
        select(TenantConfig).where(TenantConfig.tenant_id == current_user.tenant_id)
    )).scalar_one_or_none()
    if cfg:
        letterhead = dict((cfg.document_templates or {}).get("letterhead", {}))
        from app.services.letterhead import resolve_logo_data_url
        logo_data_url = await resolve_logo_data_url(cfg)
        if logo_data_url:
            letterhead["logo_data_url"] = logo_data_url

    periodo = ""
    if inv.periodo_inicio and inv.periodo_fim:
        periodo = f"{inv.periodo_inicio.strftime('%d/%m/%Y')} a {inv.periodo_fim.strftime('%d/%m/%Y')}"
    pdf = build_invoice_pdf(
        numero=inv.numero or "—",
        cliente_nome=cliente.nome_completo if cliente else "—",
        periodo=periodo,
        itens=inv.itens or [],
        valor_total=float(inv.valor_total or 0),
        data_vencimento=inv.data_vencimento.strftime("%d/%m/%Y") if inv.data_vencimento else None,
        letterhead=letterhead,
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="fatura-{inv.numero}.pdf"'},
    )
