"""Achado real de produção (log real do Railway):
`task_lock_acquire_failed error=Event loop is closed
key=task_lock:checar_infra_periodico` — a mesma classe de bug já corrigida
para o engine asyncpg (`run_worker_coro` chama `engine.dispose()` ao fim de
cada task) também afetava o cliente Redis global (`app.db.redis._redis_pool`
— singleton reaproveitado entre execuções de task, cada uma com seu próprio
event loop via `asyncio.run()`). `run_worker_coro` agora também fecha o pool
Redis ao final de cada task; um erro ao fechá-lo (conexão já rompida pelo
loop anterior) é fail-soft — nunca mascara o resultado real da task."""
import pytest

import app.workers.async_utils as async_utils_mod


class _FakeEngine:
    def __init__(self):
        self.disposed = False

    async def dispose(self):
        self.disposed = True


@pytest.fixture
def _fake_engine(monkeypatch):
    fake = _FakeEngine()
    monkeypatch.setattr("app.db.base.engine", fake)
    yield fake


def test_run_worker_coro_fecha_engine_e_redis(monkeypatch, _fake_engine):
    chamadas = []

    async def _fake_close_redis():
        chamadas.append("close_redis")

    monkeypatch.setattr("app.db.redis.close_redis", _fake_close_redis)

    async def _coro():
        return "resultado"

    resultado = async_utils_mod.run_worker_coro(_coro())

    assert resultado == "resultado"
    assert _fake_engine.disposed is True
    assert chamadas == ["close_redis"]


def test_run_worker_coro_close_redis_falhando_nao_mascara_resultado(monkeypatch, _fake_engine):
    """A prova real do fix: mesmo se `close_redis()` levantar (conexão já
    rompida pelo loop de uma task anterior), o resultado da task atual
    precisa sobreviver — nunca uma exceção de limpeza no lugar do
    resultado/exceção real."""
    async def _close_redis_quebrado():
        raise RuntimeError("Event loop is closed")

    monkeypatch.setattr("app.db.redis.close_redis", _close_redis_quebrado)

    async def _coro():
        return "resultado real"

    resultado = async_utils_mod.run_worker_coro(_coro())
    assert resultado == "resultado real"


def test_run_worker_coro_close_redis_falhando_preserva_excecao_real(monkeypatch, _fake_engine):
    """Mesmo cenário, mas a task original falhou — a exceção REAL da task
    precisa propagar, não a falha de limpeza do Redis."""
    async def _close_redis_quebrado():
        raise RuntimeError("Event loop is closed")

    monkeypatch.setattr("app.db.redis.close_redis", _close_redis_quebrado)

    async def _coro():
        raise ValueError("falha real da task")

    with pytest.raises(ValueError, match="falha real da task"):
        async_utils_mod.run_worker_coro(_coro())
