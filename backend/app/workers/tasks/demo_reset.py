"""Task Celery: reset periódico do tenant público de demonstração (Fase 199).

Roda diariamente via Beat, chamando `app.services.demo_reset.resetar_tenant_demo`
— apaga tudo que foi gerado no tenant demo desde o último reset e re-semeia o
conjunto fictício original. Mesmo molde de `app/workers/tasks/approval_reaper.py`
(lock distribuído + time_limit/soft_time_limit + retry)."""
import structlog

from app.workers.worker import celery_app

log = structlog.get_logger()


@celery_app.task(
    name="app.workers.tasks.demo_reset.resetar_tenant_demo_periodico", bind=True, max_retries=3,
    time_limit=180, soft_time_limit=150,
)
def resetar_tenant_demo_periodico(self):
    """Executa `resetar_tenant_demo()` — roda via Beat."""
    from app.workers.async_utils import run_worker_coro

    async def _run():
        from app.db.base import AsyncSessionLocal
        from app.services.demo_reset import resetar_tenant_demo

        async with AsyncSessionLocal() as db:
            return await resetar_tenant_demo(db)

    async def _run_with_lock():
        from app.workers.task_lock import TaskLock

        lock = TaskLock("resetar_tenant_demo_periodico", ttl_seconds=170)
        if not await lock.acquire():
            log.info("task_skipped_lock_held", task="resetar_tenant_demo_periodico")
            return {"skipped": True, "reason": "lock_held"}
        try:
            return await _run()
        finally:
            await lock.release()

    try:
        return run_worker_coro(_run_with_lock())
    except Exception as exc:
        log.error("demo_reset_task_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=60)
