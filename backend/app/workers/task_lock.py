"""Fase 147 — lock distribuído leve pras tasks agendadas do Celery Beat.

Nenhum job periódico deste projeto tem hoje proteção contra 2 execuções
concorrentes do MESMO job (disparo manual + Beat quase simultâneo,
redelivery, ou um worker travado além do time_limit que o Beat dispara de
novo antes do anterior morrer). `TaskLock` fecha isso via SET NX EX no
Redis — fail-open (nunca bloqueia) sem `REDIS_URL` configurado, mesmo
espírito de degradação graciosa do resto do sistema.
"""
import uuid

import structlog

from app.db.redis import get_redis

log = structlog.get_logger()


class TaskLock:
    """Uso: `lock = TaskLock("nome_curto", ttl_seconds=N)`, depois
    `if not await lock.acquire(): return` e `await lock.release()` num
    `finally` ao término da execução."""

    def __init__(self, name: str, ttl_seconds: int):
        self.key = f"task_lock:{name}"
        self.ttl_seconds = ttl_seconds
        self.token = str(uuid.uuid4())
        self._acquired = False

    async def acquire(self) -> bool:
        try:
            redis = await get_redis()
        except Exception as exc:
            log.warning("task_lock_acquire_failed", key=self.key, error=str(exc))
            return True  # fail-open — nunca bloqueia por falta/falha de Redis
        if not redis:
            return True
        try:
            ok = await redis.set(self.key, self.token, nx=True, ex=self.ttl_seconds)
        except Exception as exc:
            log.warning("task_lock_acquire_failed", key=self.key, error=str(exc))
            return True
        self._acquired = bool(ok)
        return self._acquired

    async def release(self) -> None:
        if not self._acquired:
            return
        try:
            redis = await get_redis()
            if not redis:
                return
            # Só apaga se o token bater — evita apagar o lock de uma
            # execução SEGUINTE que já pegou depois do TTL desta expirar
            # (cenário real se esta execução travou além do próprio
            # time_limit do Celery).
            current = await redis.get(self.key)
            if current == self.token:
                await redis.delete(self.key)
        except Exception as exc:
            log.warning("task_lock_release_failed", key=self.key, error=str(exc))
