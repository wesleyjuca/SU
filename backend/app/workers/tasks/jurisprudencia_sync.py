"""Task Celery: sincronização diária de jurisprudência do STJ (Fase 138.1).

Processa só o lote mais recente disponível no portal por execução — nunca um
backfill histórico completo dentro do beat automático (um backfill manual,
sob demanda e com teto explícito, é uma ação separada, fora de escopo desta
fase). Sem credencial nenhuma necessária — fonte pública, sem tenant."""
from datetime import datetime, timezone
from sqlalchemy import select
import structlog

from app.workers.worker import celery_app

log = structlog.get_logger()


async def executar_sync_stj(db) -> dict:
    """Lógica de sincronização, separada do wrapper Celery pra ser
    testável/chamável diretamente com uma sessão real. Fail-soft por
    documento (uma decisão malformada não derruba as demais)."""
    from app.models.jurisprudencia_ingerida import JurisprudenciaIngerida
    from app.integrations.jurisprudencia.stj_client import buscar_lote_recente
    from app.rag.ingestion import ingest_document
    from app.services.movements_import import iniciar_sync, finalizar_sync

    run = await iniciar_sync(db, tenant_id=None, fonte="stj_dados_abertos", tipo="INGESTAO")

    processados = 0
    pulados = 0
    falhas = 0
    try:
        registros = await buscar_lote_recente()
    except Exception as exc:
        log.error("stj_sync_busca_falhou", error=str(exc))
        stats = {"processados": 0, "pulados": 0, "falhas": 0, "erro": str(exc)[:300]}
        await finalizar_sync(db, run, "ERRO", stats)
        await db.commit()
        raise

    for reg in registros:
        fonte_documento_id = reg.get("fonte_documento_id")
        if not fonte_documento_id:
            continue
        existe = (await db.execute(
            select(JurisprudenciaIngerida).where(
                JurisprudenciaIngerida.fonte == "stj_dados_abertos",
                JurisprudenciaIngerida.fonte_documento_id == fonte_documento_id,
            )
        )).scalar_one_or_none()
        if existe:
            pulados += 1
            continue

        metadata_extraida = {
            k: v for k, v in reg.items() if k not in ("texto", "fonte_documento_id") and v
        }
        entrada = JurisprudenciaIngerida(
            fonte="stj_dados_abertos",
            fonte_documento_id=fonte_documento_id,
            collection_alvo="jurisprudencia",
            metadata_extraida=metadata_extraida,
            status="PENDENTE",
        )
        db.add(entrada)
        await db.flush()

        try:
            qdrant_metadata = {"tribunal": "STJ", **metadata_extraida}
            await ingest_document(
                content=reg["texto"], collection="jurisprudencia",
                metadata=qdrant_metadata, document_id=fonte_documento_id,
            )
            entrada.status = "EMBEDDED"
            processados += 1
        except Exception as exc:
            entrada.status = "FALHOU"
            entrada.erro = str(exc)[:500]
            falhas += 1
            log.warning("stj_ingest_falhou", fonte_documento_id=fonte_documento_id, error=str(exc))
        entrada.processed_at = datetime.now(timezone.utc)
        await db.commit()

    stats = {"processados": processados, "pulados": pulados, "falhas": falhas}
    await finalizar_sync(db, run, "OK", stats)
    await db.commit()
    log.info("stj_sync_complete", **stats)
    return stats


@celery_app.task(name="app.workers.tasks.jurisprudencia_sync.sync_stj_diario", bind=True, max_retries=3)
def sync_stj_diario(self):
    """Executa `executar_sync_stj()` — roda via Beat, re-tenta se a task
    inteira falhar (ex.: DB indisponível)."""
    from app.workers.async_utils import run_worker_coro

    async def _run():
        from app.db.base import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            return await executar_sync_stj(db)

    try:
        return run_worker_coro(_run())
    except Exception as exc:
        log.error("stj_sync_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=300)
