"""Task Celery: sincronização diária da(s) pasta(s) de doutrina do Google
Drive, por escritório (Fase 138.2).

Itera todos os tenants com a integração `google_drive_doutrina` CONECTADA e
pelo menos uma pasta configurada (`integration_hub.pastas_drive_doutrina`,
Fase pós-262 — antes era 1 pasta só, `extra_data.folder_id`) — um tenant sem
token válido (refresh falhou, acesso revogado) é pulado sem derrubar a
sincronização dos demais. Dentro de cada tenant, fail-soft por arquivo (1
arquivo malformado/tipo não suportado não impede os demais) e por pasta (1
pasta removida/sem acesso não impede as demais pastas do mesmo tenant).

Fase 185 — 2 correções: (a) Google Docs nativos (criados direto no Drive,
não upload de arquivo) agora são baixados via `/export` em vez de
`alt=media` (ver `client.py::baixar_conteudo`); (b) um arquivo que falhou
uma vez não fica marcado `FALHOU` pra sempre — só arquivos já `EMBEDDED`
são pulados, os demais são reprocessados na próxima sincronização.

Fase pós-262 — achado real (usuário reportou "a pesquisa não lê os arquivos
da pasta compartilhada"): este worker nunca ativava a IA própria (BYOK) do
admin antes de ingerir, ao contrário de TODO outro fluxo RAG do sistema
(`rag.py`, `documents.py`, `brain_assistant.py`, `brain_insights.py`,
`orchestrator.py` — todos usam `user_ai_creds`). Sem isso, um tenant sem
`OPENAI_API_KEY` central e dependente só do BYOK cadastrado em "Minha IA"
tinha 100% dos arquivos falhando com `EmbeddingProviderUnavailable` — não
silencioso no banco (`JurisprudenciaIngerida.erro` grava a causa real), mas
opaco pro usuário, que só via "não funciona". Corrigido envolvendo a
sincronização de cada tenant em `user_ai_creds(db, integ.connected_by,
"rag_ingest")` — o admin que conectou a integração é quem "empresta" a
credencial BYOK pra ingestão em background, mesmo espírito de
`ingest_document(..., force_system_default=False)` já usado pelo resto do
RAG. `connected_by` ausente (linha legada) ou sem BYOK cadastrado cai no
comportamento de sempre (chave central) — sem regressão."""
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
    from app.integrations.byok import user_ai_creds
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
        pastas = integration_hub.pastas_drive_doutrina(integ.extra_data)
        if not pastas:
            continue  # conectado mas ainda sem nenhuma pasta configurada

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

        processados = pulados = falhas = 0
        pastas_com_erro = 0
        # `True` assim que a listagem de QUALQUER uma das pastas configuradas
        # tiver sucesso — mesmo timing do "arquivos is None" de antes desta
        # fase (1 pasta só): conta o tenant como sincronizado mesmo que uma
        # exceção catastrófica no processamento de arquivo derrube o resto
        # (branch ERRO abaixo), porque a listagem em si já funcionou.
        alguma_pasta_listada = False
        # Fase 167 — uma exceção não tratada no meio da lista de arquivos de
        # UM tenant (DB caiu, SoftTimeLimitExceeded) propagava pra fora do
        # loop externo inteiro, abortando a sincronização dos DEMAIS
        # tenants e deixando o SyncRun deste tenant preso em RUNNING —
        # contrariava o próprio design fail-soft-por-tenant do arquivo
        # (ver docstring do módulo). Finaliza ERRO só pra este tenant e
        # segue pro próximo, em vez de re-lançar.
        try:
            # Fase pós-262 — a credencial BYOK do admin que conectou a
            # integração fica ativa durante toda a ingestão deste tenant
            # (todas as pastas), pra `ingest_document`/`embed_batch_with_meta`
            # conseguirem resolvê-la sem depender da chave central (ver
            # docstring do módulo — achado real do sintoma "não lê os
            # arquivos da pasta compartilhada").
            async with user_ai_creds(db, integ.connected_by, "rag_ingest"):
                for pasta in pastas:
                    folder_id = pasta["folder_id"]
                    folder_nome = pasta.get("folder_name") or folder_id
                    arquivos = await listar_arquivos(creds["access_token"], folder_id)
                    if arquivos is None:
                        pastas_com_erro += 1
                        log.warning(
                            "drive_sync_listagem_falhou", tenant_id=str(integ.tenant_id),
                            folder_id=folder_id, folder_nome=folder_nome,
                        )
                        continue
                    if not alguma_pasta_listada:
                        alguma_pasta_listada = True
                        tenants_sincronizados += 1

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
                        caminho = arq.get("caminho_pasta") or ""
                        metadata = {
                            "nome_arquivo": arq.get("name"),
                            "google_file_id": file_id,
                            "pasta_raiz_nome": folder_nome,
                            # Com só 1 pasta configurada (caso mais comum),
                            # mantém o formato de antes — sem prefixo — pra
                            # não mudar o que já é exibido hoje. Com mais de
                            # 1, prefixa com o nome da pasta-raiz pra
                            # distinguir a origem no diagnóstico.
                            "caminho_pasta": f"{folder_nome}/{caminho}".rstrip("/") if len(pastas) > 1 else caminho,
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

        if not alguma_pasta_listada:
            # Nenhuma das pastas configuradas respondeu — mesma classe de
            # ERRO que valia quando só existia 1 pasta e a listagem falhava.
            stats = {
                "processados": 0, "pulados": 0, "falhas": 0,
                "erro": "falha ao listar todas as pastas configuradas",
            }
            await finalizar_sync(db, run, "ERRO", stats)
            await db.commit()
            continue

        stats = {"processados": processados, "pulados": pulados, "falhas": falhas}
        if pastas_com_erro:
            stats["pastas_com_erro"] = pastas_com_erro
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
