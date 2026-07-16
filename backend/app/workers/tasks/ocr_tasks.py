"""Task de OCR de documentos — extrai texto de PDFs/imagens enviados e grava
em `Document.conteudo_texto`, tornando-os pesquisáveis.

Dois pontos de entrada compartilham o mesmo núcleo (`_process_ocr`):
- `ocr_document_task` — task Celery (broker/worker disponíveis).
- `run_ocr_inproc`   — coroutine para o fallback via FastAPI BackgroundTasks
  quando o broker está fora do ar (o upload nunca falha por causa do OCR).
"""
import uuid
from datetime import datetime

import structlog

from app.workers.worker import celery_app

log = structlog.get_logger()


def _parse_data_url(arquivo_url: str) -> tuple[str | None, str | None]:
    """Devolve (base64_puro, content_type) a partir de um data URL
    `data:<ct>;base64,<dados>`. Retorna (None, None) se não reconhecer."""
    if not arquivo_url or not arquivo_url.startswith("data:"):
        return None, None
    try:
        header, b64 = arquivo_url.split(",", 1)
    except ValueError:
        return None, None
    # header = "data:application/pdf;base64"
    ct = header[len("data:"):].split(";", 1)[0] or None
    return b64, ct


async def _process_ocr(doc_id: str, tenant_id: str | None) -> None:
    """Carrega o documento (isolado por tenant), roda o OCRAgent sobre os bytes
    guardados em `arquivo_url` e persiste o texto extraído + status em
    `metadata_json['ocr']`. Nunca grava o placeholder de indisponibilidade."""
    from sqlalchemy import select

    from app.db.base import AsyncSessionLocal
    from app.models.document import Document
    from app.agents.ocr.ocr_agent import OCRAgent
    from app.agents.brain.context import AgentContext
    from app.agents.base.result import AgentStatus

    async with AsyncSessionLocal() as db:
        query = select(Document).where(Document.id == uuid.UUID(doc_id))
        if tenant_id:
            query = query.where(Document.tenant_id == uuid.UUID(tenant_id))
        doc = (await db.execute(query)).scalar_one_or_none()
        if not doc:
            log.warning("ocr_document_not_found", doc_id=doc_id, tenant_id=tenant_id)
            return

        b64, ct_from_url = _parse_data_url(doc.arquivo_url or "")
        meta = dict(doc.metadata_json or {})
        content_type = meta.get("content_type") or ct_from_url

        if not b64:
            meta["ocr"] = {"status": "FALHOU", "erro": "arquivo indisponível", "at": datetime.utcnow().isoformat()}
            doc.metadata_json = meta
            await db.commit()
            return

        ctx = AgentContext(
            task_type="ocr_document",
            task_input={"file_bytes_b64": b64, "content_type": content_type},
            document_id=doc.id,
            tenant_id=doc.tenant_id,
        )
        result = await OCRAgent(db=db).execute(ctx)

        now = datetime.utcnow().isoformat()
        if result.status == AgentStatus.SUCCESS:
            texto = (result.output or {}).get("texto_extraido") or ""
            if texto == OCRAgent.UNAVAILABLE:
                meta["ocr"] = {"status": "INDISPONIVEL", "at": now,
                               "detalhe": "motor de OCR não instalado no servidor"}
            elif texto.strip():
                # Não sobrescreve texto humano/estruturado já existente.
                atual = (doc.conteudo_texto or "").strip()
                if len(atual) < 50:
                    doc.conteudo_texto = texto
                meta["ocr"] = {
                    "status": "CONCLUIDO",
                    "caracteres": (result.output or {}).get("caracteres", len(texto)),
                    "palavras": (result.output or {}).get("palavras", len(texto.split())),
                    "at": now,
                }
            else:
                meta["ocr"] = {"status": "VAZIO", "at": now,
                               "detalhe": "nenhum texto reconhecido no arquivo"}
        else:
            meta["ocr"] = {"status": "FALHOU", "erro": result.error or "erro desconhecido", "at": now}

        doc.metadata_json = meta
        await db.commit()
        log.info("ocr_document_done", doc_id=doc_id, status=meta["ocr"]["status"])

        # Encadeia a indexação no RAG: o documento digitalizado vira pesquisável
        # na Pesquisa Jurídica (coleção privada do escritório, isolada por tenant).
        # Idempotente e à prova de falha — não afeta o OCR já persistido.
        if meta.get("ocr", {}).get("status") == "CONCLUIDO":
            try:
                from app.rag.auto_ingest import auto_ingest_document
                await auto_ingest_document(
                    doc.id, doc.tenant_id, doc.titulo, doc.tipo, doc.conteudo_texto, doc.client_id
                )
                meta["ocr"]["rag"] = "indexado"
                doc.metadata_json = {**meta}
                await db.commit()
            except Exception as exc:
                log.warning("ocr_rag_index_failed", doc_id=doc_id, error=str(exc))

        # Notifica o dono do documento (best-effort) para a UI atualizar.
        try:
            from app.api.v1.ws import publish_event
            if doc.created_by:
                await publish_event(str(doc.created_by), "OCR_DONE", {
                    "document_id": doc_id,
                    "status": meta["ocr"]["status"],
                })
        except Exception:
            pass


async def run_ocr_inproc(doc_id: str, tenant_id: str | None) -> None:
    """Fallback in-process (FastAPI BackgroundTasks) quando o broker está fora."""
    try:
        await _process_ocr(doc_id, tenant_id)
    except Exception as exc:  # nunca propaga — é background do request
        log.error("ocr_inproc_failed", doc_id=doc_id, error=str(exc))


@celery_app.task(
    name="ocr_tasks.ocr_document",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def ocr_document_task(self, doc_id: str, tenant_id: str | None = None):
    """Executa o OCR de um documento em background via Celery worker."""
    from app.workers.async_utils import run_worker_coro
    try:
        run_worker_coro(_process_ocr(doc_id, tenant_id))
    except Exception as exc:
        log.error("celery_ocr_task_failed", doc_id=doc_id, error=str(exc))
        raise self.retry(exc=exc)
