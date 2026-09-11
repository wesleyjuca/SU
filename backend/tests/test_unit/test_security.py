"""Unit tests para hashing de senha (bcrypt direto, sem passlib)."""
import pytest

import app.core.security as security_mod
from app.core.security import hash_password, is_token_blacklisted, verify_password


def test_hash_verify_roundtrip():
    h = hash_password("Admin@123")
    assert h.startswith("$2b$")          # formato bcrypt, compatível com hashes legados
    assert verify_password("Admin@123", h) is True


def test_verify_rejects_wrong_password():
    h = hash_password("Admin@123")
    assert verify_password("errada", h) is False


def test_verify_malformed_hash_returns_false_not_raises():
    # hash inválido no banco deve virar 401 legítimo, nunca 500
    assert verify_password("qualquer", "nao-e-um-hash-bcrypt") is False


def test_long_password_is_truncated_not_error():
    # bcrypt 5.x levanta em >72 bytes; hash_password deve truncar com segurança
    h = hash_password("x" * 200)
    assert verify_password("x" * 200, h) is True


# ─── is_token_blacklisted — fail-open, mas não mais silencioso num erro real ──

class _FakeRedisOK:
    def __init__(self, existe: bool):
        self._existe = existe

    async def exists(self, key):
        return self._existe


class _FakeRedisQuebrado:
    async def exists(self, key):
        raise ConnectionError("redis fora do ar")


@pytest.mark.asyncio
async def test_sem_redis_configurado_devolve_false_sem_logar(monkeypatch):
    """Estado degradado documentado (REDIS_URL vazio) — get_redis() já devolve
    None por conta própria. Continua silencioso: não é uma falha, é config."""
    eventos = []
    monkeypatch.setattr(security_mod.log, "warning", lambda *a, **kw: eventos.append((a, kw)))

    async def _get_redis_none():
        return None

    monkeypatch.setattr("app.db.redis.get_redis", _get_redis_none)

    assert await is_token_blacklisted("algum-jti") is False
    assert eventos == []


@pytest.mark.asyncio
async def test_token_na_blacklist_e_detectado(monkeypatch):
    async def _get_redis_ok():
        return _FakeRedisOK(existe=True)

    monkeypatch.setattr("app.db.redis.get_redis", _get_redis_ok)

    assert await is_token_blacklisted("jti-revogado") is True


@pytest.mark.asyncio
async def test_erro_real_do_redis_e_logado_mas_continua_fail_open(monkeypatch):
    """Achado da rodada pós-166a43c: antes, um erro de verdade na chamada
    `.exists()` (Redis configurado mas indisponível/timeout) caía no mesmo
    `except Exception: pass` do caso "sem Redis" — indistinguível, sem log.
    Prova nos dois sentidos: reverter o fix faz `eventos` continuar vazio."""
    eventos = []
    monkeypatch.setattr(security_mod.log, "warning", lambda *a, **kw: eventos.append((a, kw)))

    async def _get_redis_quebrado():
        return _FakeRedisQuebrado()

    monkeypatch.setattr("app.db.redis.get_redis", _get_redis_quebrado)

    # Comportamento preservado — continua fail-open, nunca derruba o request.
    assert await is_token_blacklisted("algum-jti") is False
    # Mas agora o erro real fica visível, ao contrário do caso "sem Redis".
    assert len(eventos) == 1
    args, kwargs = eventos[0]
    assert args[0] == "blacklist_check_failed"
    assert "error" in kwargs


@pytest.mark.asyncio
async def test_get_redis_falhando_tambem_e_logado(monkeypatch):
    """`get_redis()` em si pode levantar (ex.: `from_url` mal configurado) —
    também precisa ficar visível, não só o `.exists()`."""
    eventos = []
    monkeypatch.setattr(security_mod.log, "warning", lambda *a, **kw: eventos.append((a, kw)))

    async def _get_redis_explode():
        raise RuntimeError("configuração inválida")

    monkeypatch.setattr("app.db.redis.get_redis", _get_redis_explode)

    assert await is_token_blacklisted("algum-jti") is False
    assert len(eventos) == 1
    assert eventos[0][0][0] == "blacklist_check_redis_unavailable"
