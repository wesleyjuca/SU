"""Task Celery: reaper de `SyncRun` travados em RUNNING (Fase 167).

O try/except em volta dos loops de sincronização (jurisprudencia_sync.py,
legislacao_sync.py, google_drive_sync.py, oab_capture.py, dje_monitor.py)
cobre toda falha que levanta uma exceção Python de verdade — mas não cobre
o cenário catastrófico do processo worker morrer no meio da execução (OOM
kill, `kill -9`, container evictado): nesse caso não há pilha pra
desenrolar, nenhum `except` roda, e o `SyncRun` fica "RUNNING" pra sempre
no Postgres, mesmo o worker já tendo desaparecido há muito tempo. Este
reaper varre periodicamente por esses casos residuais e os marca como
ERRO — puramente uma rede de segurança, não deveria disparar na operação
normal (onde o try/except já cobre o resto)."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
import structlog

from app.workers.worker import celery_app

log = structlog.get_logger()

# Folga generosa acima do maior time_limit das tasks de sync (2h do
# sync_google_drive_doutrina, Fase 147) — só marca como travado o que
# sobrou rodando bem além de qualquer execução legítima, mesmo child.
LIMITE_HORAS_PADRAO = 4


async def executar_reaper_syncs(db, limite_horas: int = LIMITE_HORAS_PADRAO) -> dict:
    """Marca como ERRO todo `SyncRun` ainda RUNNING além do limite. Idempotente
    — rodar de novo não retoca runs já finalizados (OK/ERRO)."""
    from app.models.sync_run import SyncRun

    cutoff = datetime.now(timezone.utc) - timedelta(hours=limite_horas)
    travados = (await db.execute(
        select(SyncRun.id).where(SyncRun.status == "RUNNING", SyncRun.started_at < cutoff)
    )).scalars().all()

    if travados:
        agora = datetime.now(timezone.utc)
        await db.execute(
            update(SyncRun)
            .where(SyncRun.id.in_(travados))
            .values(
                status="ERRO",
                finished_at=agora,
                stats={"erro": "marcado como travado pelo reaper — processo provavelmente morto sem sinalizar"},
            )
        )
        await db.commit()
        log.warning("sync_runs_reapeados", quantidade=len(travados))

    return {"marcados_travados": len(travados)}


@celery_app.task(
    name="app.workers.tasks.sync_reaper.reapear_syncs_travados_periodico", bind=True, max_retries=3,
    time_limit=120, soft_time_limit=90,
)
def reapear_syncs_travados_periodico(self):
    """Executa `executar_reaper_syncs()` — roda via Beat a cada 30min."""
    from app.workers.async_utils import run_worker_coro

    async def _run():
        from app.db.base import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            return await executar_reaper_syncs(db)

    async def _run_with_lock():
        from app.workers.task_lock import TaskLock

        lock = TaskLock("reapear_syncs_travados", ttl_seconds=280)
        if not await lock.acquire():
            log.info("task_skipped_lock_held", task="reapear_syncs_travados")
            return {"skipped": True, "reason": "lock_held"}
        try:
            return await _run()
        finally:
            await lock.release()

    try:
        return run_worker_coro(_run_with_lock())
    except Exception as exc:
        log.error("sync_reaper_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=60)
