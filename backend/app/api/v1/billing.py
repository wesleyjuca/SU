"""Cobrança do SaaS por escritório — billing manual (somente SUPERADMIN).

Fluxo manual: o SUPERADMIN configura a mensalidade, registra pagamentos à mão e
suspende/reativa escritórios inadimplentes. Gateway automático fica para a P3.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field
from datetime import date
from decimal import Decimal
import uuid

from app.db.base import get_db
from app.dependencies import require_role
from app.models.user import User
from app.models.tenant import Tenant
from app.models.billing import BillingAccount, TenantPayment
from app.core.tenant import DEFAULT_TENANT_SLUG

router = APIRouter(prefix="/billing", tags=["billing"])


def _next_due(dia_vencimento: int, ref: date) -> date:
    """Próximo vencimento a partir de uma data de referência e do dia do mês."""
    dia = max(1, min(28, dia_vencimento))
    y, m = ref.year, ref.month
    if ref.day >= dia:  # já passou o vencimento deste mês → próximo mês
        m += 1
        if m > 12:
            m = 1
            y += 1
    return date(y, m, dia)


async def _get_tenant(db: AsyncSession, tenant_id: str) -> Tenant:
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == uuid.UUID(tenant_id))
    )).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Escritório não encontrado.")
    return tenant


async def _get_or_create_account(db: AsyncSession, tenant_id: uuid.UUID) -> BillingAccount:
    acc = (await db.execute(
        select(BillingAccount).where(BillingAccount.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if not acc:
        acc = BillingAccount(tenant_id=tenant_id)
        db.add(acc)
        await db.flush()
    return acc


class BillingConfig(BaseModel):
    valor_mensal: Decimal = Field(ge=0)
    dia_vencimento: int = Field(ge=1, le=28)
    observacao: str | None = None


class PaymentCreate(BaseModel):
    valor: Decimal = Field(gt=0)
    competencia: str = Field(pattern=r"^\d{4}-\d{2}$")  # "YYYY-MM"
    observacao: str | None = None


@router.get("")
async def list_billing(
    current_user: User = Depends(require_role("SUPERADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Lista escritórios com situação de cobrança e último pagamento."""
    tenants = (await db.execute(select(Tenant).order_by(Tenant.created_at))).scalars().all()
    accounts = {a.tenant_id: a for a in (await db.execute(select(BillingAccount))).scalars().all()}
    last_pay = dict((await db.execute(
        select(TenantPayment.tenant_id, func.max(TenantPayment.pago_em)).group_by(TenantPayment.tenant_id)
    )).all())

    out = []
    for t in tenants:
        acc = accounts.get(t.id)
        out.append({
            "tenant_id": str(t.id),
            "name": t.name,
            "slug": t.slug,
            "plan": t.plan,
            "is_root": t.slug == DEFAULT_TENANT_SLUG,
            "configured": acc is not None,
            "valor_mensal": float(acc.valor_mensal) if acc else None,
            "dia_vencimento": acc.dia_vencimento if acc else None,
            "status": acc.status if acc else "NAO_CONFIGURADO",
            "proximo_vencimento": acc.proximo_vencimento.isoformat() if acc and acc.proximo_vencimento else None,
            "ultimo_pagamento": last_pay[t.id].isoformat() if t.id in last_pay and last_pay[t.id] else None,
        })
    return out


@router.put("/{tenant_id}")
async def set_billing_config(
    tenant_id: str,
    body: BillingConfig,
    current_user: User = Depends(require_role("SUPERADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Cria/atualiza a mensalidade e o dia de vencimento do escritório."""
    tenant = await _get_tenant(db, tenant_id)
    acc = await _get_or_create_account(db, tenant.id)
    acc.valor_mensal = body.valor_mensal
    acc.dia_vencimento = body.dia_vencimento
    acc.observacao = body.observacao
    if acc.status == "NAO_CONFIGURADO":
        acc.status = "ATIVO"
    if not acc.proximo_vencimento:
        acc.proximo_vencimento = _next_due(body.dia_vencimento, date.today())
    await db.commit()
    return {"message": "Cobrança configurada.", "status": acc.status,
            "proximo_vencimento": acc.proximo_vencimento.isoformat() if acc.proximo_vencimento else None}


@router.post("/{tenant_id}/payments", status_code=201)
async def register_payment(
    tenant_id: str,
    body: PaymentCreate,
    current_user: User = Depends(require_role("SUPERADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Registra um pagamento manual: reativa o escritório e avança o vencimento."""
    tenant = await _get_tenant(db, tenant_id)
    acc = await _get_or_create_account(db, tenant.id)
    db.add(TenantPayment(
        tenant_id=tenant.id, valor=body.valor, competencia=body.competencia,
        registrado_por=current_user.id, observacao=body.observacao,
    ))
    acc.status = "ATIVO"
    base = acc.proximo_vencimento or date.today()
    acc.proximo_vencimento = _next_due(acc.dia_vencimento, base)
    await db.commit()
    return {"message": "Pagamento registrado.", "status": acc.status,
            "proximo_vencimento": acc.proximo_vencimento.isoformat()}


@router.post("/{tenant_id}/suspend")
async def suspend_tenant(
    tenant_id: str,
    current_user: User = Depends(require_role("SUPERADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Suspende o escritório (bloqueio suave de escrita)."""
    tenant = await _get_tenant(db, tenant_id)
    if tenant.slug == DEFAULT_TENANT_SLUG:
        raise HTTPException(status_code=422, detail="O escritório raiz da plataforma não pode ser suspenso.")
    acc = await _get_or_create_account(db, tenant.id)
    acc.status = "SUSPENSO"
    await db.commit()
    return {"message": "Escritório suspenso.", "status": acc.status}


@router.post("/{tenant_id}/reactivate")
async def reactivate_tenant(
    tenant_id: str,
    current_user: User = Depends(require_role("SUPERADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Reativa o escritório (remove o bloqueio de escrita)."""
    tenant = await _get_tenant(db, tenant_id)
    acc = await _get_or_create_account(db, tenant.id)
    acc.status = "ATIVO"
    await db.commit()
    return {"message": "Escritório reativado.", "status": acc.status}


@router.get("/{tenant_id}/payments")
async def payment_history(
    tenant_id: str,
    current_user: User = Depends(require_role("SUPERADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Histórico de pagamentos do escritório."""
    rows = (await db.execute(
        select(TenantPayment).where(TenantPayment.tenant_id == uuid.UUID(tenant_id))
        .order_by(TenantPayment.pago_em.desc())
    )).scalars().all()
    return [
        {
            "id": str(p.id),
            "valor": float(p.valor),
            "competencia": p.competencia,
            "pago_em": p.pago_em.isoformat() if p.pago_em else None,
            "metodo": p.metodo,
            "observacao": p.observacao,
        }
        for p in rows
    ]
