"""Bloco F / F1 — testes do agregador de infra e do mapa de módulos."""
import pytest

from app.services import brain_infra as bi
from app.services.system_map import construir_mapa


@pytest.mark.asyncio
async def test_redis_probe(monkeypatch):
    class FakeRedis:
        async def info(self):
            return {"used_memory_human": "12M", "connected_clients": 3, "uptime_in_days": 2}
        async def llen(self, k):
            return 5
        async def dbsize(self):
            return 42

    import app.db.redis as rmod
    async def fake_get_redis():
        return FakeRedis()
    monkeypatch.setattr(rmod, "get_redis", fake_get_redis)

    r = await bi._redis()
    assert r["ok"] is True
    assert r["fila_celery"] == 5
    assert r["total_chaves"] == 42
    assert r["clientes_conectados"] == 3


@pytest.mark.asyncio
async def test_redis_nao_configurado(monkeypatch):
    import app.db.redis as rmod
    async def sem_redis():
        return None
    monkeypatch.setattr(rmod, "get_redis", sem_redis)
    r = await bi._redis()
    assert r["ok"] is False and r["configured"] is False


@pytest.mark.asyncio
async def test_celery_sem_broker_degrada():
    # Sem worker/broker no ambiente de teste → nunca lança, retorna ok=False.
    c = await bi._celery()
    assert c["ok"] is False
    assert c["workers"] == 0


@pytest.mark.asyncio
async def test_jobs_expoe_detalhe_do_erro_de_sync_run(monkeypatch):
    """Fase 136 — SyncRun.stats já gravava o erro real (fonte_detalhe), mas
    _jobs() só selecionava fonte/tipo/status/started_at — o painel Cérebro
    mostrava "ERRO" sem nenhuma pista do que aconteceu."""
    import datetime as dt_mod

    class _Row:
        def __init__(self, fonte, tipo, status, started_at, stats):
            self.fonte = fonte
            self.tipo = tipo
            self.status = status
            self.started_at = started_at
            self.stats = stats

    started = dt_mod.datetime(2026, 7, 31, 8, 42, 28, tzinfo=dt_mod.timezone.utc)

    class _AgentRunResult:
        def all(self_inner):
            return []  # sem AgentRun nas últimas 24h, irrelevante pro teste

    class _SyncRunResult:
        def all(self_inner):
            return [
                _Row("comunica+datajud", "CAPTURA", "ERRO", started,
                     {"fonte_detalhe": "HTTP 403 da Comunica/DJEN"}),
                _Row("datajud", "POLLING", "OK", started, {}),
            ]

    class _FakeSession:
        def __init__(self):
            self._calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def execute(self, stmt):
            self._calls += 1
            return _AgentRunResult() if self._calls == 1 else _SyncRunResult()

    import app.db.base as dbbase
    monkeypatch.setattr(dbbase, "AsyncSessionLocal", lambda: _FakeSession())

    jobs = await bi._jobs()

    assert jobs["ok"] is True
    runs = jobs["sync_runs_recentes"]
    assert runs[0]["detalhe"] == "HTTP 403 da Comunica/DJEN"
    assert runs[1]["detalhe"] is None  # sem fonte_detalhe → None, não quebra


@pytest.mark.asyncio
async def test_coletar_infra_agrega_sem_lancar():
    snap = await bi.coletar_infra()
    assert {"celery", "redis", "qdrant", "postgres_pool", "jobs", "coleta_ms"} <= set(snap)
    assert isinstance(snap["coleta_ms"], int)


def test_postgres_pool_retorna_dict():
    p = bi._postgres_pool()
    assert "ok" in p


def test_mapa_estrutura():
    m = construir_mapa()
    assert m["nos"] and m["arestas"] and "resumo" in m
    grupos = {n["grupo"] for n in m["nos"]}
    assert {"api", "agentes", "infra", "integracoes"} <= grupos
    # o nó Celery deve carregar a chave de saúde p/ o frontend colorir
    assert any(n.get("saude_key") == "celery" for n in m["nos"])
    # toda aresta referencia nós existentes
    ids = {n["id"] for n in m["nos"]}
    for a in m["arestas"]:
        assert a["de"] in ids and a["para"] in ids
