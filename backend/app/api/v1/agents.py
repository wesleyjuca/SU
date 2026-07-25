"""Endpoints para triggar, consultar e gerenciar execuções de agentes."""
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from typing import Any
import uuid

from app.db.base import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.agent_run import AgentRun
from app.models.client import Client
from app.models.process import LegalProcess
from app.agents.brain.context import AgentContext
from app.agents.brain.orchestrator import get_orchestrator_graph
from app.core.exceptions import NotFoundError

router = APIRouter(prefix="/agents", tags=["agents"])


async def _validar_pertence_ao_tenant(
    db: AsyncSession, tenant_id, process_id: uuid.UUID | None, client_id: uuid.UUID | None,
) -> None:
    """Garante que process_id/client_id (se informados) pertencem ao tenant do
    usuário — sem isso, um agente disparado manualmente pode gravar/notificar
    em processo/cliente de OUTRO escritório (ex.: process_agent.poll_process)."""
    if process_id:
        existe = (await db.execute(
            select(LegalProcess.id).where(LegalProcess.id == process_id, LegalProcess.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if not existe:
            raise HTTPException(status_code=404, detail="Processo não encontrado.")
    if client_id:
        existe = (await db.execute(
            select(Client.id).where(Client.id == client_id, Client.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if not existe:
            raise HTTPException(status_code=404, detail="Cliente não encontrado.")


class TriggerAgentRequest(BaseModel):
    task_type: str
    task_input: dict[str, Any] = {}
    process_id: str | None = None
    client_id: str | None = None
    priority: str = "NORMAL"


class AgentRunResponse(BaseModel):
    run_id: str
    agent_name: str
    status: str
    started_at: str
    completed_at: str | None
    tokens_used: int | None
    cost_usd: float | None
    output: dict | None
    error_message: str | None
    requires_approval: bool


@router.post("/trigger", status_code=202)
async def trigger_agent(
    body: TriggerAgentRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Dispara uma tarefa para o orquestrador. A execução é assíncrona.
    Retorna imediatamente com o run_id para acompanhamento.
    """
    # Bloqueio suave: se o usuário atingiu o teto mensal de IA, rejeita (429).
    from app.services.ai_budget import enforce_budget
    await enforce_budget(db, current_user.id, current_user.tenant_id)

    process_uuid = uuid.UUID(body.process_id) if body.process_id else None
    client_uuid = uuid.UUID(body.client_id) if body.client_id else None
    await _validar_pertence_ao_tenant(db, current_user.tenant_id, process_uuid, client_uuid)

    run_id = uuid.uuid4()
    # Inject tenant_id so agents can scope DB writes correctly
    task_input = {**body.task_input, "_tenant_id": str(current_user.tenant_id)} if current_user.tenant_id else body.task_input
    ctx = AgentContext(
        run_id=run_id,
        triggered_by=current_user.id,
        task_type=body.task_type,
        task_input=task_input,
        priority=body.priority,
        tenant_id=current_user.tenant_id,
        process_id=process_uuid,
        client_id=client_uuid,
    )

    # Criar registro inicial no DB
    agent_run = AgentRun(
        id=run_id,
        agent_name="orchestration_agent",
        trigger_type="MANUAL",
        triggered_by=current_user.id,
        input_data=body.task_input,
        status="RUNNING",
        tenant_id=current_user.tenant_id,
    )
    db.add(agent_run)

    # Tentar enviar para Celery; fallback para background task se Celery indisponível
    try:
        from app.workers.tasks.agent_tasks import run_agent_task
        run_agent_task.delay(
            run_id=str(run_id),
            task_type=body.task_type,
            task_input=task_input,
            triggered_by=str(current_user.id),
            process_id=body.process_id,
            client_id=body.client_id,
            priority=body.priority,
        )
    except Exception:
        background_tasks.add_task(_run_agent_task, ctx, str(run_id))

    return {
        "run_id": str(run_id),
        "status": "RUNNING",
        "message": f"Tarefa '{body.task_type}' iniciada. Acompanhe pelo run_id.",
    }


@router.get("/runs", response_model=list[AgentRunResponse])
async def list_runs(
    agent_name: str | None = None,
    status: str | None = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(AgentRun).where(
        AgentRun.tenant_id == current_user.tenant_id
    ).order_by(desc(AgentRun.started_at)).limit(limit)
    if agent_name:
        query = query.where(AgentRun.agent_name == agent_name)
    if status:
        query = query.where(AgentRun.status == status)

    result = await db.execute(query)
    runs = result.scalars().all()
    return [_run_to_response(r) for r in runs]


@router.get("/runs/{run_id}", response_model=AgentRunResponse)
async def get_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AgentRun).where(AgentRun.id == uuid.UUID(run_id)))
    run = result.scalar_one_or_none()
    if not run or run.tenant_id != current_user.tenant_id:
        raise NotFoundError("AgentRun", run_id)
    return _run_to_response(run)


# Estados finais — uma run nesses status não pode mais ser cancelada
_TERMINAL_STATES = {"SUCCESS", "FAILED", "CANCELADO"}


@router.post("/runs/{run_id}/cancel", response_model=AgentRunResponse)
async def cancel_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancela uma execução em andamento (marca CANCELADO).

    Cooperativo: encerra o registro e para o polling do frontend. Não aborta uma
    chamada de IA já em voo — o resultado, se chegar, é ignorado pela run cancelada.
    """
    from fastapi import HTTPException
    from datetime import datetime

    result = await db.execute(select(AgentRun).where(AgentRun.id == uuid.UUID(run_id)))
    run = result.scalar_one_or_none()
    if not run or run.tenant_id != current_user.tenant_id:
        raise NotFoundError("AgentRun", run_id)
    if run.status in _TERMINAL_STATES:
        raise HTTPException(status_code=409, detail=f"Execução já finalizada ({run.status}).")

    run.status = "CANCELADO"
    run.completed_at = datetime.utcnow()
    if not run.error_message:
        run.error_message = "Cancelado pelo usuário"
    await db.commit()
    await db.refresh(run)
    return _run_to_response(run)


async def _run_agent_task(ctx: AgentContext, run_id: str):
    """Executa o grafo LangGraph em background e atualiza o AgentRun."""
    from app.db.base import AsyncSessionLocal
    from app.models.agent_run import AgentRun as AR
    from datetime import datetime
    from decimal import Decimal
    import structlog
    log = structlog.get_logger()

    started = datetime.utcnow()
    status = "FAILED"
    output: dict = {}
    error_msg: str | None = None

    try:
        state = {
            "context": ctx,
            "route": "",
            "agent_results": [],
            "pending_approval": None,
            "final_output": None,
            "error": None,
            "done": False,
        }
        config = {"configurable": {"thread_id": run_id}}
        final_state = await get_orchestrator_graph().ainvoke(state, config=config)
        status = "AWAITING_APPROVAL" if final_state.get("pending_approval") else "SUCCESS"
        output = final_state.get("final_output") or {}
    except Exception as exc:
        log.error("background_agent_failed", run_id=run_id, error=str(exc))
        error_msg = str(exc)
        final_state = {}

    elapsed_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(AR).where(AR.id == uuid.UUID(run_id)))
            agent_run = result.scalar_one_or_none()
            if agent_run:
                agent_run.status = status
                agent_run.output_data = output
                agent_run.error_message = error_msg
                agent_run.completed_at = datetime.utcnow()
                agent_run.duration_ms = elapsed_ms
                agent_run.tokens_used = ctx.total_tokens or None
                agent_run.cost_usd = Decimal(str(ctx.total_cost_usd)) if ctx.total_cost_usd else None
                agent_run.requires_approval = ctx.requires_approval
                # HITL: cria o Approval PENDENTE na mesma transação
                if status == "AWAITING_APPROVAL":
                    from app.services.approval_service import create_approval_from_state
                    await create_approval_from_state(db, agent_run, final_state)
                await db.commit()
        except Exception as exc:
            log.error("agent_run_update_failed", run_id=run_id, error=str(exc))


def _run_to_response(run: AgentRun) -> AgentRunResponse:
    return AgentRunResponse(
        run_id=str(run.id),
        agent_name=run.agent_name,
        status=run.status,
        started_at=run.started_at.isoformat(),
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        tokens_used=run.tokens_used,
        cost_usd=float(run.cost_usd) if run.cost_usd else None,
        output=run.output_data,
        error_message=run.error_message,
        requires_approval=run.requires_approval,
    )
