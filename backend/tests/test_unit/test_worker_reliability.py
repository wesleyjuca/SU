"""Unit tests para confiabilidade dos workers e honestidade de status."""
import asyncio
import app.db.base as dbbase
from app.workers.async_utils import run_worker_coro
from app.agents.publication_monitor.publication_monitor_agent import PublicationMonitorAgent
from app.agents.base.result import AgentStatus
from app.agents.brain.context import AgentContext


def test_run_worker_coro_disposes_engine_and_uses_distinct_loops(monkeypatch):
    # `loops` guarda os PRÓPRIOS objetos de loop, não `id(...)`. A versão
    # anterior usava `id()`, que em CPython é o endereço de memória: como o
    # 1º loop já foi coletado quando o 2º é criado, o alocador pode devolver
    # o mesmo endereço e o set colapsa para 1 elemento — o teste acusava
    # "mesmo loop" com dois loops de fato distintos. Falhou assim no 1º run
    # real do CI (a suíte nunca havia rodado lá) depois de passar localmente.
    # Guardar a referência resolve nos dois sentidos: mantém os objetos vivos,
    # então o endereço do 1º não pode ser reciclado, e a comparação passa a
    # ser por identidade de objeto, que é o que o teste quer afirmar.
    calls = {"dispose": 0, "loops": set()}

    class _FakeEngine:
        async def dispose(self):
            calls["dispose"] += 1

    monkeypatch.setattr(dbbase, "engine", _FakeEngine())

    async def work():
        calls["loops"].add(asyncio.get_running_loop())
        return 42

    r1 = run_worker_coro(work())
    r2 = run_worker_coro(work())  # segunda task → novo loop

    assert r1 == 42 and r2 == 42
    assert calls["dispose"] == 2           # dispose por task
    assert len(calls["loops"]) == 2        # cada task em loop distinto


async def test_publication_monitor_partial_sem_db():
    agent = PublicationMonitorAgent()  # sem db
    ctx = AgentContext(
        task_type="monitor_publications",
        task_input={},
    )
    res = await agent.execute(ctx)
    assert res.status == AgentStatus.PARTIAL
    assert "DB necessário" in res.output.get("message", "")
