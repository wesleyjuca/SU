"""Publicações/Intimações capturadas do DJe (Comunica/DJEN) — fila de triagem.

TRIAGEM/HITL: a intimação vira andamento + notificação automaticamente; o PRAZO
só é criado quando o advogado tria (confirma tipo e dias) — evita prazo errado.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from datetime import date as date_type
import uuid

from app.db.base import get_db
from app.dependencies import get_current_user, require_role
from app.models.user import User
from app.models.intimacao import Intimacao
from app.models.process import ProcessDeadline, ProcessMovement
from app.core.exceptions import NotFoundError

router = APIRouter(prefix="/publicacoes", tags=["publicacoes"])


class TriagemRequest(BaseModel):
    tipo: str                    # CONTESTACAO, RECURSO, MANIFESTACAO, ...
    dias: int
    dias_uteis: bool = True
    data_intimacao: str | None = None   # ISO; default = data_disponibilizacao


def _to_dict(i: Intimacao) -> dict:
    return {
        "id": str(i.id),
        "process_id": str(i.process_id) if i.process_id else None,
        "oab": i.oab,
        "numero_cnj": i.numero_cnj_fmt or i.numero_cnj,
        "texto": i.texto,
        "data_disponibilizacao": i.data_disponibilizacao.isoformat() if i.data_disponibilizacao else None,
        "tribunal": i.tribunal,
        "tipo_comunicacao": i.tipo_comunicacao,
        "orgao": i.orgao,
        "link": i.link,
        "status": i.status,
        "deadline_id": str(i.deadline_id) if i.deadline_id else None,
        "created_at": i.created_at.isoformat(),
    }


@router.get("")
async def list_publicacoes(
    status: str | None = Query(default=None),
    mine: bool = Query(default=False, description="Somente intimações dos meus processos"),
    limit: int = Query(default=100, le=300),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(Intimacao)
        .where(Intimacao.tenant_id == current_user.tenant_id)
        .order_by(desc(Intimacao.created_at))
        .limit(limit)
    )
    if status:
        q = q.where(Intimacao.status == status)
    from app.api.v1.processes import _confinar_a_equipe
    if mine or await _confinar_a_equipe(db, current_user):
        from app.models.process import LegalProcess, ProcessTeamMember
        from sqlalchemy import or_
        meus = select(LegalProcess.id).where(
            LegalProcess.tenant_id == current_user.tenant_id,
            or_(
                LegalProcess.responsavel_id == current_user.id,
                LegalProcess.id.in_(
                    select(ProcessTeamMember.process_id).where(ProcessTeamMember.user_id == current_user.id)
                ),
            ),
        )
        q = q.where(Intimacao.process_id.in_(meus))
    rows = (await db.execute(q)).scalars().all()
    return [_to_dict(i) for i in rows]


@router.post("/{intimacao_id}/triagem", status_code=201)
async def triar_publicacao(
    intimacao_id: str,
    body: TriagemRequest,
    current_user: User = Depends(require_role("ADVOGADO", "SOCIO", "ADMIN", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    """Confirma a intimação e cria o PRAZO (CPC art. 219, feriados forenses)."""
    from app.utils.prazo import calcular_prazo
    from app.api.v1.processes import _tenant_feriados

    intim = (await db.execute(
        select(Intimacao).where(
            Intimacao.id == uuid.UUID(intimacao_id),
            Intimacao.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if not intim:
        raise NotFoundError("Intimação", intimacao_id)
    if not intim.process_id:
        raise HTTPException(
            status_code=422,
            detail="Intimação sem processo vinculado. Cadastre/associe o processo (número CNJ) antes de gerar o prazo.",
        )
    if intim.status == "TRIADA":
        raise HTTPException(status_code=422, detail="Intimação já triada.")

    base_data = body.data_intimacao or (intim.data_disponibilizacao.isoformat() if intim.data_disponibilizacao else None)
    if not base_data:
        raise HTTPException(status_code=422, detail="Data de intimação ausente — informe data_intimacao.")

    try:
        r = calcular_prazo(
            date_type.fromisoformat(base_data[:10]),
            body.dias,
            body.dias_uteis,
            await _tenant_feriados(db, current_user.tenant_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Liga ao andamento de intimação do processo, se existir.
    movement_id = (await db.execute(
        select(ProcessMovement.id)
        .where(ProcessMovement.process_id == intim.process_id, ProcessMovement.tipo == "INTIMACAO")
        .order_by(desc(ProcessMovement.data_movimento))
        .limit(1)
    )).scalar_one_or_none()

    deadline = ProcessDeadline(
        process_id=intim.process_id,
        movement_id=movement_id,
        descricao=f"{body.tipo}: {(intim.texto or '')[:180]}",
        data_prazo=r["data_prazo"],
        data_fatal=r["data_prazo"],
        tipo=body.tipo,
        status="PENDENTE",
        responsavel_id=current_user.id,
        alertas_enviados=[],
    )
    db.add(deadline)
    await db.flush()

    intim.status = "TRIADA"
    intim.deadline_id = deadline.id
    await db.flush()

    return {
        "message": "Prazo criado a partir da intimação.",
        "deadline_id": str(deadline.id),
        "data_prazo": r["data_prazo"].isoformat(),
        "process_id": str(intim.process_id),
    }


@router.post("/{intimacao_id}/ignorar")
async def ignorar_publicacao(
    intimacao_id: str,
    current_user: User = Depends(require_role("ADVOGADO", "SOCIO", "ADMIN", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    intim = (await db.execute(
        select(Intimacao).where(
            Intimacao.id == uuid.UUID(intimacao_id),
            Intimacao.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if not intim:
        raise NotFoundError("Intimação", intimacao_id)
    intim.status = "IGNORADA"
    await db.flush()
    return {"message": "Intimação arquivada.", "id": intimacao_id}


@router.post("/varrer")
async def varrer_agora(
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    """Dispara a varredura do DJe agora, só para este escritório."""
    from app.services.dje_monitor import scan_publicacoes
    resumo = await scan_publicacoes(db, tenant_id=current_user.tenant_id, dias_retro=1)
    return {"message": "Varredura concluída.", **resumo}
