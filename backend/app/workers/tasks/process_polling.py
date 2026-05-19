"""Task Celery: polling de todos os processos ativos."""
from app.workers.worker import celery_app
import structlog

log = structlog.get_logger()


@celery_app.task(name="app.workers.tasks.process_polling.poll_all_processes", bind=True, max_retries=3)
def poll_all_processes(self):
    """Executa polling batch de processos — roda a cada 30 minutos via Beat."""
    import asyncio

    async def _run():
        from app.db.base import AsyncSessionLocal
        from app.agents.process.process_agent import ProcessAgent
        from app.agents.brain.context import AgentContext

        async with AsyncSessionLocal() as db:
            agent = ProcessAgent(db=db)
            ctx = AgentContext(task_type="poll_all", task_input={"action": "poll_all"})
            result = await agent.run(ctx)
            log.info("process_poll_complete", status=result.status, output=result.output)
            return result.output

    try:
        return asyncio.run(_run())
    except Exception as exc:
        log.error("process_poll_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=60)
