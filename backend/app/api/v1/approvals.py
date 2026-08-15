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
from app.models.agent_run import Approval, AgentRun
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
    # Fase 132 — SELECT ... FOR UPDATE: sem lock de linha, 2 requisições
    # concorrentes na mesma Approval (2 pessoas clicando aprovar/rejeitar
    # quase ao mesmo tempo) podiam ambas passar pela checagem de status
    # PENDENTE antes de qualquer uma commitar — a 2ª sobrescrevia a decisão
    # da 1ª silenciosamente, e ambas execute_approved_action/mark_rejected_action
    # rodavam. Com o lock, a 2ª requisição bloqueia até a 1ª commitar e então
    # vê o status já resolvido, falhando explicitamente em vez de duplicar a ação.
    result = await db.execute(
        select(Approval).where(
            Approval.id == uuid.UUID(approval_id),
            Approval.tenant_id == current_user.tenant_id,
        ).with_for_update()
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

    # Fase 183 — achado empírico: `AsyncSessionLocal` roda com autoflush=False
    # (app/db/base.py), então sem este flush explícito a mudança de status
    # acima só chegaria ao banco no commit final da request. Isso quebrava
    # qualquer 2º+ gate HITL cujo Approval não seja PETITION_*/CONTRACT_*
    # (únicos branches de `execute_approved_action` que já davam flush por
    # conta própria): `resume_chain_after_approval` → `create_approval_
    # from_state` relia (Fase 132/171) num SELECT WHERE status='PENDENTE'
    # pra checar duplicata — via sem o flush, ele via a linha ainda como
    # PENDENTE, concluía "já existe aprovação pra esse run" e não criava a
    # Approval do próximo gate. A chain ficava presa em AWAITING_APPROVAL
    # pra sempre, sem nenhuma Approval pendente pra resolver.
    await db.flush()

    # Fase 169.2 — precisa do AgentRun tanto pra retomar o resto da chain
    # na aprovação quanto pra fechar o status na rejeição (antes disso,
    # resolve_approval nunca olhava o AgentRun — um run rejeitado ficava
    # preso em AWAITING_APPROVAL pra sempre).
    # Fase 183 — SEM FOR UPDATE aqui de propósito: essa 1ª tentativa de fix
    # tentou travar a linha logo neste ponto e causou um deadlock real
    # (achado empírico) — no caminho de aprovação, `resume_chain_after_
    # approval` chama `execute_chain_step` pra cada passo seguinte, que
    # abre sua PRÓPRIA sessão/transação pra persistir o AgentStep; o INSERT
    # precisa de um lock de FK na linha pai (agent_runs), que ficaria
    # esperando este lock liberar — mas este lock só libera no commit
    # final desta função, que por sua vez está esperando aquele INSERT
    # terminar. Autotravamento. Ver a nota mais abaixo no branch de
    # rejeição pra onde o lock realmente entra.
    agent_run: AgentRun | None = None
    if approval.run_id:
        agent_run = await db.get(AgentRun, approval.run_id)

    # Executa a ação de forma síncrona (substitui a retomada por checkpoint LangGraph,
    # que era código morto). A ação crítica só ocorre AQUI, após decisão humana.
    from app.services.approval import execute_approved_action, mark_rejected_action
    execution: dict | None = None
    resume: dict | None = None
    if body.approved:
        execution = await execute_approved_action(db, approval, body.modifications)
        if agent_run:
            from app.services.chain_resume import resume_chain_after_approval
            resume = await resume_chain_after_approval(db, agent_run, approval, body.modifications)
    else:
        await mark_rejected_action(db, approval)
        if agent_run:
            # Fase 183 — achado empírico: SELECT ... FOR UPDATE só aqui, no
            # branch de rejeição (que nunca chama execute_chain_step, então
            # não corre o risco de deadlock explicado acima). O lock da
            # Fase 132 só cobre a linha Approval; a AgentRun nunca teve
            # lock nenhum, então um retry do Celery em voo (agent_tasks.py,
            # mutação de status/tokens_used/cost_usd no fim de `_run_async`)
            # podia commitar por cima desta rejeição — a Approval ficava
            # corretamente REJEITADO, mas a AgentRun acabava com o status
            # que o retry calculou (ex.: SUCCESS) em vez de FAILED. Re-lê a
            # linha travada (pode já ter mudado desde o SELECT sem lock
            # acima) antes de decidir.
            agent_run = (await db.execute(
                select(AgentRun).where(AgentRun.id == agent_run.id).with_for_update()
            )).scalar_one_or_none()
        if agent_run and agent_run.status not in ("SUCCESS", "FAILED", "CANCELADO"):
            agent_run.status = "FAILED"
            agent_run.error_message = f"Rejeitado: {body.rejection_reason}"
            agent_run.completed_at = datetime.now(timezone.utc)
            # Fase 174.7 — rejeição fecha a chain; sem isto requires_approval
            # ficava travado em True pra sempre num run já FAILED.
            agent_run.requires_approval = False

    action = "APROVADO" if body.approved else "REJEITADO"

    # Fase 174.8 — o AuditMiddleware genérico (app/core/middleware.py) já
    # grava uma linha pra todo POST que muda estado, mas só com
    # action=f"{method}:{path}" — nunca resource_type/resource_id/
    # old_value/new_value (todos ficam NULL). Decisão HITL é ato jurídico
    # (ver docstring da função) que merece rastro específico, no mesmo
    # padrão manual já usado em lgpd.py/system.py, complementando (não
    # substituindo) o registro genérico do middleware.
    from app.models.audit_log import AuditLog
    db.add(AuditLog(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        agent_name=agent_run.agent_name if agent_run else None,
        run_id=approval.run_id,
        action=f"HITL:{action}",
        resource_type="APPROVAL",
        resource_id=approval.id,
        old_value={"status": "PENDENTE"},
        new_value={"status": approval.status, "rejection_reason": approval.rejection_reason},
        success=True,
    ))
    await db.flush()

    return {
        "message": f"Aprovação {action} com sucesso",
        "approval_id": approval_id,
        "resolved_by": current_user.full_name,
        "execution": execution,
        "chain_resume": resume,
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
