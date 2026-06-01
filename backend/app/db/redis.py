import redis.asyncio as aioredis
from app.config import settings

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
