"""Unit tests para o encadeamento real de agentes (Fase 169.1).

Antes desta fase, `TASK_ROUTE_MAP` já declarava 3 chains multi-agente mas
`classify_task()` sempre truncava pro primeiro agente e o orquestrador
LangGraph não tinha loop nenhum — disparar `new_process_intake` rodava
silenciosamente só `process_agent`. Estes testes cobrem o motor de
encadeamento real: `get_chain()` (roteamento completo), o loop de
`node_execute_agent`/`route_after_execute_agent` no orquestrador, e a
projeção de saída→entrada entre passos (`chain_projectors.py`).
"""
import app.agents.brain.orchestrator as orch
import app.db.base as dbbase
import app.db.redis as dbredis
from app.agents.brain.context import AgentContext
from app.agents.brain.router import get_chain, classify_task, TASK_ROUTE_MAP
from app.agents.brain.chain_projectors import project_output
from app.agents.base.result import AgentResult, AgentStatus


# ─── get_chain() / classify_task() ─────────────────────────────────────────

def test_get_chain_returns_full_list_for_declared_chains():
    assert get_chain("new_process_intake") == [
        "process_agent", "jurisprudence_agent", "strategy_agent", "crm_agent",
    ]
    assert get_chain("generate_and_review_petition") == [
        "jurisprudence_agent", "petition_agent", "review_agent",
    ]
    assert get_chain("full_contract_flow") == ["contract_agent", "review_agent"]


def test_get_chain_returns_single_item_list_for_direct_routes():
    assert get_chain("generate_petition") == ["petition_agent"]
    assert get_chain("tarefa_desconhecida", {}) == ["orchestration_agent"]


def test_get_chain_matches_task_route_map_exactly():
    # Nenhuma chain declarada em TASK_ROUTE_MAP pode ser truncada silenciosamente.
    for task_type, route in TASK_ROUTE_MAP.items():
        expected = list(route) if isinstance(route, list) else [route]
        assert get_chain(task_type) == expected


def test_classify_task_still_returns_only_first_agent():
    # Uso legado (fora do orquestrador) continua recebendo só o 1º agente.
    assert classify_task("new_process_intake", {}) == "process_agent"
    assert classify_task("generate_petition", {}) == "petition_agent"


# ─── chain_projectors.py ────────────────────────────────────────────────────

def test_default_projector_merges_without_overwriting_task_input():
    ctx = AgentContext(task_type="x", task_input={"query": "original do usuário"})
    result = AgentResult(
        status=AgentStatus.SUCCESS, agent_name="sem_bridge_a",
        output={"query": "seria sobrescrito", "novo_campo": "abc"},
    )
    merged = project_output("sem_bridge_a", "sem_bridge_b", result, ctx)
    assert merged["query"] == "original do usuário"
    assert merged["novo_campo"] == "abc"


def test_process_to_jurisprudence_bridge_builds_query_from_movimentos():
    ctx = AgentContext(task_type="new_process_intake", task_input={})
    result = AgentResult(
        status=AgentStatus.SUCCESS, agent_name="process_agent",
        output={"movimentos": [{"ai_resumo": "resumo 1"}, {"descricao": "descricao 2"}]},
    )
    merged = project_output("process_agent", "jurisprudence_agent", result, ctx)
    assert "resumo 1" in merged["query"]
    assert "descricao 2" in merged["query"]


def test_bridge_never_overrides_caller_supplied_field():
    ctx = AgentContext(task_type="new_process_intake", task_input={"query": "busca manual do usuário"})
    result = AgentResult(
        status=AgentStatus.SUCCESS, agent_name="process_agent",
        output={"movimentos": [{"descricao": "algo"}]},
    )
    merged = project_output("process_agent", "jurisprudence_agent", result, ctx)
    assert merged["query"] == "busca manual do usuário"


# ─── loop real no orquestrador ──────────────────────────────────────────────

class _FakeSession:
    def __init__(self):
        self.committed = 0
        self.rolledback = 0
        self.added = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed += 1

    async def rollback(self):
        self.rolledback += 1


def _fake_agent_class(route, result):
    class FakeAgent:
        name = route

        def __init__(self, db=None, redis=None, qdrant=None):
            pass

        async def run(self, ctx):
            return result

    return FakeAgent


async def _drive_chain(monkeypatch, task_type, results_by_route, task_input=None):
    """Roda o grafo manualmente: classify_intent, depois execute_agent em
    loop seguindo route_after_execute_agent — sem precisar do LangGraph
    compilado nem de DB/Redis reais."""
    monkeypatch.setattr(dbbase, "AsyncSessionLocal", lambda: _FakeSession())

    async def _fake_redis():
        return None
    monkeypatch.setattr(dbredis, "get_redis", _fake_redis)

    def _resolve(route):
        return _fake_agent_class(route, results_by_route[route])
    monkeypatch.setattr(orch, "_resolve_agent_class", _resolve)

    ctx = AgentContext(task_type=task_type, task_input=task_input or {})
    state = {
        "context": ctx, "route": "", "chain": [], "chain_index": 0,
        "agent_results": [], "pending_approval": None, "final_output": None,
        "error": None, "done": False,
    }
    state = await orch.node_classify_intent(state)

    executed = []
    while True:
        current_route = state["route"]
        state = await orch.node_execute_agent(state)
        executed.append(current_route)
        if orch.route_after_execute_agent(state) != "execute_agent":
            break
    return state, executed


async def test_new_process_intake_runs_all_four_steps_in_order(monkeypatch):
    results = {
        "process_agent": AgentResult(status=AgentStatus.SUCCESS, agent_name="process_agent", output={"movimentos": []}),
        "jurisprudence_agent": AgentResult(status=AgentStatus.SUCCESS, agent_name="jurisprudence_agent", output={"resultados": [], "analise_ia": ""}),
        "strategy_agent": AgentResult(status=AgentStatus.SUCCESS, agent_name="strategy_agent", output={"analise_estrategica": ""}),
        "crm_agent": AgentResult(status=AgentStatus.SUCCESS, agent_name="crm_agent", output={"ok": True}),
    }
    state, executed = await _drive_chain(monkeypatch, "new_process_intake", results)

    assert executed == ["process_agent", "jurisprudence_agent", "strategy_agent", "crm_agent"]
    assert len(state["agent_results"]) == 4
    assert all(r.status == AgentStatus.SUCCESS for r in state["agent_results"])
    assert state["chain_index"] == 3


async def test_chain_stops_on_failed_step_without_advancing(monkeypatch):
    results = {
        "process_agent": AgentResult(status=AgentStatus.SUCCESS, agent_name="process_agent", output={"movimentos": []}),
        "jurisprudence_agent": AgentResult(status=AgentStatus.FAILED, agent_name="jurisprudence_agent", error="sem jurisprudência"),
    }
    # strategy_agent/crm_agent de propósito NÃO estão em `results` — se o loop
    # tentasse rodá-los mesmo após a falha, isso estouraria KeyError aqui.
    state, executed = await _drive_chain(monkeypatch, "new_process_intake", results)

    assert executed == ["process_agent", "jurisprudence_agent"]
    assert len(state["agent_results"]) == 2
    assert state["done"] is True
    assert state["error"] == "sem jurisprudência"


async def test_full_contract_flow_stops_at_gate_without_running_review(monkeypatch):
    results = {
        "contract_agent": AgentResult(
            status=AgentStatus.AWAITING_APPROVAL, agent_name="contract_agent",
            output={"contrato": "rascunho"}, approval_required={"tipo": "CONTRACT_SIGN"},
        ),
    }
    # review_agent de propósito não está em `results` (ver comentário acima).
    state, executed = await _drive_chain(monkeypatch, "full_contract_flow", results)

    assert executed == ["contract_agent"]
    assert len(state["agent_results"]) == 1

    state = await orch.node_check_approval(state)
    assert state["pending_approval"] == {"tipo": "CONTRACT_SIGN"}
    assert orch.route_after_approval_check(state) == "awaiting_approval"


async def test_generate_and_review_petition_stops_at_middle_gate(monkeypatch):
    results = {
        "jurisprudence_agent": AgentResult(status=AgentStatus.SUCCESS, agent_name="jurisprudence_agent", output={"resultados": [], "analise_ia": ""}),
        "petition_agent": AgentResult(
            status=AgentStatus.AWAITING_APPROVAL, agent_name="petition_agent",
            output={}, approval_required={"tipo": "PETITION_FILING"},
        ),
    }
    # review_agent (3º passo) de propósito não está em `results`.
    state, executed = await _drive_chain(monkeypatch, "generate_and_review_petition", results)

    assert executed == ["jurisprudence_agent", "petition_agent"]
    assert len(state["agent_results"]) == 2

    state = await orch.node_check_approval(state)
    assert state["pending_approval"] == {"tipo": "PETITION_FILING"}
    assert orch.route_after_approval_check(state) == "awaiting_approval"
