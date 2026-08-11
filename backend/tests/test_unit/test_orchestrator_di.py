"""Unit tests para injeção de dependências no nó do orquestrador."""
import app.agents.brain.orchestrator as orch
import app.db.base as dbbase
import app.db.redis as dbredis
from app.agents.brain.context import AgentContext
from app.agents.base.result import AgentResult, AgentStatus


async def test_qdrant_guard_returns_none_on_placeholder():
    # QDRANT_URL padrão é placeholder → RAG desligado (None), sem tentar conectar
    assert await orch._get_qdrant_if_configured() is None


class _FakeSession:
    def __init__(self):
        self.committed = False
        self.rolledback = False
        self.added = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolledback = True


def _base_state(route="fake_agent"):
    return {
        "context": AgentContext(task_type="x"),
        "route": route,
        "chain": [route],
        "chain_index": 0,
        "agent_results": [],
        "pending_approval": None,
        "final_output": None,
        "error": None,
        "done": False,
    }


async def test_node_injects_db_redis_and_commits_on_success(monkeypatch):
    captured = {}

    class FakeAgent:
        name = "fake_agent"

        def __init__(self, db=None, redis=None, qdrant=None):
            captured.update(db=db, redis=redis, qdrant=qdrant)

        async def run(self, ctx):
            return AgentResult(status=AgentStatus.SUCCESS, agent_name=self.name, output={"ok": True})

    sess = _FakeSession()
    monkeypatch.setattr(dbbase, "AsyncSessionLocal", lambda: sess)

    async def _fake_redis():
        return "REDIS"
    monkeypatch.setattr(dbredis, "get_redis", _fake_redis)
    monkeypatch.setattr(orch, "resolve_agent_class", lambda route: FakeAgent)

    out = await orch.node_execute_agent(_base_state())

    assert captured["db"] is sess
    assert captured["redis"] == "REDIS"
    assert sess.committed is True and sess.rolledback is False
    assert out["agent_results"][0].status == AgentStatus.SUCCESS


async def test_node_rolls_back_on_failure(monkeypatch):
    class FailAgent:
        name = "fail_agent"

        def __init__(self, db=None, redis=None, qdrant=None):
            pass

        async def run(self, ctx):
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name, error="boom")

    sess = _FakeSession()
    monkeypatch.setattr(dbbase, "AsyncSessionLocal", lambda: sess)

    async def _fake_redis():
        return None
    monkeypatch.setattr(dbredis, "get_redis", _fake_redis)
    monkeypatch.setattr(orch, "resolve_agent_class", lambda route: FailAgent)

    out = await orch.node_execute_agent(_base_state("fail_agent"))

    # A falha do agente em si é revertida (rollback), mas o AgentStep que
    # registra "esse passo falhou" ainda é gravado numa transação própria
    # depois — daí `committed` também ficar True (Fase 169.1).
    assert sess.rolledback is True and sess.committed is True
    assert len(sess.added) == 1
    assert out["error"] == "boom" and out["done"] is True


async def test_node_unknown_route_returns_error(monkeypatch):
    monkeypatch.setattr(orch, "resolve_agent_class", lambda route: None)
    out = await orch.node_execute_agent(_base_state("nao_existe"))
    assert out["done"] is True and "não encontrado" in out["error"]
