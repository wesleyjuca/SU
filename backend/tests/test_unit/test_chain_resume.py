"""Unit tests para a retomada de chains após aprovação humana (Fase 169.2).

Estilo de fixtures espelha test_hitl.py (fakes leves de sessão, sem harness
de FastAPI) e test_agent_chaining.py (monkeypatch de AsyncSessionLocal/
get_redis/resolve_agent_class pra rodar `execute_chain_step` de verdade,
sem DB real)."""
import uuid
from decimal import Decimal

import app.agents.brain.orchestrator as orch
import app.db.base as dbbase
import app.db.redis as dbredis
import app.services.chain_resume as chain_resume
from app.agents.base.result import AgentResult, AgentStatus
from app.models.agent_run import AgentRun, AgentStep, Approval
from app.services.chain_resume import resume_chain_after_approval


class _FakeStepsResult:
    def __init__(self, steps):
        self._steps = steps

    def scalars(self):
        steps = self._steps

        class _S:
            def all(self_inner):
                return steps
        return _S()


class _FakeDB:
    """`db` externo passado a resume_chain_after_approval — só precisa
    responder o SELECT de AgentStep e commit()."""

    def __init__(self, steps):
        self._steps = steps
        self.commits = 0

    async def execute(self, stmt):
        return _FakeStepsResult(self._steps)

    async def commit(self):
        self.commits += 1


class _FakeSession:
    """`AsyncSessionLocal()` fake usado por execute_chain_step (agente
    individual) — mesmo papel do _FakeSession em test_agent_chaining.py."""
    def __init__(self):
        self.added = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass

    async def rollback(self):
        pass


def _make_agent_run(task_type: str, status: str = "AWAITING_APPROVAL") -> AgentRun:
    return AgentRun(
        id=uuid.uuid4(),
        agent_name="orchestration_agent",
        trigger_type="CHAINED",
        input_data={},
        status=status,
        task_type=task_type,
        tokens_used=100,
        cost_usd=Decimal("0.01"),
    )


def _make_step(step_number: int, step_name: str, status: str, output: dict | None = None) -> AgentStep:
    return AgentStep(
        run_id=uuid.uuid4(),
        step_number=step_number,
        step_name=step_name,
        output_json={"_status": status, **(output or {})},
        duration_ms=100,
    )


def _patch_step_execution(monkeypatch, results_by_route: dict):
    """Faz `execute_chain_step` rodar de verdade (não mockado), mas com
    agentes fake e sem DB/Redis reais — mesmo padrão de test_agent_chaining.py."""
    monkeypatch.setattr(dbbase, "AsyncSessionLocal", lambda: _FakeSession())

    async def _fake_redis():
        return None
    monkeypatch.setattr(dbredis, "get_redis", _fake_redis)

    captured_inputs = {}

    def _resolve(route):
        result = results_by_route[route]

        class FakeAgent:
            name = route

            def __init__(self, db=None, redis=None, qdrant=None):
                pass

            async def run(self, ctx):
                captured_inputs[route] = dict(ctx.task_input)
                return result

        return FakeAgent

    monkeypatch.setattr(orch, "resolve_agent_class", _resolve)
    return captured_inputs


async def test_resume_generate_and_review_petition_after_approval(monkeypatch):
    agent_run = _make_agent_run("generate_and_review_petition")
    steps = [
        _make_step(0, "jurisprudence_agent", "SUCCESS", {"resultados": []}),
        _make_step(1, "petition_agent", "AWAITING_APPROVAL", {"document_id": "abc", "conteudo_texto": "rascunho"}),
    ]
    _patch_step_execution(monkeypatch, {
        "review_agent": AgentResult(status=AgentStatus.SUCCESS, agent_name="review_agent", output={"reviewed": True}),
    })

    result = await resume_chain_after_approval(_FakeDB(steps), agent_run, approval=None)

    assert result == {"resumed": True, "final_status": "SUCCESS", "steps_run": 1}
    assert agent_run.status == "SUCCESS"
    assert agent_run.completed_at is not None


async def test_resume_full_contract_flow_after_approval(monkeypatch):
    agent_run = _make_agent_run("full_contract_flow")
    steps = [
        _make_step(0, "contract_agent", "AWAITING_APPROVAL", {"document_id": "xyz"}),
    ]
    _patch_step_execution(monkeypatch, {
        "review_agent": AgentResult(status=AgentStatus.SUCCESS, agent_name="review_agent", output={"reviewed": True}),
    })

    result = await resume_chain_after_approval(_FakeDB(steps), agent_run, approval=None)

    assert result == {"resumed": True, "final_status": "SUCCESS", "steps_run": 1}
    assert agent_run.status == "SUCCESS"


async def test_resume_noop_when_task_type_missing():
    agent_run = _make_agent_run(None)
    result = await resume_chain_after_approval(_FakeDB([]), agent_run, approval=None)
    assert result["resumed"] is False
    assert "task_type" in result["reason"]


async def test_resume_noop_when_gate_was_last_step():
    # generate_and_review_petition tem 3 passos; simula os 3 já executados
    # (review_agent, o último, teria de alguma forma pedido aprovação —
    # cenário sintético só pra exercitar o guard de "não sobra passo").
    agent_run = _make_agent_run("generate_and_review_petition", status="AWAITING_APPROVAL")
    steps = [
        _make_step(0, "jurisprudence_agent", "SUCCESS"),
        _make_step(1, "petition_agent", "SUCCESS"),
        _make_step(2, "review_agent", "AWAITING_APPROVAL"),
    ]
    result = await resume_chain_after_approval(_FakeDB(steps), agent_run, approval=None)

    assert result["resumed"] is False
    assert "último passo" in result["reason"]
    assert agent_run.status == "SUCCESS"  # finaliza mesmo sem rodar mais nada


async def test_resume_stops_on_failed_step(monkeypatch):
    agent_run = _make_agent_run("full_contract_flow")
    steps = [_make_step(0, "contract_agent", "AWAITING_APPROVAL", {"document_id": "xyz"})]
    _patch_step_execution(monkeypatch, {
        "review_agent": AgentResult(status=AgentStatus.FAILED, agent_name="review_agent", error="revisão falhou"),
    })

    result = await resume_chain_after_approval(_FakeDB(steps), agent_run, approval=None)

    assert result == {"resumed": True, "final_status": "FAILED", "steps_run": 1}
    assert agent_run.status == "FAILED"
    assert agent_run.error_message == "revisão falhou"


async def test_resume_propagates_modifications_to_next_step(monkeypatch):
    agent_run = _make_agent_run("generate_and_review_petition")
    steps = [
        _make_step(0, "jurisprudence_agent", "SUCCESS"),
        _make_step(1, "petition_agent", "AWAITING_APPROVAL", {"document_id": "abc", "conteudo_texto": "rascunho original"}),
    ]
    captured = _patch_step_execution(monkeypatch, {
        "review_agent": AgentResult(status=AgentStatus.SUCCESS, agent_name="review_agent", output={"reviewed": True}),
    })

    await resume_chain_after_approval(
        _FakeDB(steps), agent_run, approval=None,
        modifications={"conteudo_texto": "texto editado pelo humano"},
    )

    assert captured["review_agent"]["conteudo_texto"] == "texto editado pelo humano"


# ─── Fase 171 — múltiplos gates HITL na mesma chain ────────────────────────

class _FakeResultFlexible:
    """Resultado de query mais genérico que _FakeStepsResult — suporta tanto
    `.scalars().all()` (SELECT AgentStep, SELECT User.id) quanto
    `.scalar_one_or_none()` (checagem de idempotência do create_approval_from_state)."""
    def __init__(self, *, scalars_list=None, scalar_value=None):
        self._scalars_list = scalars_list
        self._scalar_value = scalar_value

    def scalars(self):
        items = self._scalars_list or []

        class _S:
            def all(self_inner):
                return items
        return _S()

    def scalar_one_or_none(self):
        return self._scalar_value


class _FakeDBQueue:
    """DB fake que devolve resultados de uma fila, em ordem — necessário
    quando a retomada também cria uma nova Approval (dispara consultas
    extras dentro de create_approval_from_state/_notify_tenant_of_approval),
    não só o SELECT de AgentStep que _FakeDB (acima) cobre."""
    def __init__(self, results):
        self._results = list(results)
        self.added = []
        self.commits = 0

    async def execute(self, stmt):
        return self._results.pop(0) if self._results else _FakeResultFlexible()

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1


async def test_resume_creates_second_approval_when_step_also_needs_approval(monkeypatch):
    agent_run = _make_agent_run("generate_and_review_petition")
    steps = [
        _make_step(0, "jurisprudence_agent", "SUCCESS"),
        _make_step(1, "petition_agent", "AWAITING_APPROVAL", {"document_id": "abc"}),
    ]
    gate2_result = AgentResult(
        status=AgentStatus.AWAITING_APPROVAL, agent_name="review_agent", output={"revisado": True},
        approval_required={"tipo": "PETITION_REVIEW", "titulo": "Revisão pede aprovação também", "descricao": "d"},
    )
    _patch_step_execution(monkeypatch, {"review_agent": gate2_result})

    db = _FakeDBQueue([
        _FakeResultFlexible(scalars_list=steps),   # SELECT AgentStep
        _FakeResultFlexible(scalar_value=None),    # idempotência: nenhuma Approval PENDENTE pra esse run
        _FakeResultFlexible(scalars_list=[]),      # _notify_tenant_of_approval: sem staff cadastrado
    ])

    result = await resume_chain_after_approval(db, agent_run, approval=None)

    assert result == {"resumed": True, "final_status": "AWAITING_APPROVAL", "steps_run": 1}
    assert agent_run.status == "AWAITING_APPROVAL"
    assert agent_run.requires_approval is True
    novas_approvals = [o for o in db.added if isinstance(o, Approval)]
    assert len(novas_approvals) == 1
    assert novas_approvals[0].status == "PENDENTE"
    assert novas_approvals[0].tipo == "PETITION_REVIEW"


async def test_resume_full_roundtrip_through_two_gates(monkeypatch):
    """1ª retomada acha um 2º gate e pausa de novo; 2ª retomada (simulando
    o humano aprovar esse 2º gate) completa a chain com sucesso."""
    monkeypatch.setattr(chain_resume, "get_chain", lambda task_type, task_input=None: ["a_agent", "b_agent", "c_agent"])
    agent_run = _make_agent_run("chain_sintetica_2_gates")

    steps_apos_gate1 = [_make_step(0, "a_agent", "AWAITING_APPROVAL", {"x": 1})]
    gate2 = AgentResult(
        status=AgentStatus.AWAITING_APPROVAL, agent_name="b_agent", output={"y": 2},
        approval_required={"tipo": "X", "titulo": "T", "descricao": "d"},
    )
    _patch_step_execution(monkeypatch, {"b_agent": gate2})
    db1 = _FakeDBQueue([
        _FakeResultFlexible(scalars_list=steps_apos_gate1),
        _FakeResultFlexible(scalar_value=None),
        _FakeResultFlexible(scalars_list=[]),
    ])
    r1 = await resume_chain_after_approval(db1, agent_run, approval=None)
    assert r1["final_status"] == "AWAITING_APPROVAL"
    assert agent_run.status == "AWAITING_APPROVAL"

    steps_apos_gate2 = steps_apos_gate1 + [_make_step(1, "b_agent", "AWAITING_APPROVAL", {"y": 2})]
    _patch_step_execution(monkeypatch, {"c_agent": AgentResult(status=AgentStatus.SUCCESS, agent_name="c_agent", output={})})
    db2 = _FakeDBQueue([_FakeResultFlexible(scalars_list=steps_apos_gate2)])

    r2 = await resume_chain_after_approval(db2, agent_run, approval=None)
    assert r2 == {"resumed": True, "final_status": "SUCCESS", "steps_run": 1}
    assert agent_run.status == "SUCCESS"


async def test_resume_noop_when_lock_busy(monkeypatch):
    agent_run = _make_agent_run("full_contract_flow")
    steps = [_make_step(0, "contract_agent", "AWAITING_APPROVAL", {"document_id": "xyz"})]

    class _BusyLock:
        def __init__(self, *a, **kw):
            pass

        async def acquire(self):
            return False

        async def release(self):
            pass

    monkeypatch.setattr(chain_resume, "TaskLock", _BusyLock)

    result = await resume_chain_after_approval(_FakeDB(steps), agent_run, approval=None)

    assert result["resumed"] is False
    assert "andamento" in result["reason"]
    assert agent_run.status == "AWAITING_APPROVAL"  # não mexeu em nada
