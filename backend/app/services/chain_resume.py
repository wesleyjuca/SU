"""Fase 169.2 — retomada de chains após aprovação humana.

`resolve_approval` (`app/api/v1/approvals.py`) roda numa request totalmente
separada da execução original do orquestrador — o grafo LangGraph já
terminou (`awaiting_approval → END`, ver `orchestrator.py`) quando o humano
aprova. Retomar os passos restantes de uma chain não reinvoca o grafo (o
`MemorySaver` configurado nele não sobrevive entre processos/requests,
mesma limitação já documentada em `app/services/approval.py`) — em vez
disso, reconstrói o `AgentContext` a partir do que ficou persistido
(`AgentRun.task_type`/`process_id`/`client_id`, Fase 169.2) e roda os
passos restantes com `execute_chain_step`, a mesma unidade de trabalho que
o orquestrador usa internamente.

Fase 171 — se um passo retomado também pedir aprovação humana (2º gate na
mesma chain), a retomada cria uma nova Approval e pausa de novo em vez de
falhar; `resolve_approval` já chama esta função incondicionalmente a cada
aprovação, então um 3º gate (ou mais) funciona pelo mesmo mecanismo, sem
código adicional.
"""
from datetime import datetime
from decimal import Decimal

import structlog
from sqlalchemy import select

from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.chain_projectors import project_output
from app.agents.brain.context import AgentContext
from app.agents.brain.orchestrator import execute_chain_step
from app.agents.brain.router import get_chain
from app.models.agent_run import AgentRun
from app.workers.task_lock import TaskLock

log = structlog.get_logger()


async def resume_chain_after_approval(db, agent_run, approval, modifications: dict | None = None) -> dict:
    """Roda os passos restantes de uma chain depois que o passo protegido
    por HITL foi aprovado. Auto-protegido: no-op (`resumed=False`) se o run
    não tem `task_type` persistido (runs anteriores à Fase 169.2), se já
    está num estado terminal (ex.: cancelado enquanto a aprovação estava
    pendente), ou se o gate era o último passo da chain — o call site
    (`resolve_approval`) não precisa checar nenhuma dessas condições antes
    de chamar.
    """
    if not agent_run or not agent_run.task_type:
        return {"resumed": False, "reason": "run sem task_type persistido (anterior à Fase 169.2)"}
    if agent_run.status == "CANCELADO":
        return {"resumed": False, "reason": "run cancelado"}

    chain = get_chain(agent_run.task_type, agent_run.input_data or {})

    from sqlalchemy import select
    from app.models.agent_run import AgentStep

    steps = (await db.execute(
        select(AgentStep).where(AgentStep.run_id == agent_run.id).order_by(AgentStep.step_number)
    )).scalars().all()
    if not steps:
        return {"resumed": False, "reason": "run sem AgentStep gravado"}

    last_step = steps[-1]
    next_index = last_step.step_number + 1

    if next_index >= len(chain):
        # Gate era o último passo — nada a retomar, só fecha o run se ainda
        # não estiver num estado terminal (sem isso, aprovar o gate de uma
        # chain de 1-passo-com-gate deixaria o run preso em
        # AWAITING_APPROVAL pra sempre).
        if agent_run.status not in ("SUCCESS", "FAILED", "CANCELADO"):
            agent_run.status = "SUCCESS"
            agent_run.completed_at = datetime.utcnow()
        return {"resumed": False, "reason": "gate era o último passo da chain"}

    lock = TaskLock(f"agent_run_resume:{agent_run.id}", ttl_seconds=300)
    if not await lock.acquire():
        log.warning("chain_resume_lock_busy", run_id=str(agent_run.id))
        return {"resumed": False, "reason": "retomada já em andamento"}

    try:
        return await _run_remaining_steps(db, agent_run, chain, last_step, next_index, modifications)
    finally:
        await lock.release()


async def _run_remaining_steps(db, agent_run, chain, last_step, next_index, modifications) -> dict:
    gated_output = dict(last_step.output_json or {})
    gated_output.pop("_status", None)
    if modifications:
        # Edição humana na hora de aprovar deve valer pros passos seguintes
        # da chain, não só pro artefato salvo — `execute_approved_action`
        # (app/services/approval.py) já aplica `modifications` no
        # Document/Petition/Contract; aqui é o mesmo dado alimentando o
        # próximo passo do orquestrador, pra não perder a edição a caminho.
        gated_output.update(modifications)

    gated_result = AgentResult(status=AgentStatus.SUCCESS, agent_name=last_step.step_name, output=gated_output)

    ctx = AgentContext(
        run_id=agent_run.id,
        triggered_by=agent_run.triggered_by,
        task_type=agent_run.task_type,
        task_input=dict(agent_run.input_data or {}),
        tenant_id=agent_run.tenant_id,
        process_id=agent_run.process_id,
        client_id=agent_run.client_id,
    )
    ctx.task_input = project_output(last_step.step_name, chain[next_index], gated_result, ctx)

    results = []
    for i in range(next_index, len(chain)):
        # Fase 176.5 — achado da Fase 175: `resume_chain_after_approval` só
        # checava CANCELADO 1x, antes deste loop começar — um cancelamento
        # cooperativo (`POST /agents/runs/{id}/cancel`, endpoint documenta a
        # intenção: "não aborta uma chamada de IA já em voo") pedido
        # enquanto a chain retomada estava entre passos nunca era observado
        # aqui, e o loop terminava sobrescrevendo CANCELADO com
        # SUCCESS/FAILED/AWAITING_APPROVAL. Query direta na coluna (não
        # `db.refresh(agent_run)`) pra enxergar o commit de outra
        # sessão/request sob READ COMMITTED sem tocar nos atributos já
        # carregados no objeto ORM em memória.
        current_status = (await db.execute(
            select(AgentRun.status).where(AgentRun.id == agent_run.id)
        )).scalar_one_or_none()
        if current_status == "CANCELADO":
            log.info("chain_resume_cancelled_mid_loop", run_id=str(agent_run.id), next_step=i)
            _accumulate_usage(agent_run, ctx)
            await db.commit()
            return {"resumed": True, "final_status": "CANCELADO", "steps_run": len(results)}

        result = await execute_chain_step(ctx, chain, i)
        results.append(result)

        if result.status == AgentStatus.FAILED:
            agent_run.status = "FAILED"
            agent_run.error_message = result.error
            agent_run.completed_at = datetime.utcnow()
            # Fase 174.7 — requires_approval fica True desde que o 1º gate
            # pausou a chain (setado em agent_tasks.py::_run_async); se o
            # passo retomado depois FALHA, a chain já terminou — sem isso o
            # flag ficava travado em True pra sempre num run já FAILED.
            agent_run.requires_approval = False
            _accumulate_usage(agent_run, ctx)
            await db.commit()
            return {"resumed": True, "final_status": "FAILED", "steps_run": len(results)}

        if result.status == AgentStatus.AWAITING_APPROVAL:
            # Fase 171 — um 2º (ou N-ésimo) gate HITL na mesma chain: cria
            # uma nova Approval reaproveitando create_approval_from_state
            # (mesma função que o orquestrador usa pro 1º gate), montando
            # um "final_state" mínimo no formato que ela já espera. A
            # idempotência dela (relaxada na Fase 171 pra checar só
            # Approval PENDENTE) não barra isso: o gate anterior já foi
            # resolvido, então não conta mais como pendência em aberto.
            from app.services.approval import create_approval_from_state
            pseudo_state = {"pending_approval": result.approval_required or {}, "agent_results": [result]}
            await create_approval_from_state(db, agent_run, pseudo_state)

            agent_run.status = "AWAITING_APPROVAL"
            agent_run.requires_approval = True
            _accumulate_usage(agent_run, ctx)
            await db.commit()
            await _publish_completion(agent_run)
            return {"resumed": True, "final_status": "AWAITING_APPROVAL", "steps_run": len(results)}

        next_i = i + 1
        if next_i < len(chain):
            ctx.task_input = project_output(chain[i], chain[next_i], result, ctx)

    agent_run.status = "SUCCESS"
    agent_run.completed_at = datetime.utcnow()
    # Fase 174.7 — mesma correção do branch FAILED acima: a chain terminou
    # com sucesso, não precisa mais de atenção humana.
    agent_run.requires_approval = False
    agent_run.output_data = {
        "run_id": str(agent_run.id),
        "task_type": agent_run.task_type,
        "agents_invoked": ctx.agents_invoked,
        "total_tokens": ctx.total_tokens,
        "total_cost_usd": ctx.total_cost_usd,
        "results": [r.to_dict() for r in results],
    }
    _accumulate_usage(agent_run, ctx)
    await db.commit()

    await _publish_completion(agent_run)
    return {"resumed": True, "final_status": "SUCCESS", "steps_run": len(results)}


def _accumulate_usage(agent_run, ctx: AgentContext) -> None:
    """Soma o consumo dos passos retomados ao que já estava gravado dos
    passos pré-gate (o `AgentRun.tokens_used`/`cost_usd` originais já
    refletem os passos até o gate — ver `_run_agent_task`/`_run_async`)."""
    agent_run.tokens_used = (agent_run.tokens_used or 0) + ctx.total_tokens
    added_cost = Decimal(str(ctx.total_cost_usd)) if ctx.total_cost_usd else Decimal("0")
    agent_run.cost_usd = (agent_run.cost_usd or Decimal("0")) + added_cost


async def _publish_completion(agent_run) -> None:
    if not agent_run.triggered_by:
        return
    try:
        from app.api.v1.ws import publish_event
        await publish_event(str(agent_run.triggered_by), "AGENT_RUN_COMPLETED", {
            "run_id": str(agent_run.id),
            "status": agent_run.status,
            "task_type": agent_run.task_type,
            "agent_name": agent_run.agent_name,
        })
    except Exception as exc:
        log.warning("chain_resume_ws_publish_failed", run_id=str(agent_run.id), error=str(exc))
