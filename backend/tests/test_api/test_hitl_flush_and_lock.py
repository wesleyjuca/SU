"""Fase 186 — reconfirmação via HTTP real (app.main:app + Postgres real,
mesmo fixture `client`/`auth_headers` de test_google_docs_sheets_export.py)
dos 2 bugs mais graves achados na Fase 183 e corrigidos na Fase 184:

1. `resolve_approval` (approvals.py) precisa de `db.flush()` explícito
   após mutar `Approval.status` — sem isso (`AsyncSessionLocal` roda com
   `autoflush=False`), qualquer 2º+ gate HITL de uma chain cujo tipo de
   Approval não seja PETITION_*/CONTRACT_* travava em AWAITING_APPROVAL
   pra sempre (a checagem de idempotência via a linha ainda como
   PENDENTE).
2. `AgentRun` precisa de `SELECT ... FOR UPDATE` no branch de rejeição de
   `resolve_approval` e na persistência final de `agent_tasks.py::
   _run_async` — sem isso, um retry do Celery em voo podia commitar por
   cima de uma rejeição humana já commitada.

Até a Fase 185 nenhum teste commitado batia Postgres real pra esses 2
bugs — a "verificação empírica" da Fase 184 ficou só num script de
scratchpad, nunca virou teste (achado da Fase 186). Este arquivo fecha
essa lacuna."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.models.agent_run import AgentRun, AgentStep, Approval

pytestmark = pytest.mark.anyio

AFJ_TENANT = uuid.UUID("982f3011-fa9c-4cdc-8cc3-cf1f3376708c")


def _patch_orchestrator(monkeypatch):
    import app.agents.brain.orchestrator as orch
    from app.agents.base.result import AgentResult, AgentStatus

    route_results = {
        "jurisprudence_agent": AgentResult(status=AgentStatus.AWAITING_APPROVAL, agent_name="jurisprudence_agent", output={"nota": "passo2"}, approval_required={"tipo": "GATE2"}),
        "strategy_agent": AgentResult(status=AgentStatus.AWAITING_APPROVAL, agent_name="strategy_agent", output={"nota": "passo3"}, approval_required={"tipo": "GATE3"}),
        "crm_agent": AgentResult(status=AgentStatus.SUCCESS, agent_name="crm_agent", output={"nota": "passo4 final"}),
    }

    def _resolve(route):
        result = route_results[route]

        class _FakeAgent:
            def __init__(self, db=None, redis=None, qdrant=None):
                pass

            async def run(self, ctx):
                return result
        return _FakeAgent

    monkeypatch.setattr(orch, "resolve_agent_class", _resolve)


async def test_gate_generico_3_passos_completa_ate_success(client, auth_headers, monkeypatch):
    """Fase 183(a) — sem o flush, o 2º gate (GATE2, tipo genérico — não
    PETITION_*/CONTRACT_*) travava a chain em AWAITING_APPROVAL pra
    sempre, sem nenhuma Approval pendente pra resolver."""
    _patch_orchestrator(monkeypatch)

    async with AsyncSessionLocal() as db:
        run = AgentRun(
            id=uuid.uuid4(), agent_name="orchestration_agent", trigger_type="CHAINED",
            input_data={}, status="AWAITING_APPROVAL", task_type="new_process_intake",
            tenant_id=AFJ_TENANT, tokens_used=10, cost_usd=Decimal("0.001"),
            requires_approval=True,
        )
        db.add(run)
        await db.flush()
        db.add(AgentStep(run_id=run.id, step_number=0, step_name="process_agent", output_json={"_status": "SUCCESS"}))
        appr1 = Approval(id=uuid.uuid4(), run_id=run.id, tipo="GATE1", titulo="Gate 1", status="PENDENTE", tenant_id=AFJ_TENANT)
        db.add(appr1)
        await db.commit()
        run_id, approval_id = run.id, appr1.id

    try:
        for i in range(3):
            resp = await client.post(f"/api/v1/approvals/{approval_id}/resolve", json={"approved": True}, headers=auth_headers)
            assert resp.status_code == 200, resp.text
            if i < 2:
                r = await client.get("/api/v1/approvals?status=PENDENTE", headers=auth_headers)
                pend = [a for a in r.json() if a["run_id"] == str(run_id)]
                assert len(pend) == 1, (
                    f"gate {i+1}: esperava exatamente 1 Approval pendente pro próximo passo, "
                    f"achou {len(pend)} — sem o flush (Fase 184.1) a chain trava aqui"
                )
                approval_id = pend[0]["id"]

        async with AsyncSessionLocal() as db:
            run = await db.get(AgentRun, run_id)
            steps = (await db.execute(select(AgentStep).where(AgentStep.run_id == run_id).order_by(AgentStep.step_number))).scalars().all()
            assert run.status == "SUCCESS"
            assert not run.requires_approval
            assert [s.step_number for s in steps] == [0, 1, 2, 3]
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(AgentStep.__table__.delete().where(AgentStep.run_id == run_id))
            await db.execute(Approval.__table__.delete().where(Approval.run_id == run_id))
            await db.execute(AgentRun.__table__.delete().where(AgentRun.id == run_id))
            await db.commit()


async def test_rejeicao_sobrevive_a_retry_concorrente_do_celery(client, auth_headers):
    """Fase 183(c) — sem o lock `FOR UPDATE` na AgentRun, um retry do
    Celery em voo (aqui simulado: SELECT...FOR UPDATE + sleep + mutação +
    commit, mesma sequência de agent_tasks.py::_run_async) podia commitar
    por cima de uma rejeição humana já commitada via HTTP — a Approval
    ficava REJEITADO mas o AgentRun.status refletia o que o retry
    calculou (SUCCESS) em vez de FAILED."""
    import asyncio

    async with AsyncSessionLocal() as db:
        run = AgentRun(
            id=uuid.uuid4(), agent_name="orchestration_agent", trigger_type="CHAINED",
            input_data={}, status="AWAITING_APPROVAL", task_type="full_contract_flow",
            tenant_id=AFJ_TENANT, tokens_used=100, cost_usd=Decimal("0.05"),
            requires_approval=True,
        )
        db.add(run)
        await db.flush()
        appr = Approval(id=uuid.uuid4(), run_id=run.id, tipo="TEST_GENERIC_186_LOCK", titulo="Teste lock 186", status="PENDENTE", tenant_id=AFJ_TENANT)
        db.add(appr)
        await db.commit()
        run_id, approval_id = run.id, appr.id

    async def _retry_em_voo():
        async with AsyncSessionLocal() as db2:
            run = (await db2.execute(select(AgentRun).where(AgentRun.id == run_id).with_for_update())).scalar_one_or_none()
            await asyncio.sleep(0.6)
            if run.status not in ("SUCCESS", "FAILED", "CANCELADO"):
                run.status = "SUCCESS"
            run.tokens_used = (run.tokens_used or 0) + 50
            run.completed_at = datetime.now(timezone.utc)
            await db2.commit()

    async def _rejeicao_http():
        await asyncio.sleep(0.2)
        resp = await client.post(
            f"/api/v1/approvals/{approval_id}/resolve",
            json={"approved": False, "rejection_reason": "teste 186 lock"},
            headers=auth_headers,
        )
        return resp

    try:
        _, resp = await asyncio.gather(_retry_em_voo(), _rejeicao_http())
        assert resp.status_code == 200, resp.text

        async with AsyncSessionLocal() as db:
            run = await db.get(AgentRun, run_id)
            appr = await db.get(Approval, approval_id)
            assert appr.status == "REJEITADO"
            assert run.status == "FAILED", (
                f"esperava AgentRun.status=FAILED refletindo a rejeição, achou {run.status} — "
                "sem o lock FOR UPDATE (Fase 184.2) o retry em voo sobrescreve a rejeição"
            )
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(Approval.__table__.delete().where(Approval.run_id == run_id))
            await db.execute(AgentRun.__table__.delete().where(AgentRun.id == run_id))
            await db.commit()
