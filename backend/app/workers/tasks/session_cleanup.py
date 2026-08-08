"""Task Celery: limpeza de sessões expiradas (Fase 116).

Sessões nunca são removidas quando expiram sem logout explícito (usuário
fecha o navegador) — a linha em `sessions` fica pra sempre. Em volume baixo
de usuários (equipe de escritório) isso não é um risco de volume relevante,
mas é uma faxina de baixo esforço e sem risco.
"""
from app.workers.worker import celery_app
import structlog

log = structlog.get_logger()


@celery_app.task(
    name="app.workers.tasks.session_cleanup.cleanup_expired_sessions", bind=True,
    time_limit=600, soft_time_limit=480,
)
def cleanup_expired_sessions(self):
    """Remove sessões com expires_at no passado."""
    from app.workers.async_utils import run_worker_coro

    async def _run():
        from datetime import datetime, timezone
        from sqlalchemy import delete
        from app.db.base import AsyncSessionLocal
        from app.models.user import Session

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                delete(Session).where(Session.expires_at < datetime.now(timezone.utc))
            )
            await db.commit()
            log.info("sessions_cleanup", removidas=result.rowcount)
            return {"removidas": result.rowcount}

    async def _run_with_lock():
        from app.workers.task_lock import TaskLock

        lock = TaskLock("cleanup_expired_sessions", ttl_seconds=900)
        if not await lock.acquire():
            log.info("task_skipped_lock_held", task="cleanup_expired_sessions")
            return {"skipped": True, "reason": "lock_held"}
        try:
            return await _run()
        finally:
            await lock.release()

    return run_worker_coro(_run_with_lock())
