"""Task Celery: descoberta automática periódica de processos novos por OAB
(Fase 194). `capturar_por_oab()` (app/services/oab_capture.py) já existe e
funciona desde a Fase 73/102 — dedup idempotente por numero_cnj, registra
SyncRun — mas só disparava manualmente (POST /oabs/capturar) ou por agente
sob demanda; nenhuma entrada no beat_schedule automatizava a descoberta.
Mesma função, só automatiza o disparo por tenant — não mexe nos conectores
credenciados (Jusbrasil/Escavador), que continuam só para enriquecimento
sob demanda (puxar esses pra descoberta ativa é uma decisão de custo/
rate-limit maior, fora de escopo aqui)."""
import uuid

from sqlalchemy import select
import structlog

from app.workers.worker import celery_app

log = structlog.get_logger()

# Janela retroativa menor que a captura manual (365 dias, 1ª varredura) —
# rodando diariamente, comunicações novas aparecem em poucos dias; uma
# janela grande a cada rodada só re-varreria o que a dedup por numero_cnj
# já descartaria, sem necessidade real.
DIAS_RETRO_PERIODICO = 14


async def executar_descoberta_por_oab(db) -> dict:
    """Roda `capturar_por_oab()` pra cada tenant ativo — fail-soft por
    tenant (um escritório sem OAB configurada, ou cuja captura falhe, não
    impede a descoberta dos demais). `capturar_por_oab` já é um no-op
    barato pra tenants sem nenhuma OAB monitorada."""
    from app.models.tenant import Tenant
    from app.services.oab_capture import capturar_por_oab

    tenant_ids: list[uuid.UUID] = (await db.execute(
        select(Tenant.id).where(Tenant.is_active == True)  # noqa: E712
    )).scalars().all()

    tenants_com_oab = 0
    total_criados = 0
    for tenant_id in tenant_ids:
        try:
            resultado = await capturar_por_oab(db, tenant_id, dias_retro=DIAS_RETRO_PERIODICO)
        except Exception as exc:
            log.warning("oab_discovery_tenant_falhou", tenant_id=str(tenant_id), error=str(exc))
            continue
        if resultado.get("oabs"):
            tenants_com_oab += 1
            total_criados += resultado.get("processos_criados", 0)

    stats = {
        "tenants_verificados": len(tenant_ids),
        "tenants_com_oab": tenants_com_oab,
        "processos_criados": total_criados,
    }
    log.info("oab_discovery_complete", **stats)
    return stats


@celery_app.task(
    name="app.workers.tasks.oab_discovery.descobrir_processos_por_oab_periodico", bind=True, max_retries=3,
    time_limit=3600, soft_time_limit=3300,
)
def descobrir_processos_por_oab_periodico(self):
    """Executa `executar_descoberta_por_oab()` — roda via Beat (diário)."""
    from app.workers.async_utils import run_worker_coro

    async def _run():
        from app.db.base import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            return await executar_descoberta_por_oab(db)

    async def _run_with_lock():
        from app.workers.task_lock import TaskLock

        lock = TaskLock("descobrir_processos_por_oab", ttl_seconds=3900)
        if not await lock.acquire():
            log.info("task_skipped_lock_held", task="descobrir_processos_por_oab")
            return {"skipped": True, "reason": "lock_held"}
        try:
            return await _run()
        finally:
            await lock.release()

    try:
        return run_worker_coro(_run_with_lock())
    except Exception as exc:
        log.error("oab_discovery_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=300)
