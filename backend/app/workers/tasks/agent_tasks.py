"""Celery tasks para execução de agentes em background."""
import asyncio
import uuid
from datetime import datetime

import structlog

from app.workers.worker import celery_app

log = structlog.get_logger()


@celery_app.task(
    name="agent_tasks.run_agent",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def run_agent_task(self, run_id: str, task_type: str, task_input: dict,
                   triggered_by: str | None = None, process_id: str | None = None,
                   client_id: str | None = None, priority: str = "NORMAL"):
    """Executa um agente via orquestrador LangGraph dentro do Celery worker."""
    try:
        asyncio.run(_run_async(
            run_id=run_id,
            task_type=task_type,
            task_input=task_input,
            triggered_by=triggered_by,
            process_id=process_id,
            client_id=client_id,
            priority=priority,
        ))
    except Exception as exc:
        log.error("celery_agent_task_failed", run_id=run_id, error=str(exc))
        raise self.retry(exc=exc)


async def _run_async(
    run_id: str,
    task_type: str,
    task_input: dict,
    triggered_by: str | None,
    process_id: str | None,
    client_id: str | None,
    priority: str,
):
    """Lógica assíncrona do worker: monta contexto, executa grafo, persiste resultado."""
    from app.db.base import AsyncSessionLocal
    from app.agents.brain.context import AgentContext
    from app.agents.brain.orchestrator import orchestrator_graph
    from app.models.agent_run import AgentRun
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        # Buscar o AgentRun existente
        result = await db.execute(select(AgentRun).where(AgentRun.id == uuid.UUID(run_id)))
        agent_run = result.scalar_one_or_none()

        ctx = AgentContext(
            run_id=uuid.UUID(run_id),
            triggered_by=uuid.UUID(triggered_by) if triggered_by else None,
            task_type=task_type,
            task_input=task_input,
            priority=priority,
            process_id=uuid.UUID(process_id) if process_id else None,
            client_id=uuid.UUID(client_id) if client_id else None,
        )

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

        started = datetime.utcnow()
        try:
            final_state = await orchestrator_graph.ainvoke(state, config=config)
            status = "AWAITING_APPROVAL" if final_state.get("pending_approval") else "SUCCESS"
            output = final_state.get("final_output") or {}
            error_msg = None
        except Exception as exc:
            status = "FAILED"
            output = {}
            error_msg = str(exc)
            log.error("orchestration_failed_in_worker", run_id=run_id, error=error_msg)

        # Atualizar status no DB
        if agent_run:
            agent_run.status = status
            agent_run.output_data = output
            agent_run.error_message = error_msg
            agent_run.completed_at = datetime.utcnow()
            agent_run.duration_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
            agent_run.tokens_used = ctx.total_tokens
            from decimal import Decimal
            agent_run.cost_usd = Decimal(str(ctx.total_cost_usd)) if ctx.total_cost_usd else None
            agent_run.requires_approval = ctx.requires_approval
            await db.commit()

        # Publicar evento WebSocket
        try:
            from app.api.v1.ws import publish_event
            if triggered_by:
                await publish_event(triggered_by, "AGENT_RUN_COMPLETED", {
                    "run_id": run_id,
                    "status": status,
                    "task_type": task_type,
                })
        except Exception:
            pass

        log.info("agent_task_done", run_id=run_id, status=status)
