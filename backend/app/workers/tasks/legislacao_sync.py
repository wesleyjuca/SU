"""Task Celery: sincronização diária de legislação federal (LexML →
Planalto, Fase 138.3).

Processa só o lote mais recente por execução — sem paginação/cursor real por
data, a tabela `JurisprudenciaIngerida` funciona como "cursor implícito"
(normas já vistas são puladas), mesma filosofia do STJ (Fase 138.1). Fonte
pública, sem tenant, sem credencial."""
from datetime import datetime, timezone
from sqlalchemy import select
import structlog

from app.workers.worker import celery_app

log = structlog.get_logger()

FONTE = "lexml_legislacao"


async def executar_sync_legislacao(db) -> dict:
    """Lógica de sincronização, separada do wrapper Celery pra ser
    testável/chamável diretamente com uma sessão real. Fail-soft por norma
    (uma lei/decreto malformado não derruba as demais)."""
    from app.models.jurisprudencia_ingerida import JurisprudenciaIngerida
    from app.integrations.lexml.client import buscar_lote_legislacao_federal, buscar_norma_completa
    from app.rag.ingestion import ingest_document
    from app.services.movements_import import iniciar_sync, finalizar_sync

    run = await iniciar_sync(db, tenant_id=None, fonte=FONTE, tipo="INGESTAO")

    processados = 0
    pulados = 0
    falhas = 0
    try:
        registros = await buscar_lote_legislacao_federal()
    except Exception as exc:
        log.error("legislacao_sync_busca_falhou", error=str(exc))
        stats = {"processados": 0, "pulados": 0, "falhas": 0, "erro": str(exc)[:300]}
        await finalizar_sync(db, run, "ERRO", stats)
        await db.commit()
        raise

    for registro in registros:
        urn = registro.get("urn")
        if not urn:
            continue
        existe = (await db.execute(
            select(JurisprudenciaIngerida).where(
                JurisprudenciaIngerida.fonte == FONTE,
                JurisprudenciaIngerida.fonte_documento_id == urn,
            )
        )).scalar_one_or_none()
        if existe:
            pulados += 1
            continue

        metadata_extraida = {
            "titulo": registro.get("titulo"),
            "tipo_norma": registro.get("tipo_norma"),
            "url": registro.get("url"),
        }
        entrada = JurisprudenciaIngerida(
            fonte=FONTE,
            fonte_documento_id=urn,
            collection_alvo="legislacao",
            metadata_extraida=metadata_extraida,
            status="PENDENTE",
        )
        db.add(entrada)
        await db.flush()

        try:
            norma = await buscar_norma_completa(registro)
            if norma is None:
                raise RuntimeError("download/extração de texto falhou ou devolveu vazio")
            qdrant_metadata = {
                "diploma": norma.get("titulo") or urn,
                "tipo_norma": norma.get("tipo_norma"),
                "urn": urn,
            }
            await ingest_document(
                content=norma["texto"], collection="legislacao",
                metadata=qdrant_metadata, document_id=urn,
            )
            entrada.status = "EMBEDDED"
            processados += 1
        except Exception as exc:
            entrada.status = "FALHOU"
            entrada.erro = str(exc)[:500]
            falhas += 1
            log.warning("legislacao_ingest_falhou", urn=urn, error=str(exc))
        entrada.processed_at = datetime.now(timezone.utc)
        await db.commit()

    stats = {"processados": processados, "pulados": pulados, "falhas": falhas}
    await finalizar_sync(db, run, "OK", stats)
    await db.commit()
    log.info("legislacao_sync_complete", **stats)
    return stats


@celery_app.task(name="app.workers.tasks.legislacao_sync.sync_legislacao_diario", bind=True, max_retries=3)
def sync_legislacao_diario(self):
    """Executa `executar_sync_legislacao()` — roda via Beat, re-tenta se a
    task inteira falhar (ex.: DB indisponível)."""
    from app.workers.async_utils import run_worker_coro

    async def _run():
        from app.db.base import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            return await executar_sync_legislacao(db)

    try:
        return run_worker_coro(_run())
    except Exception as exc:
        log.error("legislacao_sync_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=300)
