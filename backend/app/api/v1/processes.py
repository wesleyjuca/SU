"""Endpoints para gestão de processos judiciais."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
import uuid

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


@router.get("/agenda")
async def get_agenda(
    dias: int = Query(default=30, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retorna todos os prazos pendentes do tenant com dados do processo, ordenados por data."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc).date()
    cutoff = now + timedelta(days=dias)

    q = await db.execute(
        select(ProcessDeadline, LegalProcess)
        .join(LegalProcess, ProcessDeadline.process_id == LegalProcess.id)
        .where(
            LegalProcess.tenant_id == current_user.tenant_id,
            ProcessDeadline.status == "PENDENTE",
            ProcessDeadline.data_prazo <= cutoff,
        )
        .order_by(ProcessDeadline.data_prazo.asc())
    )
    rows = q.all()
    return [
        {
            "id": str(d.id),
            "descricao": d.descricao,
            "tipo": d.tipo,
            "status": d.status,
            "data_prazo": d.data_prazo.isoformat() if d.data_prazo else None,
            "data_fatal": d.data_fatal.isoformat() if d.data_fatal else None,
            "process_id": str(p.id),
            "numero_cnj": p.numero_cnj,
            "tribunal": p.tribunal,
            "area_direito": p.area_direito,
        }
        for d, p in rows
    ]


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
    query = (
        select(LegalProcess)
        .where(LegalProcess.tenant_id == current_user.tenant_id)
        .order_by(LegalProcess.proximo_prazo_at.asc().nulls_last())
        .offset(offset)
        .limit(limit)
    )

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
        tenant_id=current_user.tenant_id,
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
    result = await db.execute(
        select(LegalProcess).where(
            LegalProcess.id == uuid.UUID(process_id),
            LegalProcess.tenant_id == current_user.tenant_id,
        )
    )
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


@router.put("/{process_id}", response_model=ProcessResponse)
async def update_process(
    process_id: str,
    body: ProcessCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LegalProcess).where(
            LegalProcess.id == uuid.UUID(process_id),
            LegalProcess.tenant_id == current_user.tenant_id,
        )
    )
    process = result.scalar_one_or_none()
    if not process:
        raise NotFoundError("Processo", process_id)
    for field, value in body.model_dump(exclude_none=True).items():
        if field == "client_id" and value:
            setattr(process, field, uuid.UUID(value))
        else:
            setattr(process, field, value)
    await db.flush()
    return _to_response(process)


@router.delete("/{process_id}", status_code=204)
async def archive_process(
    process_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LegalProcess).where(
            LegalProcess.id == uuid.UUID(process_id),
            LegalProcess.tenant_id == current_user.tenant_id,
        )
    )
    process = result.scalar_one_or_none()
    if not process:
        raise NotFoundError("Processo", process_id)
    process.situacao = "ARQUIVADO"
    process.monitoring_active = False
    await db.flush()


class MovementCreate(BaseModel):
    descricao: str
    tipo: str | None = None
    data_movimento: str | None = None


@router.post("/{process_id}/movements", status_code=201)
async def create_movement(
    process_id: str,
    body: MovementCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timezone
    result = await db.execute(select(LegalProcess).where(LegalProcess.id == uuid.UUID(process_id)))
    if not result.scalar_one_or_none():
        raise NotFoundError("Processo", process_id)
    data_mov = (
        datetime.fromisoformat(body.data_movimento)
        if body.data_movimento
        else datetime.now(timezone.utc)
    )
    movement = ProcessMovement(
        process_id=uuid.UUID(process_id),
        descricao=body.descricao,
        tipo=body.tipo,
        data_movimento=data_mov,
    )
    db.add(movement)
    await db.flush()
    return {
        "id": str(movement.id),
        "process_id": process_id,
        "descricao": movement.descricao,
        "tipo": movement.tipo,
        "data": movement.data_movimento.isoformat(),
    }


class DeadlineCreate(BaseModel):
    descricao: str
    tipo: str | None = None
    data_prazo: str
    data_fatal: str | None = None
    observacoes: str | None = None


@router.post("/{process_id}/deadlines", status_code=201)
async def create_deadline(
    process_id: str,
    body: DeadlineCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from datetime import date as date_type
    result = await db.execute(
        select(LegalProcess).where(
            LegalProcess.id == uuid.UUID(process_id),
            LegalProcess.tenant_id == current_user.tenant_id,
        )
    )
    if not result.scalar_one_or_none():
        raise NotFoundError("Processo", process_id)

    deadline = ProcessDeadline(
        process_id=uuid.UUID(process_id),
        descricao=body.descricao,
        tipo=body.tipo,
        data_prazo=date_type.fromisoformat(body.data_prazo),
        data_fatal=date_type.fromisoformat(body.data_fatal) if body.data_fatal else None,
        status="PENDENTE",
        responsavel_id=current_user.id,
    )
    db.add(deadline)
    await db.flush()
    return {
        "id": str(deadline.id),
        "process_id": process_id,
        "descricao": deadline.descricao,
        "tipo": deadline.tipo,
        "data_prazo": deadline.data_prazo.isoformat(),
        "data_fatal": deadline.data_fatal.isoformat() if deadline.data_fatal else None,
        "status": deadline.status,
    }


class DeadlineUpdate(BaseModel):
    status: str
    descricao: str | None = None


@router.put("/{process_id}/deadlines/{deadline_id}")
async def update_deadline(
    process_id: str,
    deadline_id: str,
    body: DeadlineUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProcessDeadline).where(
            ProcessDeadline.id == uuid.UUID(deadline_id),
            ProcessDeadline.process_id == uuid.UUID(process_id),
        )
    )
    deadline = result.scalar_one_or_none()
    if not deadline:
        raise NotFoundError("Prazo", deadline_id)
    deadline.status = body.status
    if body.descricao:
        deadline.descricao = body.descricao
    await db.flush()
    return {"id": str(deadline.id), "status": deadline.status}


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
