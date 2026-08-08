"""Task Celery: polling de todos os processos ativos."""
from app.workers.worker import celery_app
import structlog

log = structlog.get_logger()


@celery_app.task(
    name="app.workers.tasks.process_polling.poll_all_processes", bind=True, max_retries=3,
    time_limit=1500, soft_time_limit=1200,
)
def poll_all_processes(self):
    """Executa polling batch de processos — roda a cada 30 minutos via Beat."""
    from app.workers.async_utils import run_worker_coro

    async def _run():
        from app.db.base import AsyncSessionLocal
        from app.agents.process.process_agent import ProcessAgent
        from app.agents.brain.context import AgentContext
        from app.workers.task_lock import TaskLock

        lock = TaskLock("poll_all_processes", ttl_seconds=1800)
        if not await lock.acquire():
            log.info("task_skipped_lock_held", task="poll_all_processes")
            return {"skipped": True, "reason": "lock_held"}
        try:
            async with AsyncSessionLocal() as db:
                agent = ProcessAgent(db=db)
                ctx = AgentContext(task_type="poll_all", task_input={"action": "poll_all"})
                result = await agent.run(ctx)
                log.info("process_poll_complete", status=result.status, output=result.output)
                return result.output
        finally:
            await lock.release()

    try:
        return run_worker_coro(_run())
    except Exception as exc:
        log.error("process_poll_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=60)
