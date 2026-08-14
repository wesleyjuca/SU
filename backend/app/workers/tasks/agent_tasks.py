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
    # Fase 174.4 — sem time_limit/soft_time_limit, uma chamada de LLM travada
    # (rede pendurada, provedor sem resposta) segurava o slot do worker
    # indefinidamente — nenhum outro run daquele worker avançava. Margem
    # acima do timeout interno (`asyncio.wait_for(..., timeout=300.0)` em
    # `_run_async`) pra ele ter a chance de agir primeiro e persistir
    # FAILED/"Agent timeout after 300s" antes do Celery matar a task à
    # força; `SoftTimeLimitExceeded` (perto de soft_time_limit) e o kill
    # duro (perto de time_limit) já caem no `except Exception`/retry
    # existente abaixo, mesmo padrão das outras tasks agendadas (Fase 147).
    soft_time_limit=330,
    time_limit=360,
)
def run_agent_task(self, run_id: str, task_type: str, task_input: dict,
                   triggered_by: str | None = None, process_id: str | None = None,
                   client_id: str | None = None, priority: str = "NORMAL"):
    """Executa um agente via orquestrador LangGraph dentro do Celery worker."""
    from app.workers.async_utils import run_worker_coro
    try:
        run_worker_coro(_run_async(
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
    from app.agents.brain.orchestrator import get_orchestrator_graph
    from app.models.agent_run import AgentRun, AgentStep
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        # Buscar o AgentRun existente
        result = await db.execute(select(AgentRun).where(AgentRun.id == uuid.UUID(run_id)))
        agent_run = result.scalar_one_or_none()

        _tenant = task_input.get("_tenant_id") if isinstance(task_input, dict) else None
        ctx = AgentContext(
            run_id=uuid.UUID(run_id),
            triggered_by=uuid.UUID(triggered_by) if triggered_by else None,
            task_type=task_type,
            task_input=task_input,
            priority=priority,
            tenant_id=uuid.UUID(_tenant) if _tenant else None,
            process_id=uuid.UUID(process_id) if process_id else None,
            client_id=uuid.UUID(client_id) if client_id else None,
        )

        # Fase 174.6 — Celery retenta `run_agent_task` do zero (self.retry())
        # em QUALQUER exceção, incluindo uma que só acontece DEPOIS de passos
        # anteriores já terem sido persistidos com sucesso (ex.: achado
        # CRÍTICO da Fase 173, corrigido na 174.1). Sem checar isso, cada
        # retry reexecutava a chain inteira desde o passo 0 — inclusive
        # passos com efeito colateral externo real (ex.: process_agent
        # buscando andamentos de verdade) — deixando `AgentStep` duplicado e
        # gastando chamadas externas à toa. Se já há passos persistidos e o
        # último terminou SUCCESS, retoma do próximo passo em vez de
        # reinvocar o grafo do zero — mesma unidade de trabalho
        # (`execute_chain_step`) que o orquestrador e `chain_resume.py` usam.
        existing_steps_result = await db.execute(
            select(AgentStep).where(AgentStep.run_id == uuid.UUID(run_id)).order_by(AgentStep.step_number)
        )
        existing_steps = existing_steps_result.scalars().all()
        resumable_retry = bool(existing_steps) and (existing_steps[-1].output_json or {}).get("_status") == "SUCCESS"

        started = datetime.utcnow()
        final_state: dict = {}
        try:
            if resumable_retry:
                log.info("agent_task_retry_resuming", run_id=run_id, from_step=existing_steps[-1].step_number + 1)
                final_state = await asyncio.wait_for(
                    _resume_chain_from_steps(ctx, task_type, task_input, existing_steps),
                    timeout=300.0,
                )
            else:
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
                orchestrator_graph = get_orchestrator_graph()
                final_state = await asyncio.wait_for(
                    orchestrator_graph.ainvoke(state, config=config),
                    timeout=300.0,
                )
            output = final_state.get("final_output") or {}
            # Fase 174.2 — antes só se decidia entre AWAITING_APPROVAL e
            # SUCCESS: se um passo da chain falhasse (node_execute_agent seta
            # state["error"], propagado agora por node_post_process em
            # final_output["error"] — ver orchestrator.py), o run inteiro
            # ainda era gravado como SUCCESS, escondendo a falha real.
            if final_state.get("pending_approval"):
                status = "AWAITING_APPROVAL"
                error_msg = None
            elif final_state.get("error") or output.get("error"):
                status = "FAILED"
                error_msg = final_state.get("error") or output.get("error")
            else:
                status = "SUCCESS"
                error_msg = None
        except asyncio.TimeoutError:
            status = "FAILED"
            output = {}
            error_msg = "Agent timeout after 300s"
            log.error("orchestration_timeout", run_id=run_id)
        except Exception as exc:
            status = "FAILED"
            output = {}
            error_msg = str(exc)
            log.error("orchestration_failed_in_worker", run_id=run_id, error=error_msg)

        # Trilha de tempo por chamada de LLM (Fase 113) — ctx.audit_events já é
        # preenchido por BaseAgent.run()/ask_llm(), só faltava persistir.
        output["_trace"] = ctx.audit_events

        # Atualizar status no DB
        if agent_run:
            # Se o run foi CANCELADO enquanto executava, não sobrescrever o
            # status final (senão um cancelamento "revive" como SUCCESS/AWAITING).
            await db.refresh(agent_run)
            canceled = agent_run.status == "CANCELADO"
            if not canceled:
                agent_run.status = status
            agent_run.output_data = output
            agent_run.error_message = error_msg
            agent_run.completed_at = datetime.utcnow()
            agent_run.duration_ms = int((datetime.utcnow() - started).total_seconds() * 1000)
            agent_run.tokens_used = ctx.total_tokens
            from decimal import Decimal
            agent_run.cost_usd = Decimal(str(ctx.total_cost_usd)) if ctx.total_cost_usd else None
            agent_run.requires_approval = ctx.requires_approval
            # HITL: cria o Approval PENDENTE na mesma transação (não p/ run cancelado)
            if not canceled and status == "AWAITING_APPROVAL":
                from app.services.approval import create_approval_from_state
                await create_approval_from_state(db, agent_run, final_state)
            await db.commit()
            status = agent_run.status  # reflete o status realmente persistido

        # Publicar evento WebSocket
        try:
            from app.api.v1.ws import publish_event
            if triggered_by:
                await publish_event(triggered_by, "AGENT_RUN_COMPLETED", {
                    "run_id": run_id,
                    "status": status,
                    "task_type": task_type,
                    "agent_name": agent_run.agent_name if agent_run else None,
                })
        except Exception:
            pass

        log.info("agent_task_done", run_id=run_id, status=status)


async def _resume_chain_from_steps(ctx, task_type: str, task_input: dict, existing_steps: list) -> dict:
    """Fase 174.6 — retoma uma chain a partir do próximo passo não executado,
    reconstruindo `agent_results` dos passos já persistidos em vez de
    reexecutá-los. Devolve um dict no mesmo formato que
    `orchestrator_graph.ainvoke(...)` devolveria (`final_output`/
    `pending_approval`/`error`), pra `_run_async` decidir status e persistir
    sem precisar saber qual dos dois caminhos rodou."""
    from app.agents.brain.orchestrator import execute_chain_step
    from app.agents.brain.router import get_chain
    from app.agents.brain.chain_projectors import project_output
    from app.agents.base.result import AgentResult, AgentStatus

    chain = get_chain(task_type, task_input)
    agent_results = [
        AgentResult(
            status=AgentStatus((s.output_json or {}).get("_status", "SUCCESS")),
            agent_name=s.step_name,
            output={k: v for k, v in (s.output_json or {}).items() if k != "_status"},
            duration_ms=s.duration_ms or 0,
        )
        for s in existing_steps
    ]
    last_step = existing_steps[-1]
    next_index = last_step.step_number + 1

    if next_index >= len(chain):
        # A tentativa anterior já tinha concluído todos os passos da chain —
        # só faltou o commit final do AgentRun antes do worker morrer/retry.
        return {
            "final_output": {
                "run_id": str(ctx.run_id),
                "task_type": ctx.task_type,
                "agents_invoked": ctx.agents_invoked,
                "total_tokens": ctx.total_tokens,
                "total_cost_usd": ctx.total_cost_usd,
                "results": [r.to_dict() for r in agent_results],
            },
            "pending_approval": None,
            "error": None,
            "agent_results": agent_results,
        }

    ctx.task_input = project_output(last_step.step_name, chain[next_index], agent_results[-1], ctx)

    for i in range(next_index, len(chain)):
        result = await execute_chain_step(ctx, chain, i)
        agent_results.append(result)

        if result.status == AgentStatus.FAILED:
            return {"final_output": None, "pending_approval": None, "error": result.error, "agent_results": agent_results}

        if result.status == AgentStatus.AWAITING_APPROVAL:
            # `agent_results` precisa estar presente pro caller
            # (create_approval_from_state, ver app/services/approval.py)
            # conseguir montar `ai_suggestion` a partir do último resultado.
            return {"final_output": None, "pending_approval": result.approval_required, "error": None, "agent_results": agent_results}

        next_i = i + 1
        if next_i < len(chain):
            ctx.task_input = project_output(chain[i], chain[next_i], result, ctx)

    return {
        "final_output": {
            "run_id": str(ctx.run_id),
            "task_type": ctx.task_type,
            "agents_invoked": ctx.agents_invoked,
            "total_tokens": ctx.total_tokens,
            "total_cost_usd": ctx.total_cost_usd,
            "results": [r.to_dict() for r in agent_results],
        },
        "pending_approval": None,
        "error": None,
        "agent_results": agent_results,
    }
