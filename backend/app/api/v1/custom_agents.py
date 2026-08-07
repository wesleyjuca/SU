"""Propostas de agentes de IA customizados (Fase 140.2) — ADMIN propõe,
SUPERADMIN aprova. Registrado fora do bloco try/except que envolve
agents.router (app/api/v1/router.py): CRUD/aprovação não dependem do grafo
LangGraph — só a EXECUÇÃO de um agente aprovado passa por lá."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel, field_validator

from app.db.base import get_db
from app.dependencies import require_role
from app.models.user import User
from app.models.custom_agent import CustomAgent
from app.api.v1.rag import VALID_COLLECTIONS
from app.core.exceptions import NotFoundError

router = APIRouter(prefix="/custom-agents", tags=["custom-agents"])

STATUS_VALIDOS = {"PENDENTE", "APROVADO", "REJEITADO"}


class CustomAgentCreateRequest(BaseModel):
    name: str
    description: str
    system_prompt: str
    rag_collections: list[str] | None = None

    @field_validator("rag_collections")
    @classmethod
    def _validar_colecoes(cls, v):
        if v:
            invalidas = set(v) - VALID_COLLECTIONS
            if invalidas:
                raise ValueError(f"Coleções inválidas: {', '.join(sorted(invalidas))}")
        return v


class CustomAgentResolveRequest(BaseModel):
    approved: bool
    rejection_reason: str | None = None
    max_cost_usd_per_run: float | None = None


class CustomAgentResponse(BaseModel):
    id: str
    name: str
    description: str
    system_prompt: str
    rag_collections: list[str] | None
    status: str
    max_cost_usd_per_run: float
    created_by: str
    approved_by: str | None
    approved_at: str | None
    rejection_reason: str | None
    created_at: str

    @classmethod
    def from_row(cls, row: CustomAgent) -> "CustomAgentResponse":
        return cls(
            id=str(row.id), name=row.name, description=row.description,
            system_prompt=row.system_prompt, rag_collections=row.rag_collections,
            status=row.status, max_cost_usd_per_run=row.max_cost_usd_per_run,
            created_by=str(row.created_by),
            approved_by=str(row.approved_by) if row.approved_by else None,
            approved_at=row.approved_at.isoformat() if row.approved_at else None,
            rejection_reason=row.rejection_reason,
            created_at=row.created_at.isoformat(),
        )


@router.post("", status_code=201, response_model=CustomAgentResponse)
async def propose_custom_agent(
    body: CustomAgentCreateRequest,
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "SUPERADMIN")),
    db: AsyncSession = Depends(get_db),
):
    existe = (await db.execute(select(CustomAgent.id).where(CustomAgent.name == body.name))).scalar_one_or_none()
    if existe:
        raise HTTPException(status_code=409, detail="Já existe um agente customizado com esse nome.")
    row = CustomAgent(
        name=body.name, description=body.description, system_prompt=body.system_prompt,
        rag_collections=body.rag_collections, status="PENDENTE",
        created_by=current_user.id, tenant_id=current_user.tenant_id,
    )
    db.add(row)
    await db.flush()

    # Notifica todos os SUPERADMIN da plataforma — fan-out via create_batch,
    # mesmo padrão de app/services/notification.py (Fase 118).
    from app.services.notification import create_batch
    superadmin_ids = (await db.execute(select(User.id).where(User.role == "SUPERADMIN"))).scalars().all()
    if superadmin_ids:
        await create_batch(
            db, superadmin_ids,
            titulo=f"Novo agente customizado proposto: {row.name}",
            tipo="APROVACAO_PENDENTE",
            corpo=f"{current_user.full_name} propôs o agente '{row.name}'. Revise em Cérebro → Agentes Propostos.",
            priority="NORMAL",
            link="/admin/cerebro?aba=agentes-propostos",
        )
    return CustomAgentResponse.from_row(row)


@router.get("", response_model=list[CustomAgentResponse])
async def list_custom_agents(
    status: str | None = Query(None),
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "SUPERADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """SUPERADMIN vê todas as propostas (plataforma inteira, pra poder
    aprovar qualquer uma). Não-SUPERADMIN vê só as que ele mesmo criou,
    EXCETO agentes já APROVADOS — esses são plataforma-wide por decisão de
    desenho (mesmo padrão dos 19 agentes nativos), então ficam visíveis pra
    todo mundo independente de quem propôs."""
    query = select(CustomAgent)
    if status:
        if status not in STATUS_VALIDOS:
            raise HTTPException(status_code=400, detail=f"status inválido. Use: {', '.join(STATUS_VALIDOS)}")
        query = query.where(CustomAgent.status == status)
    if current_user.role != "SUPERADMIN" and status != "APROVADO":
        query = query.where(CustomAgent.created_by == current_user.id)
    rows = (await db.execute(query.order_by(desc(CustomAgent.created_at)))).scalars().all()
    return [CustomAgentResponse.from_row(r) for r in rows]


@router.get("/{agent_id}", response_model=CustomAgentResponse)
async def get_custom_agent(
    agent_id: str,
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "SUPERADMIN")),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(CustomAgent).where(CustomAgent.id == uuid.UUID(agent_id)))).scalar_one_or_none()
    if not row:
        raise NotFoundError("CustomAgent", agent_id)
    if current_user.role != "SUPERADMIN" and row.status != "APROVADO" and row.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Sem acesso a esta proposta.")
    return CustomAgentResponse.from_row(row)


@router.post("/{agent_id}/resolve", response_model=CustomAgentResponse)
async def resolve_custom_agent(
    agent_id: str,
    body: CustomAgentResolveRequest,
    current_user: User = Depends(require_role("SUPERADMIN")),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(CustomAgent).where(CustomAgent.id == uuid.UUID(agent_id)))).scalar_one_or_none()
    if not row:
        raise NotFoundError("CustomAgent", agent_id)
    if row.status != "PENDENTE":
        raise HTTPException(status_code=400, detail=f"Proposta já resolvida (status={row.status}).")

    row.status = "APROVADO" if body.approved else "REJEITADO"
    row.approved_by = current_user.id
    row.approved_at = datetime.now(timezone.utc)
    if not body.approved:
        row.rejection_reason = body.rejection_reason
    if body.approved and body.max_cost_usd_per_run is not None:
        row.max_cost_usd_per_run = body.max_cost_usd_per_run
    await db.flush()

    # Notifica o proponente do resultado.
    from app.services.notification import create_notification
    await create_notification(
        db, row.created_by,
        titulo=f"Agente '{row.name}' {'aprovado' if body.approved else 'rejeitado'}",
        tipo="SISTEMA",
        corpo=row.rejection_reason if not body.approved else "Já disponível para uso.",
        link="/agentes",
    )
    return CustomAgentResponse.from_row(row)
