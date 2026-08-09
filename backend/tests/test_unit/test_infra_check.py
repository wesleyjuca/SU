"""Fase 164 — alerta proativo de infra pro Cérebro. Antes, `coletar_infra()`
só rodava quando um SUPERADMIN abria a aba manualmente; a nova task
periódica reaproveita o fan-out `create_batch` (mesmo padrão de
`custom_agents.py`) e notifica só na TRANSIÇÃO de estado (debounce via
Redis), nunca a cada tick enquanto o problema persiste."""
import uuid

import pytest

from app.workers.tasks.infra_check import _checks_de, executar_infra_check


def _infra_base(celery_ok=True, redis_configured=True, redis_ok=True,
                 qdrant_configured=True, qdrant_ok=True, fontes=None):
    return {
        "celery": {"ok": celery_ok},
        "redis": {"ok": redis_ok, "configured": redis_configured},
        "qdrant": {"ok": qdrant_ok, "configured": qdrant_configured},
        "postgres_pool": {"ok": True},
        "jobs": {"ok": True},
        "fontes": {"ok": True, "fontes": fontes or []},
    }


def test_checks_de_ignora_redis_qdrant_nao_configurados():
    infra = _infra_base(redis_configured=False, qdrant_configured=False)
    checks = _checks_de(infra)
    chaves = [c[0] for c in checks]
    assert "redis" not in chaves
    assert "qdrant" not in chaves
    assert "celery" in chaves


def test_checks_de_marca_celery_quebrado():
    infra = _infra_base(celery_ok=False)
    checks = _checks_de(infra)
    (chave, quebrado, label) = next(c for c in checks if c[0] == "celery")
    assert quebrado is True
    assert "Celery" in label


def test_checks_de_inclui_fonte_com_breaker_aberto():
    infra = _infra_base(fontes=[
        {"nome": "comunica", "breaker": "OPEN"},
        {"nome": "datajud", "breaker": "CLOSED"},
    ])
    checks = _checks_de(infra)
    por_chave = {c[0]: c[1] for c in checks}
    assert por_chave["fonte:comunica"] is True
    assert por_chave["fonte:datajud"] is False


class _FakeRedis:
    def __init__(self):
        self._store = {}

    async def get(self, key):
        return self._store.get(key)

    async def set(self, key, value, ex=None):
        self._store[key] = value
        return True


class _FakeScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _FakeResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return _FakeScalars(self._items)


class _FakeDB:
    def __init__(self, superadmin_ids):
        self._superadmin_ids = superadmin_ids
        self.commits = 0

    async def execute(self, _stmt):
        return _FakeResult(self._superadmin_ids)

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_transicao_ok_para_broken_dispara_alerta_e_persiste_estado(monkeypatch):
    fake_redis = _FakeRedis()
    superadmin_id = uuid.uuid4()
    db = _FakeDB([superadmin_id])
    disparos = []

    async def _fake_coletar_infra():
        return _infra_base(celery_ok=False)

    async def _fake_get_redis():
        return fake_redis

    async def _fake_create_batch(_db, user_ids, titulo, tipo, corpo, priority, link):
        disparos.append({"user_ids": user_ids, "titulo": titulo, "tipo": tipo, "priority": priority})
        return len(user_ids)

    monkeypatch.setattr("app.services.brain_infra.coletar_infra", _fake_coletar_infra)
    monkeypatch.setattr("app.db.redis.get_redis", _fake_get_redis)
    monkeypatch.setattr("app.services.notification.create_batch", _fake_create_batch)

    resultado = await executar_infra_check(db)

    assert resultado["alertas"] == 1
    assert resultado["normalizacoes"] == 0
    assert disparos[0]["tipo"] == "INFRA_ALERTA"
    assert disparos[0]["priority"] == "ALTA"
    assert disparos[0]["user_ids"] == [superadmin_id]
    assert fake_redis._store["infra_alert_state:celery"] == "broken"


@pytest.mark.asyncio
async def test_estado_ja_broken_nao_reenvia_alerta_no_tick_seguinte(monkeypatch):
    fake_redis = _FakeRedis()
    fake_redis._store["infra_alert_state:celery"] = "broken"
    db = _FakeDB([uuid.uuid4()])
    disparos = []

    async def _fake_coletar_infra():
        return _infra_base(celery_ok=False)

    async def _fake_get_redis():
        return fake_redis

    async def _fake_create_batch(*a, **kw):
        disparos.append(1)
        return 1

    monkeypatch.setattr("app.services.brain_infra.coletar_infra", _fake_coletar_infra)
    monkeypatch.setattr("app.db.redis.get_redis", _fake_get_redis)
    monkeypatch.setattr("app.services.notification.create_batch", _fake_create_batch)

    resultado = await executar_infra_check(db)

    assert resultado["alertas"] == 0
    assert resultado["normalizacoes"] == 0
    assert disparos == []


@pytest.mark.asyncio
async def test_transicao_broken_para_ok_dispara_normalizacao(monkeypatch):
    fake_redis = _FakeRedis()
    fake_redis._store["infra_alert_state:celery"] = "broken"
    db = _FakeDB([uuid.uuid4()])
    disparos = []

    async def _fake_coletar_infra():
        return _infra_base(celery_ok=True)

    async def _fake_get_redis():
        return fake_redis

    async def _fake_create_batch(_db, user_ids, titulo, tipo, corpo, priority, link):
        disparos.append({"titulo": titulo, "priority": priority})
        return len(user_ids)

    monkeypatch.setattr("app.services.brain_infra.coletar_infra", _fake_coletar_infra)
    monkeypatch.setattr("app.db.redis.get_redis", _fake_get_redis)
    monkeypatch.setattr("app.services.notification.create_batch", _fake_create_batch)

    resultado = await executar_infra_check(db)

    assert resultado["alertas"] == 0
    assert resultado["normalizacoes"] == 1
    assert "normalizada" in disparos[0]["titulo"]
    assert disparos[0]["priority"] == "NORMAL"
    assert fake_redis._store["infra_alert_state:celery"] == "ok"


@pytest.mark.asyncio
async def test_sem_redis_pula_fan_out_inteiro_em_vez_de_notificar_a_cada_tick(monkeypatch):
    db = _FakeDB([uuid.uuid4()])
    disparos = []

    async def _fake_coletar_infra():
        return _infra_base(celery_ok=False)

    async def _fake_get_redis_none():
        return None

    async def _fake_create_batch(*a, **kw):
        disparos.append(1)
        return 1

    monkeypatch.setattr("app.services.brain_infra.coletar_infra", _fake_coletar_infra)
    monkeypatch.setattr("app.db.redis.get_redis", _fake_get_redis_none)
    monkeypatch.setattr("app.services.notification.create_batch", _fake_create_batch)

    resultado = await executar_infra_check(db)

    assert resultado["sem_redis"] is True
    assert disparos == []
