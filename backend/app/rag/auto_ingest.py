"""Ingestão automática de documentos aprovados nas coleções privadas do RAG.

Ao aprovar/protocolar um documento, seu texto é indexado no Qdrant (coleção do
escritório) com `tenant_id` no payload — o que torna a Pesquisa Jurídica útil e,
combinado ao filtro por tenant na busca, mantém o isolamento entre escritórios.

Roda em background: falhas (ex.: OPENAI_API_KEY ausente) apenas logam, sem
afetar a requisição do usuário.
"""
import structlog

log = structlog.get_logger()

_PETICAO_TIPOS = {
    "PETICAO", "PETICAO_INICIAL", "CONTESTACAO", "RECURSO", "RECURSO_APELACAO",
    "AGRAVO", "MANDADO_SEGURANCA", "HABEAS_CORPUS", "IMPUGNACAO",
}


def _collection_for(tipo: str | None) -> str:
    return "peticoes_afj" if (tipo or "").upper() in _PETICAO_TIPOS else "documentos_clientes"


async def auto_ingest_document(doc_id, tenant_id, titulo, tipo, texto, client_id=None) -> None:
    """Indexa (ou reindexa) o texto de um documento aprovado. Idempotente."""
    if not tenant_id or not (texto and texto.strip()):
        return
    collection = _collection_for(tipo)
    try:
        from app.rag.ingestion import ingest_document, delete_document_chunks
        # Idempotência: remove chunks antigos deste documento antes de reindexar.
        try:
            await delete_document_chunks(collection, str(doc_id))
        except Exception:
            pass
        metadata = {
            "tenant_id": str(tenant_id),
            "document_id": str(doc_id),
            "titulo": titulo,
            "tipo": tipo,
        }
        if client_id:
            metadata["client_id"] = str(client_id)
        ids = await ingest_document(
            content=texto, collection=collection, metadata=metadata, document_id=str(doc_id)
        )
        log.info("auto_ingest_ok", document_id=str(doc_id), collection=collection, chunks=len(ids))
    except Exception as exc:
        log.warning("auto_ingest_failed", document_id=str(doc_id), error=str(exc))
