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
    query = select(FinancialEntry).order_by(desc(FinancialEntry.created_at)).limit(limit)
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
    )
    db.add(entry)
    await db.flush()
    return _to_response(entry)


@router.post("/{entry_id}/mark-paid")
async def mark_paid(
    entry_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(FinancialEntry).where(FinancialEntry.id == uuid.UUID(entry_id)))
    entry = result.scalar_one_or_none()
    if not entry:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("Lançamento", entry_id)
    entry.status = "PAGO"
    entry.data_pagamento = date.today()
    return {"message": "Marcado como pago", "id": entry_id}


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
