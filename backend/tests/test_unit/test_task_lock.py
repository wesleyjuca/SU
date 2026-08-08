"""Fase 147 — TaskLock: lock distribuído leve (Redis SET NX EX) pras 7 tasks
agendadas do Celery Beat. Nenhuma tinha proteção contra execução concorrente
do MESMO job (disparo manual + Beat quase simultâneo, redelivery)."""
import pytest

from app.workers.task_lock import TaskLock


class _FakeRedis:
    """SET NX EX + GET + DELETE mínimos, o bastante pra exercitar TaskLock."""

    def __init__(self):
        self._store = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self._store:
            return None
        self._store[key] = value
        return True

    async def get(self, key):
        return self._store.get(key)

    async def delete(self, key):
        self._store.pop(key, None)


@pytest.mark.asyncio
async def test_segunda_aquisicao_concorrente_falha_enquanto_a_primeira_nao_libera(monkeypatch):
    fake = _FakeRedis()

    async def _fake_get_redis():
        return fake

    monkeypatch.setattr("app.workers.task_lock.get_redis", _fake_get_redis)

    lock1 = TaskLock("job_x", ttl_seconds=60)
    lock2 = TaskLock("job_x", ttl_seconds=60)

    assert await lock1.acquire() is True
    assert await lock2.acquire() is False  # "execução concorrente" nao consegue


@pytest.mark.asyncio
async def test_release_libera_o_lock_pra_proxima_execucao(monkeypatch):
    fake = _FakeRedis()

    async def _fake_get_redis():
        return fake

    monkeypatch.setattr("app.workers.task_lock.get_redis", _fake_get_redis)

    lock1 = TaskLock("job_y", ttl_seconds=60)
    lock2 = TaskLock("job_y", ttl_seconds=60)
    lock3 = TaskLock("job_y", ttl_seconds=60)

    assert await lock1.acquire() is True
    assert await lock2.acquire() is False
    await lock1.release()
    assert await lock3.acquire() is True  # depois do release, uma nova execucao consegue


@pytest.mark.asyncio
async def test_release_nao_apaga_lock_de_outra_execucao_com_token_diferente(monkeypatch):
    """Cenário real: lock1 trava além do próprio TTL/time_limit do Celery, o
    Beat dispara de novo e lock2 pega o lock (token novo) — quando lock1
    finalmente chama release(), NÃO pode apagar o lock que já é do lock2."""
    fake = _FakeRedis()

    async def _fake_get_redis():
        return fake

    monkeypatch.setattr("app.workers.task_lock.get_redis", _fake_get_redis)

    lock1 = TaskLock("job_z", ttl_seconds=60)
    assert await lock1.acquire() is True

    # Simula o TTL do lock1 expirando no Redis de verdade (fora do controle
    # do processo) e uma 2a execução pegando o lock antes do release() do 1º.
    fake._store.pop("task_lock:job_z", None)
    lock2 = TaskLock("job_z", ttl_seconds=60)
    assert await lock2.acquire() is True

    await lock1.release()  # token de lock1 != o que está no Redis agora (lock2)
    assert fake._store.get("task_lock:job_z") == lock2.token  # lock de lock2 sobrevive


@pytest.mark.asyncio
async def test_sem_redis_configurado_acquire_e_sempre_true_fail_open(monkeypatch):
    async def _fake_get_redis_none():
        return None

    monkeypatch.setattr("app.workers.task_lock.get_redis", _fake_get_redis_none)

    lock1 = TaskLock("job_w", ttl_seconds=60)
    lock2 = TaskLock("job_w", ttl_seconds=60)
    assert await lock1.acquire() is True
    assert await lock2.acquire() is True  # sem Redis, nunca bloqueia


@pytest.mark.asyncio
async def test_falha_de_redis_no_acquire_tambem_e_fail_open(monkeypatch):
    async def _fake_get_redis_falha():
        raise ConnectionError("redis fora do ar")

    monkeypatch.setattr("app.workers.task_lock.get_redis", _fake_get_redis_falha)

    lock = TaskLock("job_v", ttl_seconds=60)
    assert await lock.acquire() is True  # nunca bloqueia por falha de infra opcional


def test_check_upcoming_deadlines_pula_execucao_quando_lock_ja_esta_preso(monkeypatch):
    """Integração leve: com o lock de check_upcoming_deadlines já preso (2ª
    execução concorrente do mesmo job), a task real devolve 'skipped' sem
    nunca tocar o banco (prova que o lock intercepta ANTES de abrir sessão).

    Sem @pytest.mark.asyncio de propósito: check_upcoming_deadlines.run()
    chama asyncio.run() internamente (run_worker_coro) — rodar isso dentro
    de um teste já async lançaria 'asyncio.run() cannot be called from a
    running event loop'."""
    fake = _FakeRedis()
    fake._store["task_lock:check_upcoming_deadlines"] = "outra-execucao-em-andamento"

    async def _fake_get_redis():
        return fake

    monkeypatch.setattr("app.workers.task_lock.get_redis", _fake_get_redis)

    from app.workers.tasks.deadline_check import check_upcoming_deadlines

    resultado = check_upcoming_deadlines.run()
    assert resultado == {"skipped": True, "reason": "lock_held"}
