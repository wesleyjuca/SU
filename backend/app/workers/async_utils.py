"""Utilitários para execução de corrotinas dentro de tasks Celery."""
import asyncio

import structlog

log = structlog.get_logger()


def run_worker_coro(coro):
    """Roda uma corrotina em um event loop dedicado e descarta o pool do engine
    e do cliente Redis ao fim.

    Cada task Celery cria um novo loop via asyncio.run(); sem descartar os
    pools, uma conexão (asyncpg OU o cliente `redis.asyncio`) reutilizada na
    task seguinte fica presa ao loop anterior (já fechado) → 'got Future
    attached to a different loop' / 'Event loop is closed'. Chamar
    engine.dispose() + close_redis() ao término garante que nenhuma conexão
    sobreviva ao loop que a criou. Roda apenas no processo worker (a API
    nunca executa estas tasks).

    Achado real de produção (log real, `task_lock_acquire_failed
    error=Event loop is closed`): o cliente Redis global
    (`app/db/redis.py::_redis_pool`) sofria exatamente a mesma classe de bug
    já corrigida aqui só para o engine asyncpg — a task ainda terminava com
    sucesso (fail-open em `TaskLock.acquire()`), mas o warning era ruído
    evitável a cada execução seguinte no mesmo processo worker.
    """
    async def _runner():
        try:
            return await coro
        finally:
            from app.db.base import engine
            from app.db.redis import close_redis
            await engine.dispose()
            try:
                await close_redis()
            except Exception as exc:
                # Fail-soft: a conexão pode já estar rompida pelo loop
                # anterior fechado — não deixar isso mascarar o resultado
                # (ou uma exceção real) da task que acabou de rodar.
                log.warning("run_worker_coro_close_redis_falhou", error=str(exc))

    return asyncio.run(_runner())
