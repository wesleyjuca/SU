"""Contador de rate limit — a chave PRECISA sempre ter TTL.

Contexto do bug que estes testes fecham: os 4 pontos de rate limit do projeto
(`core/middleware.py` e os três de `api/v1/auth.py`) faziam

    n = await redis.incr(chave)
    if n == 1:
        await redis.expire(chave, janela)

O `expire` só era tentado na PRIMEIRA requisição. Se falhasse — processo morto
entre as duas chamadas, erro de rede, exceção engolida — a chave ficava sem
expiração para sempre, o contador crescia sem teto e o usuário recebia 429
indefinidamente, sem nenhum caminho de reparo no código.

Não é hipótese: durante a fase que introduziu estes testes, a chave
`ratelimit:auth:127.0.0.1` foi encontrada no Redis local com valor **463** e
**TTL=-1**, contra um teto de 10/min — travando todo login da suíte.

Cobertura anterior desta área: praticamente nenhuma. `test_middleware_ratelimit.py`
só exercitava lógica pura (casamento de path, identificador do usuário), sem
Redis e sem 429.
"""
import pytest

from app.db.redis import get_redis, incrementar_com_janela


async def _redis_e_chave(sufixo: str):
    """Devolve `(redis, chave)` com a chave já limpa.

    O pool do Redis é singleton de módulo (`app/db/redis.py::_redis_pool`),
    exatamente como era o engine do Postgres — uma conexão criada no loop de
    um teste e reusada no loop do teste seguinte estoura "attached to a
    different loop". Por isso aqui o pool é descartado e recriado a cada
    teste: a conexão nasce e morre dentro do mesmo loop.

    (A app em produção não tem esse problema: um único loop, pool
    compartilhado é justamente o que se quer.)"""
    import app.db.redis as redis_mod

    if redis_mod._redis_pool is not None:
        try:
            await redis_mod._redis_pool.aclose()
        except Exception:
            pass
        redis_mod._redis_pool = None

    redis = await get_redis()
    if redis is None:
        pytest.skip("REDIS_URL não configurado neste ambiente")
    chave = f"teste:rate_limit:{sufixo}"
    await redis.delete(chave)
    return redis, chave


@pytest.mark.asyncio
async def test_primeira_chamada_ja_cria_a_chave_com_ttl():
    redis_real, chave = await _redis_e_chave("nasce_com_ttl")
    n = await incrementar_com_janela(redis_real, chave, 60)

    assert n == 1
    ttl = await redis_real.ttl(chave)
    assert 0 < ttl <= 60, f"chave nasceu sem expiração (TTL={ttl})"


@pytest.mark.asyncio
async def test_chave_ja_travada_sem_ttl_se_cura_sozinha():
    """O caso observado em produção/local: chave existente, contador alto e
    TTL=-1 (eterna). O código antigo nunca mais tentava `expire` — só o fazia
    quando o contador valia 1, e ele nunca mais valeria 1. A chave ficava
    travada até alguém apagar à mão no Redis.

    Aqui a expiração é reaplicada em QUALQUER incremento que encontre TTL
    ausente, então a próxima requisição do usuário já destrava o estado."""
    redis_real, chave = await _redis_e_chave("travada")
    await redis_real.set(chave, 463)  # sem `ex=` — exatamente o estado quebrado
    assert await redis_real.ttl(chave) == -1  # confirma o estado ruim antes

    n = await incrementar_com_janela(redis_real, chave, 60)

    assert n == 464
    ttl = await redis_real.ttl(chave)
    assert 0 < ttl <= 60, f"chave continuou eterna (TTL={ttl}) — o bug voltou"


@pytest.mark.asyncio
async def test_incrementos_seguintes_nao_reiniciam_a_janela():
    """Reaplicar o TTL a cada chamada seria outro bug: a janela nunca
    fecharia enquanto o usuário insistisse, e um atacante manteria a própria
    punição eterna (ou, pior, a janela de um usuário legítimo). O TTL só é
    tocado quando está ausente."""
    redis_real, chave = await _redis_e_chave("janela")
    await incrementar_com_janela(redis_real, chave, 60)
    ttl_inicial = await redis_real.ttl(chave)

    await redis_real.expire(chave, 5)  # simula a janela quase no fim
    await incrementar_com_janela(redis_real, chave, 60)

    ttl_depois = await redis_real.ttl(chave)
    assert ttl_depois <= 5, (
        f"a janela foi reiniciada (era 5s, virou {ttl_depois}s) — o contador "
        f"nunca expiraria sob tráfego contínuo"
    )
    assert ttl_inicial > 0


@pytest.mark.asyncio
async def test_falha_de_redis_devolve_none_para_o_chamador_deixar_passar():
    """Fail-open: indisponibilidade de Redis nunca pode derrubar requisição
    (mesmo princípio de `workers/task_lock.py`). O contrato é devolver `None`
    — "sem informação" — e não zero, que o chamador poderia confundir com uma
    contagem legítima."""

    class _RedisQuebrado:
        def pipeline(self, transaction=True):
            raise ConnectionError("redis fora do ar")

    assert await incrementar_com_janela(_RedisQuebrado(), "qualquer", 60) is None


@pytest.mark.asyncio
async def test_expire_falhando_nao_derruba_a_contagem():
    """Se o `EXPIRE` falhar, a contagem ainda vale e a requisição segue — a
    próxima chamada vê o TTL ausente e tenta de novo. Sem isto voltaríamos a
    ter um caminho onde a falha do expire é definitiva."""

    redis_real, chave = await _redis_e_chave("expire_quebrado")

    class _ExpireQuebrado:
        def __init__(self, real):
            self._real = real

        def pipeline(self, transaction=True):
            return self._real.pipeline(transaction=transaction)

        async def expire(self, *_args, **_kwargs):
            raise ConnectionError("expire falhou")

    n = await incrementar_com_janela(_ExpireQuebrado(redis_real), chave, 60)
    assert n == 1  # a contagem foi devolvida mesmo com o expire quebrado

    # E a chamada seguinte, com um Redis são, conserta o TTL.
    await incrementar_com_janela(redis_real, chave, 60)
    assert 0 < await redis_real.ttl(chave) <= 60
