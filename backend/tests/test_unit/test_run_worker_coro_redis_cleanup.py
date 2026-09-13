"""Achado real de produção (log real do Railway):
`task_lock_acquire_failed error=Event loop is closed
key=task_lock:checar_infra_periodico` — a mesma classe de bug já corrigida
para o engine asyncpg (`run_worker_coro` chama `engine.dispose()` ao fim de
cada task) também afetava o cliente Redis global (`app.db.redis._redis_pool`
— singleton reaproveitado entre execuções de task, cada uma com seu próprio
event loop via `asyncio.run()`). `run_worker_coro` agora também fecha o pool
Redis ao final de cada task; um erro ao fechá-lo (conexão já rompida pelo
loop anterior) é fail-soft — nunca mascara o resultado real da task.

Fase pós-264 — o mesmo padrão também afetava o `AsyncOpenAI` singleton de
`app.rag.embeddings._client` (achado real: "Event loop is closed" ao
sincronizar a Doutrina do Google Drive, num documento grande com múltiplas
chamadas sequenciais de embedding)."""
import pytest

import app.rag.embeddings as embeddings_mod
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


class _FakeEmbeddingsClient:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _limpa_embeddings_client():
    embeddings_mod._client = None
    yield
    embeddings_mod._client = None


def test_run_worker_coro_fecha_e_reseta_client_de_embeddings(monkeypatch, _fake_engine):
    async def _fake_close_redis():
        pass

    monkeypatch.setattr("app.db.redis.close_redis", _fake_close_redis)
    fake_client = _FakeEmbeddingsClient()
    embeddings_mod._client = fake_client

    async def _coro():
        return "resultado"

    resultado = async_utils_mod.run_worker_coro(_coro())

    assert resultado == "resultado"
    assert fake_client.closed is True
    assert embeddings_mod._client is None


def test_run_worker_coro_sem_client_de_embeddings_nao_quebra(monkeypatch, _fake_engine):
    """Caminho comum (nenhuma task usou embeddings ainda) — `_client` já é
    `None`, `run_worker_coro` não deve tentar fechar nada nem quebrar."""
    async def _fake_close_redis():
        pass

    monkeypatch.setattr("app.db.redis.close_redis", _fake_close_redis)
    assert embeddings_mod._client is None

    async def _coro():
        return "resultado"

    resultado = async_utils_mod.run_worker_coro(_coro())
    assert resultado == "resultado"
    assert embeddings_mod._client is None


def test_run_worker_coro_close_embeddings_falhando_nao_mascara_resultado(monkeypatch, _fake_engine):
    """Mesma prova de fail-soft já usada pro Redis: uma falha ao fechar o
    client de embeddings (conexão já rompida pelo loop anterior) nunca pode
    mascarar o resultado real da task."""
    async def _fake_close_redis():
        pass

    monkeypatch.setattr("app.db.redis.close_redis", _fake_close_redis)

    class _ClientQuebrado:
        async def close(self):
            raise RuntimeError("Event loop is closed")

    embeddings_mod._client = _ClientQuebrado()

    async def _coro():
        return "resultado real"

    resultado = async_utils_mod.run_worker_coro(_coro())
    assert resultado == "resultado real"
    # Mesmo com a falha ao fechar, o singleton é resetado — nunca fica
    # preso a um client possivelmente inutilizável.
    assert embeddings_mod._client is None
