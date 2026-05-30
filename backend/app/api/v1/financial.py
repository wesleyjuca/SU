"""Endpoints financeiros — honorários, despesas e relatórios."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from decimal import Decimal
from datetime import date
import uuid

from app.db.base import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.financial import FinancialEntry

router = APIRouter(prefix="/financial", tags=["financial"])


class FinancialEntryCreate(BaseModel):
    tipo: str            # RECEITA, DESPESA
    categoria: str | None = None
    client_id: str | None = None
    process_id: str | None = None
    descricao: str
    valor: float
    data_vencimento: date | None = None
    status: str = "PENDENTE"


class FinancialEntryResponse(BaseModel):
    id: str
    tipo: str
    categoria: str | None
    descricao: str
    valor: float
    status: str
    data_vencimento: str | None
    data_pagamento: str | None
    client_id: str | None
    process_id: str | None
    created_at: str


@router.get("", response_model=list[FinancialEntryResponse])
async def list_entries(
    tipo: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(FinancialEntry)
        .where(FinancialEntry.tenant_id == current_user.tenant_id)
        .order_by(desc(FinancialEntry.created_at))
        .limit(limit)
    )
    if tipo:
        query = query.where(FinancialEntry.tipo == tipo)
    if status:
        query = query.where(FinancialEntry.status == status)
    result = await db.execute(query)
    entries = result.scalars().all()
    return [_to_response(e) for e in entries]


@router.post("", response_model=FinancialEntryResponse, status_code=201)
async def create_entry(
    body: FinancialEntryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = FinancialEntry(
        tipo=body.tipo,
        categoria=body.categoria,
        client_id=uuid.UUID(body.client_id) if body.client_id else None,
        process_id=uuid.UUID(body.process_id) if body.process_id else None,
        descricao=body.descricao,
        valor=Decimal(str(body.valor)),
        data_vencimento=body.data_vencimento,
        status=body.status,
        created_by=current_user.id,
        tenant_id=current_user.tenant_id,
    )
    db.add(entry)
    await db.flush()
    return _to_response(entry)


class FinancialEntryUpdate(BaseModel):
    descricao: str | None = None
    valor: float | None = None
    categoria: str | None = None
    data_vencimento: date | None = None
    status: str | None = None


@router.put("/{entry_id}", response_model=FinancialEntryResponse)
async def update_entry(
    entry_id: str,
    body: FinancialEntryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.core.exceptions import NotFoundError
    result = await db.execute(
        select(FinancialEntry).where(
            FinancialEntry.id == uuid.UUID(entry_id),
            FinancialEntry.tenant_id == current_user.tenant_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise NotFoundError("Lançamento", entry_id)
    updates = body.model_dump(exclude_none=True)
    if "valor" in updates:
        entry.valor = Decimal(str(updates.pop("valor")))
    for field, value in updates.items():
        setattr(entry, field, value)
    await db.flush()
    return _to_response(entry)


@router.delete("/{entry_id}", status_code=204)
async def delete_entry(
    entry_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.core.exceptions import NotFoundError
    result = await db.execute(
        select(FinancialEntry).where(
            FinancialEntry.id == uuid.UUID(entry_id),
            FinancialEntry.tenant_id == current_user.tenant_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise NotFoundError("Lançamento", entry_id)
    await db.delete(entry)
    await db.flush()


@router.get("/export")
async def export_financial(
    tipo: str | None = None,
    status: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Exporta lançamentos como CSV."""
    import csv, io
    from fastapi.responses import StreamingResponse

    query = (
        select(FinancialEntry)
        .where(FinancialEntry.tenant_id == current_user.tenant_id)
        .order_by(desc(FinancialEntry.created_at))
    )
    if tipo:
        query = query.where(FinancialEntry.tipo == tipo)
    if status:
        query = query.where(FinancialEntry.status == status)
    result = await db.execute(query)
    entries = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Tipo", "Categoria", "Descrição", "Valor", "Status", "Vencimento", "Pagamento", "Criado em"])
    for e in entries:
        writer.writerow([
            str(e.id), e.tipo, e.categoria or "", e.descricao, float(e.valor),
            e.status,
            e.data_vencimento.isoformat() if e.data_vencimento else "",
            e.data_pagamento.isoformat() if e.data_pagamento else "",
            e.created_at.isoformat(),
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=financeiro.csv"},
    )


@router.post("/{entry_id}/mark-paid")
async def mark_paid(
    entry_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FinancialEntry).where(
            FinancialEntry.id == uuid.UUID(entry_id),
            FinancialEntry.tenant_id == current_user.tenant_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("Lançamento", entry_id)
    entry.status = "PAGO"
    entry.data_pagamento = date.today()
    return {"message": "Marcado como pago", "id": entry_id}


@router.get("/monthly")
async def monthly_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retorna receitas e despesas pagas agrupadas por mês (últimos 6 meses)."""
    from sqlalchemy import func, extract
    from datetime import date, timedelta

    six_months_ago = date.today().replace(day=1) - timedelta(days=150)
    result = await db.execute(
        select(
            extract("year", FinancialEntry.created_at).label("ano"),
            extract("month", FinancialEntry.created_at).label("mes"),
            FinancialEntry.tipo,
            func.sum(FinancialEntry.valor).label("total"),
        )
        .where(
            FinancialEntry.tenant_id == current_user.tenant_id,
            FinancialEntry.status == "PAGO",
            FinancialEntry.created_at >= six_months_ago,
        )
        .group_by("ano", "mes", FinancialEntry.tipo)
        .order_by("ano", "mes")
    )
    rows = result.all()

    months: dict[str, dict] = {}
    for row in rows:
        key = f"{int(row.ano)}-{int(row.mes):02d}"
        if key not in months:
            months[key] = {"mes": key, "receitas": 0.0, "despesas": 0.0}
        if row.tipo == "RECEITA":
            months[key]["receitas"] = float(row.total)
        else:
            months[key]["despesas"] = float(row.total)

    return {"data": list(months.values())}


@router.get("/summary")
async def financial_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Resumo financeiro via analytics_agent."""
    from app.agents.financial.financial_agent import FinancialAgent
    from app.agents.brain.context import AgentContext
    agent = FinancialAgent(db=db)
    ctx = AgentContext(task_type="financial_report", task_input={"action": "summary"})
    result = await agent.run(ctx)
    return result.output


def _to_response(e: FinancialEntry) -> FinancialEntryResponse:
    return FinancialEntryResponse(
        id=str(e.id),
        tipo=e.tipo,
        categoria=e.categoria,
        descricao=e.descricao,
        valor=float(e.valor),
        status=e.status,
        data_vencimento=e.data_vencimento.isoformat() if e.data_vencimento else None,
        data_pagamento=e.data_pagamento.isoformat() if e.data_pagamento else None,
        client_id=str(e.client_id) if e.client_id else None,
        process_id=str(e.process_id) if e.process_id else None,
        created_at=e.created_at.isoformat(),
    )
