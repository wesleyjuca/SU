"""Fila de aprovação humana — HITL (Human-in-the-Loop)."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from datetime import datetime, timezone
import uuid

from app.db.base import get_db
from app.dependencies import get_current_user, require_role
from app.models.user import User
from app.models.agent_run import Approval
from app.core.exceptions import NotFoundError, ValidationError

router = APIRouter(prefix="/approvals", tags=["approvals"])


class ApprovalResponse(BaseModel):
    id: str
    run_id: str | None
    tipo: str | None
    titulo: str
    descricao: str | None
    ai_suggestion: dict | None
    prioridade: str
    status: str
    assignee_id: str | None
    expires_at: str | None
    created_at: str
    resolved_at: str | None


class ResolveApprovalRequest(BaseModel):
    approved: bool
    rejection_reason: str | None = None
    modifications: dict | None = None  # modificações do usuário à sugestão da IA


@router.get("", response_model=list[ApprovalResponse])
async def list_approvals(
    status: str = "PENDENTE",
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lista aprovações pendentes para o usuário atual."""
    query = (
        select(Approval)
        .where(
            Approval.status == status,
            Approval.tenant_id == current_user.tenant_id,
        )
        .order_by(
            Approval.prioridade.desc(),
            desc(Approval.created_at),
        )
        .limit(limit)
    )
    result = await db.execute(query)
    approvals = result.scalars().all()
    return [_to_response(a) for a in approvals]


@router.get("/{approval_id}", response_model=ApprovalResponse)
async def get_approval(
    approval_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Approval).where(
            Approval.id == uuid.UUID(approval_id),
            Approval.tenant_id == current_user.tenant_id,
        )
    )
    approval = result.scalar_one_or_none()
    if not approval:
        raise NotFoundError("Approval", approval_id)
    return _to_response(approval)


@router.post("/{approval_id}/resolve")
async def resolve_approval(
    approval_id: str,
    body: ResolveApprovalRequest,
    # Decisão HITL é ato jurídico: restrita a advogado/sócio/admin (SUPERADMIN passa).
    current_user: User = Depends(require_role("ADVOGADO", "SOCIO", "ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """
    Aprova ou rejeita uma sugestão da IA.
    Regra: rejeição EXIGE justificativa.
    Após resolução, retoma o workflow LangGraph se aplicável.
    """
    result = await db.execute(
        select(Approval).where(
            Approval.id == uuid.UUID(approval_id),
            Approval.tenant_id == current_user.tenant_id,
        )
    )
    approval = result.scalar_one_or_none()
    if not approval:
        raise NotFoundError("Approval", approval_id)

    if approval.status != "PENDENTE":
        raise ValidationError(f"Aprovação já resolvida com status: {approval.status}")

    if not body.approved and not body.rejection_reason:
        raise ValidationError("Justificativa obrigatória para rejeição")

    approval.status = "APROVADO" if body.approved else "REJEITADO"
    approval.approved_by = current_user.id
    approval.rejection_reason = body.rejection_reason
    approval.resolved_at = datetime.now(timezone.utc)

    # Executa a ação de forma síncrona (substitui a retomada por checkpoint LangGraph,
    # que era código morto). A ação crítica só ocorre AQUI, após decisão humana.
    from app.services.approval_service import execute_approved_action, mark_rejected_action
    execution: dict | None = None
    if body.approved:
        execution = await execute_approved_action(db, approval, body.modifications)
    else:
        await mark_rejected_action(db, approval)

    await db.flush()

    action = "APROVADO" if body.approved else "REJEITADO"
    return {
        "message": f"Aprovação {action} com sucesso",
        "approval_id": approval_id,
        "resolved_by": current_user.full_name,
        "execution": execution,
    }


def _to_response(a: Approval) -> ApprovalResponse:
    return ApprovalResponse(
        id=str(a.id),
        run_id=str(a.run_id) if a.run_id else None,
        tipo=a.tipo,
        titulo=a.titulo,
        descricao=a.descricao,
        ai_suggestion=a.ai_suggestion,
        prioridade=a.prioridade,
        status=a.status,
        assignee_id=str(a.assignee_id) if a.assignee_id else None,
        expires_at=a.expires_at.isoformat() if a.expires_at else None,
        created_at=a.created_at.isoformat(),
        resolved_at=a.resolved_at.isoformat() if a.resolved_at else None,
    )
