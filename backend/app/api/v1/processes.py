"""Endpoints para gestão de processos judiciais."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from pydantic import BaseModel
from typing import Any
import uuid
from datetime import date

from app.db.base import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.process import LegalProcess, ProcessMovement, ProcessDeadline
from app.core.exceptions import NotFoundError

router = APIRouter(prefix="/processes", tags=["processes"])


class ProcessCreate(BaseModel):
    numero_cnj: str | None = None
    tribunal: str
    vara: str | None = None
    comarca: str | None = None
    uf: str | None = None
    tipo_acao: str | None = None
    area_direito: str | None = None
    fase: str | None = None
    valor_causa: float | None = None
    client_id: str | None = None
    parte_contraria: str | None = None
    polo: str | None = None
    oab_responsavel: str | None = None
    monitoring_active: bool = True


class ProcessResponse(BaseModel):
    id: str
    numero_cnj: str | None
    tribunal: str
    vara: str | None
    area_direito: str | None
    situacao: str
    valor_causa: float | None
    client_id: str | None
    responsavel_id: str | None
    proximo_prazo_at: str | None
    ultimo_andamento_at: str | None
    monitoring_active: bool
    created_at: str


@router.get("", response_model=list[ProcessResponse])
async def list_processes(
    tribunal: str | None = None,
    area_direito: str | None = None,
    situacao: str | None = None,
    client_id: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(LegalProcess).order_by(LegalProcess.proximo_prazo_at.asc().nulls_last()).offset(offset).limit(limit)

    if tribunal:
        query = query.where(LegalProcess.tribunal == tribunal)
    if area_direito:
        query = query.where(LegalProcess.area_direito == area_direito)
    if situacao:
        query = query.where(LegalProcess.situacao == situacao)
    if client_id:
        query = query.where(LegalProcess.client_id == uuid.UUID(client_id))

    result = await db.execute(query)
    processes = result.scalars().all()
    return [_to_response(p) for p in processes]


@router.post("", response_model=ProcessResponse, status_code=201)
async def create_process(
    body: ProcessCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    process = LegalProcess(
        **body.model_dump(exclude_none=True),
        responsavel_id=current_user.id,
        client_id=uuid.UUID(body.client_id) if body.client_id else None,
    )
    db.add(process)
    await db.flush()
    return _to_response(process)


@router.get("/{process_id}", response_model=ProcessResponse)
async def get_process(
    process_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(LegalProcess).where(LegalProcess.id == uuid.UUID(process_id)))
    process = result.scalar_one_or_none()
    if not process:
        raise NotFoundError("Processo", process_id)
    return _to_response(process)


@router.get("/{process_id}/movements")
async def get_movements(
    process_id: str,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProcessMovement)
        .where(ProcessMovement.process_id == uuid.UUID(process_id))
        .order_by(desc(ProcessMovement.data_movimento))
        .limit(limit)
    )
    movements = result.scalars().all()
    return [
        {
            "id": str(m.id),
            "data": m.data_movimento.isoformat(),
            "descricao": m.descricao,
            "tipo": m.tipo,
            "ai_summary": m.ai_summary,
            "documento_url": m.documento_url,
        }
        for m in movements
    ]


@router.get("/{process_id}/deadlines")
async def get_deadlines(
    process_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProcessDeadline)
        .where(
            ProcessDeadline.process_id == uuid.UUID(process_id),
            ProcessDeadline.status == "PENDENTE",
        )
        .order_by(ProcessDeadline.data_prazo.asc())
    )
    deadlines = result.scalars().all()
    return [
        {
            "id": str(d.id),
            "descricao": d.descricao,
            "data_prazo": d.data_prazo.isoformat() if d.data_prazo else None,
            "data_fatal": d.data_fatal.isoformat() if d.data_fatal else None,
            "tipo": d.tipo,
            "status": d.status,
        }
        for d in deadlines
    ]


def _to_response(p: LegalProcess) -> ProcessResponse:
    return ProcessResponse(
        id=str(p.id),
        numero_cnj=p.numero_cnj,
        tribunal=p.tribunal,
        vara=p.vara,
        area_direito=p.area_direito,
        situacao=p.situacao,
        valor_causa=float(p.valor_causa) if p.valor_causa else None,
        client_id=str(p.client_id) if p.client_id else None,
        responsavel_id=str(p.responsavel_id) if p.responsavel_id else None,
        proximo_prazo_at=p.proximo_prazo_at.isoformat() if p.proximo_prazo_at else None,
        ultimo_andamento_at=p.ultimo_andamento_at.isoformat() if p.ultimo_andamento_at else None,
        monitoring_active=p.monitoring_active,
        created_at=p.created_at.isoformat(),
    )
