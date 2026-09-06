import redis.asyncio as aioredis
import structlog
from app.config import settings

log = structlog.get_logger()

_redis_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis | None:
    """Retorna o pool Redis, ou None se REDIS_URL não estiver configurado.

    Em modo de config mínima (sem Redis), o app degrada graciosamente:
    rate-limit e blacklist de token viram no-ops. Os consumidores checam `if redis:`.
    """
    global _redis_pool
    if not settings.REDIS_URL:
        return None
    if _redis_pool is None:
        try:
            _redis_pool = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                max_connections=20,
            )
        except Exception:
            return None
    return _redis_pool


async def close_redis():
    global _redis_pool
    if _redis_pool:
        await _redis_pool.aclose()
        _redis_pool = None


async def incrementar_com_janela(redis, chave: str, janela_segundos: int) -> int | None:
    """Incrementa um contador de rate limit garantindo que a chave TENHA TTL.

    Substitui o padrão que existia em 4 lugares do projeto:

        n = await redis.incr(chave)
        if n == 1:
            await redis.expire(chave, janela)

    Esse padrão tem uma janela de falha permanente: o `expire` só é tentado
    na PRIMEIRA requisição. Se ele não acontecer — processo morto entre as
    duas chamadas, falha de rede, exceção engolida por um `except: pass` —
    a chave fica **sem expiração para sempre**, o contador cresce sem limite
    e o usuário passa a receber 429 indefinidamente, sem nenhum caminho de
    reparo no código. Não é hipótese: durante esta fase a chave
    `ratelimit:auth:127.0.0.1` foi encontrada com valor 463 e `TTL=-1`,
    bloqueando todo login.

    Aqui o `INCR` e a leitura do `TTL` vão num MULTI/EXEC (um round-trip,
    consistente entre si) e o `EXPIRE` é reaplicado sempre que o TTL estiver
    ausente — não só na primeira vez. Isso torna a função **auto-curável**:
    uma chave que já esteja travada sem TTL (inclusive as criadas pelo código
    antigo) ganha expiração no próximo acesso, em vez de exigir intervenção
    manual no Redis.

    Devolve a contagem, ou `None` se o Redis falhar — o chamador trata `None`
    como "sem informação" e deixa passar (fail-open, mesmo princípio de
    `task_lock.py`: indisponibilidade de Redis nunca derruba a requisição).
    """
    try:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.incr(chave)
            pipe.ttl(chave)
            contagem, ttl = await pipe.execute()
    except Exception as exc:
        log.warning("rate_limit_incr_falhou", chave=chave, erro=str(exc))
        return None

    # TTL negativo = -1 (existe, sem expiração) ou -2 (não existe mais).
    # Nos dois casos reaplicar é correto e barato.
    if ttl is None or int(ttl) < 0:
        try:
            await redis.expire(chave, janela_segundos)
        except Exception as exc:
            # Não é fatal: a próxima chamada vê o TTL ausente e tenta de novo.
            log.warning("rate_limit_expire_falhou", chave=chave, erro=str(exc))

    return int(contagem)
