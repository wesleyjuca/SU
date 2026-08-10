"""Fase 166 — circuit breaker persiste estado no Redis, compartilhado entre
processos. Antes, `CircuitBreaker` vivia só na memória do processo que criou
a instância — o web (uvicorn, serve o painel Cérebro) e o worker (Celery,
roda a captura de verdade via polling/Beat) tinham cada um sua própria cópia
isolada, então o indicador "Fontes da Captura" nunca refletia falhas reais
registradas pelo worker. Também corrige, de brinde, as fontes credenciadas
(pdpj/escavador/judit/jusbrasil) — cada chamada cria uma instância NOVA via
`para_tenant()`, então o contador de falhas consecutivas nunca sobrevivia
entre 2 capturas nem dentro do MESMO processo, sem persistência externa."""
import pytest

from app.integrations.fontes.circuit_breaker import CLOSED, OPEN, CircuitBreaker


class _FakeRedis:
    def __init__(self):
        self._store = {}

    async def get(self, key):
        return self._store.get(key)

    async def set(self, key, value, ex=None):
        self._store[key] = value
        return True


@pytest.mark.asyncio
async def test_run_persiste_falha_no_redis(monkeypatch):
    fake = _FakeRedis()

    async def _fake_get_redis():
        return fake

    monkeypatch.setattr("app.db.redis.get_redis", _fake_get_redis)

    cb = CircuitBreaker(failure_threshold=1, reset_timeout=999, name="comunica")

    async def explode():
        raise RuntimeError("boom")

    await cb.run(explode, default=None)

    assert cb.state == OPEN
    assert "circuit_breaker:comunica" in fake._store


@pytest.mark.asyncio
async def test_nova_instancia_hidrata_falha_gravada_por_outro_processo(monkeypatch):
    """Simula 2 processos: o worker abre o breaker via uma instância, o web
    (uma instância NOVA e sem histórico local) precisa enxergar isso."""
    fake = _FakeRedis()

    async def _fake_get_redis():
        return fake

    monkeypatch.setattr("app.db.redis.get_redis", _fake_get_redis)

    cb_worker = CircuitBreaker(failure_threshold=1, reset_timeout=999, name="comunica")

    async def explode():
        raise RuntimeError("fonte fora do ar")

    await cb_worker.run(explode, default=None)
    assert cb_worker.state == OPEN

    # Processo "web" — instância nova, memória local zerada.
    cb_web = CircuitBreaker(failure_threshold=1, reset_timeout=999, name="comunica")
    assert cb_web.state == CLOSED  # sem hidratar ainda, estado local puro

    async def factory_nao_deveria_rodar():
        raise AssertionError("não deveria ter passado — breaker deveria estar OPEN após hidratar")

    resultado = await cb_web.run(factory_nao_deveria_rodar, default="bloqueado")
    assert resultado == "bloqueado"  # hidratou do Redis e bloqueou a chamada


@pytest.mark.asyncio
async def test_estado_atual_reflete_o_que_outro_processo_gravou_sem_precisar_de_run(monkeypatch):
    """O painel Cérebro chama `estado_atual()` direto, sem passar por
    `run()` — precisa refletir o Redis mesmo numa instância que nunca fez
    nenhuma chamada local."""
    fake = _FakeRedis()

    async def _fake_get_redis():
        return fake

    monkeypatch.setattr("app.db.redis.get_redis", _fake_get_redis)

    cb_worker = CircuitBreaker(failure_threshold=1, reset_timeout=999, name="datajud")

    async def explode():
        raise RuntimeError("timeout")

    await cb_worker.run(explode, default=None)

    cb_painel = CircuitBreaker(failure_threshold=1, reset_timeout=999, name="datajud")
    estado = await cb_painel.estado_atual()

    assert estado == OPEN


@pytest.mark.asyncio
async def test_estado_atual_sempre_busca_fresco_nao_usa_cache_local(monkeypatch):
    """2 chamadas seguidas de `estado_atual()` na MESMA instância devem
    refletir mudanças feitas por outro processo entre as 2 chamadas —
    diferente de `run()`, que hidrata só 1x por instância."""
    fake = _FakeRedis()

    async def _fake_get_redis():
        return fake

    monkeypatch.setattr("app.db.redis.get_redis", _fake_get_redis)

    cb_painel = CircuitBreaker(failure_threshold=1, reset_timeout=999, name="comunica")
    assert await cb_painel.estado_atual() == CLOSED  # nada no Redis ainda

    cb_worker = CircuitBreaker(failure_threshold=1, reset_timeout=999, name="comunica")

    async def explode():
        raise RuntimeError("boom")

    await cb_worker.run(explode, default=None)

    assert await cb_painel.estado_atual() == OPEN  # mesma instância, estado novo


@pytest.mark.asyncio
async def test_run_persiste_sucesso_fecha_e_zera_no_redis(monkeypatch):
    fake = _FakeRedis()

    async def _fake_get_redis():
        return fake

    monkeypatch.setattr("app.db.redis.get_redis", _fake_get_redis)

    cb = CircuitBreaker(failure_threshold=1, reset_timeout=999, name="comunica")

    async def explode():
        raise RuntimeError("boom")

    await cb.run(explode, default=None)
    assert cb.state == OPEN

    async def ok():
        return "resultado"

    cb.record_success()  # simula meio-aberto liberando 1 tentativa e dando certo
    await cb._persistir()

    outro = CircuitBreaker(failure_threshold=1, reset_timeout=999, name="comunica")
    assert await outro.estado_atual() == CLOSED


@pytest.mark.asyncio
async def test_sem_redis_configurado_degrada_graciosamente_pro_comportamento_local(monkeypatch):
    async def _fake_get_redis_none():
        return None

    monkeypatch.setattr("app.db.redis.get_redis", _fake_get_redis_none)

    cb = CircuitBreaker(failure_threshold=1, reset_timeout=999, name="comunica")

    async def explode():
        raise RuntimeError("boom")

    r = await cb.run(explode, default="D")
    assert r == "D"
    assert cb.state == OPEN  # gating local continua funcionando sem Redis

    assert await cb.estado_atual() == OPEN  # cai pro estado local se Redis ausente


@pytest.mark.asyncio
async def test_falha_de_redis_nao_propaga_fail_soft(monkeypatch):
    async def _fake_get_redis_quebrado():
        raise ConnectionError("redis fora do ar")

    monkeypatch.setattr("app.db.redis.get_redis", _fake_get_redis_quebrado)

    cb = CircuitBreaker(failure_threshold=1, reset_timeout=999, name="comunica")

    async def ok():
        return "x"

    # Não deve lançar mesmo com Redis inacessível.
    r = await cb.run(ok, default=None)
    assert r == "x"


@pytest.mark.asyncio
async def test_hidratar_so_roda_uma_vez_por_instancia(monkeypatch):
    fake = _FakeRedis()
    leituras = {"n": 0}

    async def _fake_get_redis():
        return fake

    async def get_contando(key):
        leituras["n"] += 1
        return fake._store.get(key)

    fake.get = get_contando
    monkeypatch.setattr("app.db.redis.get_redis", _fake_get_redis)

    cb = CircuitBreaker(failure_threshold=5, reset_timeout=999, name="comunica")

    async def ok():
        return "x"

    await cb.run(ok, default=None)
    await cb.run(ok, default=None)
    await cb.run(ok, default=None)

    assert leituras["n"] == 1  # hidratou só na 1ª chamada
