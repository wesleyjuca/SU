"""Task Celery: sincronização diária da pasta de doutrina do Google Drive,
por escritório (Fase 138.2).

Itera todos os tenants com a integração `google_drive_doutrina` CONECTADA e
uma pasta configurada (`extra_data.folder_id`) — um tenant sem token válido
(refresh falhou, acesso revogado) é pulado sem derrubar a sincronização dos
demais. Dentro de cada tenant, fail-soft por arquivo (1 arquivo malformado/
tipo não suportado não impede os demais)."""
from datetime import datetime, timezone
from sqlalchemy import select
import structlog

from app.workers.worker import celery_app

log = structlog.get_logger()


async def executar_sync_drive_doutrina(db) -> dict:
    from app.models.integrations import TenantIntegration
    from app.models.tenant import TenantConfig
    from app.models.jurisprudencia_ingerida import JurisprudenciaIngerida
    from app.services import integration_hub
    from app.integrations.google_drive.client import listar_arquivos, baixar_arquivo, extrair_texto
    from app.rag.ingestion import ingest_document
    from app.services.movements_import import iniciar_sync, finalizar_sync

    integracoes = (await db.execute(
        select(TenantIntegration).where(
            TenantIntegration.provider == "google_drive_doutrina",
            TenantIntegration.status == "CONECTADA",
        )
    )).scalars().all()

    tenants_sincronizados = 0
    tenants_pulados = 0
    total_processados = 0
    total_pulados = 0
    total_falhas = 0

    for integ in integracoes:
        folder_id = (integ.extra_data or {}).get("folder_id")
        if not folder_id:
            continue  # conectado mas ainda sem pasta configurada

        cfg = (await db.execute(
            select(TenantConfig).where(TenantConfig.tenant_id == integ.tenant_id)
        )).scalar_one_or_none()
        if not cfg or not (cfg.modules_enabled or {}).get("google_drive_doutrina", False):
            continue  # módulo desabilitado depois de conectar — não sincroniza mais

        creds = await integration_hub.get_credentials(db, integ.tenant_id, "google_drive_doutrina")
        if not creds or not creds.get("access_token"):
            tenants_pulados += 1
            log.warning("drive_sync_sem_token", tenant_id=str(integ.tenant_id))
            continue

        fonte = f"google_drive:{integ.tenant_id}"
        run = await iniciar_sync(db, integ.tenant_id, fonte=fonte, tipo="INGESTAO")

        arquivos = await listar_arquivos(creds["access_token"], folder_id)
        if arquivos is None:
            log.warning("drive_sync_listagem_falhou", tenant_id=str(integ.tenant_id))
            await finalizar_sync(db, run, "ERRO", {"processados": 0, "pulados": 0, "falhas": 0, "erro": "falha ao listar a pasta"})
            await db.commit()
            continue

        tenants_sincronizados += 1
        processados = pulados = falhas = 0
        # Fase 167 — uma exceção não tratada no meio da lista de arquivos de
        # UM tenant (DB caiu, SoftTimeLimitExceeded) propagava pra fora do
        # loop externo inteiro, abortando a sincronização dos DEMAIS
        # tenants e deixando o SyncRun deste tenant preso em RUNNING —
        # contrariava o próprio design fail-soft-por-tenant do arquivo
        # (ver docstring do módulo). Finaliza ERRO só pra este tenant e
        # segue pro próximo, em vez de re-lançar.
        try:
            for arq in arquivos:
                file_id = arq.get("id")
                if not file_id:
                    continue
                existe = (await db.execute(
                    select(JurisprudenciaIngerida).where(
                        JurisprudenciaIngerida.fonte == fonte,
                        JurisprudenciaIngerida.fonte_documento_id == file_id,
                    )
                )).scalar_one_or_none()
                if existe:
                    pulados += 1
                    continue

                metadata = {"nome_arquivo": arq.get("name"), "google_file_id": file_id}
                entrada = JurisprudenciaIngerida(
                    tenant_id=integ.tenant_id, fonte=fonte, fonte_documento_id=file_id,
                    collection_alvo="doutrina_privada", metadata_extraida=metadata, status="PENDENTE",
                )
                db.add(entrada)
                await db.flush()

                try:
                    conteudo = await baixar_arquivo(creds["access_token"], file_id)
                    if conteudo is None:
                        raise RuntimeError("download do arquivo falhou")
                    texto = await extrair_texto(arq.get("mimeType"), conteudo)
                    if not texto:
                        entrada.status = "FALHOU"
                        entrada.erro = "tipo de arquivo não suportado ou sem texto extraível"
                        falhas += 1
                    else:
                        await ingest_document(
                            content=texto, collection="doutrina_privada",
                            metadata={"tenant_id": str(integ.tenant_id), **metadata}, document_id=file_id,
                        )
                        entrada.status = "EMBEDDED"
                        processados += 1
                except Exception as exc:
                    entrada.status = "FALHOU"
                    entrada.erro = str(exc)[:500]
                    falhas += 1
                    log.warning("drive_ingest_falhou", tenant_id=str(integ.tenant_id), file_id=file_id, error=str(exc))
                entrada.processed_at = datetime.now(timezone.utc)
                await db.commit()
        except Exception as exc:
            log.error("drive_sync_loop_falhou", tenant_id=str(integ.tenant_id), error=str(exc))
            stats = {"processados": processados, "pulados": pulados, "falhas": falhas, "erro": str(exc)[:300]}
            await finalizar_sync(db, run, "ERRO", stats)
            await db.commit()
            continue

        stats = {"processados": processados, "pulados": pulados, "falhas": falhas}
        await finalizar_sync(db, run, "OK", stats)
        await db.commit()
        total_processados += processados
        total_pulados += pulados
        total_falhas += falhas

    resultado = {
        "tenants_sincronizados": tenants_sincronizados,
        "tenants_sem_token": tenants_pulados,
        "processados": total_processados,
        "pulados": total_pulados,
        "falhas": total_falhas,
    }
    log.info("drive_sync_complete", **resultado)
    return resultado


@celery_app.task(
    name="app.workers.tasks.google_drive_sync.sync_google_drive_doutrina", bind=True, max_retries=3,
    time_limit=7200, soft_time_limit=6900,
)
def sync_google_drive_doutrina(self):
    """Executa `executar_sync_drive_doutrina()` — roda via Beat."""
    from app.workers.async_utils import run_worker_coro

    async def _run():
        from app.db.base import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            return await executar_sync_drive_doutrina(db)

    async def _run_with_lock():
        from app.workers.task_lock import TaskLock

        lock = TaskLock("sync_google_drive_doutrina", ttl_seconds=7500)
        if not await lock.acquire():
            log.info("task_skipped_lock_held", task="sync_google_drive_doutrina")
            return {"skipped": True, "reason": "lock_held"}
        try:
            return await _run()
        finally:
            await lock.release()

    try:
        return run_worker_coro(_run_with_lock())
    except Exception as exc:
        log.error("drive_sync_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=300)
