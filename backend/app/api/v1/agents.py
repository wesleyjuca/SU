"""Endpoints para triggar, consultar e gerenciar execuções de agentes."""
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from typing import Any
import uuid

from app.db.base import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.agent_run import AgentRun
from app.agents.brain.context import AgentContext
from app.agents.brain.orchestrator import orchestrator_graph
from app.core.exceptions import NotFoundError

router = APIRouter(prefix="/agents", tags=["agents"])


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
    run_id = uuid.uuid4()
    ctx = AgentContext(
        run_id=run_id,
        triggered_by=current_user.id,
        task_type=body.task_type,
        task_input=body.task_input,
        priority=body.priority,
        process_id=uuid.UUID(body.process_id) if body.process_id else None,
        client_id=uuid.UUID(body.client_id) if body.client_id else None,
    )

    # Criar registro inicial no DB
    agent_run = AgentRun(
        id=run_id,
        agent_name="orchestration_agent",
        trigger_type="MANUAL",
        triggered_by=current_user.id,
        input_data=body.task_input,
        status="RUNNING",
    )
    db.add(agent_run)

    # Tentar enviar para Celery; fallback para background task se Celery indisponível
    try:
        from app.workers.tasks.agent_tasks import run_agent_task
        run_agent_task.delay(
            run_id=str(run_id),
            task_type=body.task_type,
            task_input=body.task_input,
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
    query = select(AgentRun).order_by(desc(AgentRun.started_at)).limit(limit)
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
    if not run:
        raise NotFoundError("AgentRun", run_id)
    return _run_to_response(run)


async def _run_agent_task(ctx: AgentContext, run_id: str):
    """Executa o grafo LangGraph em background."""
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
        await orchestrator_graph.ainvoke(state, config=config)
    except Exception as exc:
        import structlog
        log = structlog.get_logger()
        log.error("background_agent_failed", run_id=run_id, error=str(exc))


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
