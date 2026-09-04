"""Task Celery: sincronização diária da pasta de doutrina do Google Drive,
por escritório (Fase 138.2).

Itera todos os tenants com a integração `google_drive_doutrina` CONECTADA e
uma pasta configurada (`extra_data.folder_id`) — um tenant sem token válido
(refresh falhou, acesso revogado) é pulado sem derrubar a sincronização dos
demais. Dentro de cada tenant, fail-soft por arquivo (1 arquivo malformado/
tipo não suportado não impede os demais).

Fase 185 — 2 correções: (a) Google Docs nativos (criados direto no Drive,
não upload de arquivo) agora são baixados via `/export` em vez de
`alt=media` (ver `client.py::baixar_conteudo`); (b) um arquivo que falhou
uma vez não fica marcado `FALHOU` pra sempre — só arquivos já `EMBEDDED`
são pulados, os demais são reprocessados na próxima sincronização."""
from datetime import datetime, timezone
from sqlalchemy import select
import structlog

from app.workers.worker import celery_app

log = structlog.get_logger()


async def executar_sync_drive_doutrina(db, tenant_id=None) -> dict:
    """`tenant_id` — Fase 258, opcional: quando informado, sincroniza só esse
    tenant (usado por `POST /integrations/hub/google_drive_doutrina/
    sync-now`, ação manual do ADMIN). Omitido (chamada do Celery Beat via
    `sync_google_drive_doutrina` abaixo, sem mudança) continua iterando
    todos os tenants conectados — comportamento idêntico ao de antes desta
    fase."""
    from app.models.integrations import TenantIntegration
    from app.models.tenant import TenantConfig
    from app.models.jurisprudencia_ingerida import JurisprudenciaIngerida
    from app.services import integration_hub
    from app.integrations.google_drive.client import (
        listar_arquivos, baixar_conteudo, extrair_texto, tipo_suportado,
    )
    from app.rag.ingestion import ingest_document, delete_document_chunks
    from app.services.movements_import import iniciar_sync, finalizar_sync

    where_clause = [
        TenantIntegration.provider == "google_drive_doutrina",
        TenantIntegration.status == "CONECTADA",
    ]
    if tenant_id is not None:
        where_clause.append(TenantIntegration.tenant_id == tenant_id)

    integracoes = (await db.execute(
        select(TenantIntegration).where(*where_clause)
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
                # Só pula quem já terminou EMBEDDED — um FALHOU (tipo antes
                # não suportado, download que deu erro transiente, etc.)
                # ficava marcado assim pra sempre, porque esta checagem não
                # olhava o `status`: nenhuma sincronização seguinte tentava
                # de novo, mesmo depois da causa da falha ser corrigida.
                # Reaproveita a linha existente em vez de inserir outra —
                # `(fonte, fonte_documento_id)` é UNIQUE.
                metadata = {
                    "nome_arquivo": arq.get("name"),
                    "google_file_id": file_id,
                    "caminho_pasta": arq.get("caminho_pasta") or "",
                }
                if existe:
                    if existe.status == "EMBEDDED":
                        pulados += 1
                        continue
                    entrada = existe
                    entrada.metadata_extraida = metadata
                    entrada.erro = None
                else:
                    entrada = JurisprudenciaIngerida(
                        tenant_id=integ.tenant_id, fonte=fonte, fonte_documento_id=file_id,
                        collection_alvo="doutrina_privada", metadata_extraida=metadata, status="PENDENTE",
                    )
                    db.add(entrada)
                await db.flush()

                try:
                    mime_type = arq.get("mimeType")
                    # Achado real (validação da pasta Doutrina): tipos
                    # nativos do Google Workspace fora de Docs (Sheets/
                    # Slides/Forms/Desenhos) caíam em `alt=media`, que a
                    # Drive API rejeita pra esses tipos — o download falhava
                    # com um erro HTTP genérico, virando uma mensagem que
                    # não deixava claro que o FORMATO em si não é suportado.
                    # Checar antes evita a chamada HTTP fadada a falhar e dá
                    # uma mensagem precisa — não adiciona suporte a nenhum
                    # formato novo, só move o ponto de checagem pra antes do
                    # download.
                    if not tipo_suportado(mime_type):
                        entrada.status = "FALHOU"
                        entrada.erro = f"Formato não suportado ({mime_type}) — suportados: PDF, DOCX, Google Docs."
                        falhas += 1
                        entrada.processed_at = datetime.now(timezone.utc)
                        await db.commit()
                        continue
                    conteudo = await baixar_conteudo(creds["access_token"], file_id, mime_type)
                    if conteudo is None:
                        raise RuntimeError("download do arquivo falhou")
                    texto = await extrair_texto(mime_type, conteudo)
                    if not texto:
                        entrada.status = "FALHOU"
                        entrada.erro = "tipo de arquivo não suportado ou sem texto extraível"
                        falhas += 1
                    else:
                        # Fase 188.1 — achado da Fase 186: reprocessar um
                        # arquivo que já tinha `document_id` ingerido antes
                        # (ex.: FALHOU depois do upsert ter subido, ou um
                        # reprocessamento normal) duplicava chunks órfãos no
                        # Qdrant — `point_id` é `uuid4()` não-determinístico,
                        # então reingerir nunca sobrescreve o ponto antigo.
                        # Idempotente mesmo se não havia nada pra apagar.
                        await delete_document_chunks(collection="doutrina_privada", document_id=file_id)
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
            # Achado real (validação da pasta Doutrina): este commit final
            # estava desprotegido — se a sessão tivesse sido invalidada por
            # uma falha anterior no loop, ele lançava de novo, sem nada pra
            # capturar, escapando de `executar_sync_drive_doutrina()` inteira
            # (chamada sem try/except por `hub_drive_sync_now`). O `SyncRun`
            # ficava preso em RUNNING pra sempre — a tela mostrava "em
            # andamento"/"0 processados" mesmo com arquivos já processados e
            # commitados individualmente antes da falha. `rollback()` antes
            # de tentar limpa uma transação possivelmente abortada; se ainda
            # assim falhar, loga e segue pro próximo tenant com sessão limpa
            # — nunca deixa uma 2ª exceção escapar daqui.
            try:
                await db.rollback()
                await finalizar_sync(db, run, "ERRO", stats)
                await db.commit()
            except Exception as exc2:
                log.error("drive_sync_finalizar_erro_falhou", tenant_id=str(integ.tenant_id), error=str(exc2))
                try:
                    await db.rollback()
                except Exception:
                    pass
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
