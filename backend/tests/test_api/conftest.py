"""Fixtures exclusivas dos testes de API (HTTP real via ASGITransport).

Fica separado de `tests/conftest.py` de propósito: a limpeza de rate limit
abaixo só faz sentido para quem faz request HTTP. Quando ela era autouse no
conftest raiz, passava a valer também para `tests/test_unit/` e introduziu ali
uma falha dependente de ordem (`test_chain_resume` passava isolado e falhava em
conjunto) — uma fixture async autouse aplicada a testes que não precisam dela
não é inócua.
"""
import pytest


@pytest.fixture(autouse=True)
async def _limpar_rate_limit():
    """Zera os contadores de rate limit entre testes de API.

    O `ASGITransport` reporta sempre o mesmo IP, então todos os testes
    compartilham a mesma chave `ratelimit:auth:127.0.0.1` — cujo teto é 10
    req/min. Sem esta limpeza a suíte se autobloqueia a partir do 11º login e
    dezenas de testes viram "Login failed", que parece falta de seed e não é.

    Um teste que exercita rate limit de propósito deve marcar
    `@pytest.mark.rate_limit_real` e cuidar da própria limpeza (ver
    `test_demo_login.py`).
    """
    yield
    try:
        from app.db.redis import get_redis
        redis = await get_redis()
        if redis:
            for padrao in ("ratelimit:*", "login_fail:*"):
                chaves = [k async for k in redis.scan_iter(match=padrao)]
                if chaves:
                    await redis.delete(*chaves)
    except Exception:
        pass  # limpeza é conveniência; nunca deve derrubar um teste
