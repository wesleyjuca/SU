"""Achado real (validação da pasta Doutrina): `auto_ingest.py::
auto_ingest_document()` engolia 100% silenciosamente qualquer falha de
`delete_document_chunks()` (ex.: índice de payload ausente na coleção,
exatamente a causa raiz do erro 400 "Index required but not found for
document_id" achado na Doutrina) — chunks antigos nunca eram limpos antes
do reingest, e ninguém via nenhum rastro disso. Continua non-blocking
(nunca impede a aprovação do documento), só passa a logar."""
import pytest
import structlog

from app.rag.auto_ingest import auto_ingest_document


@pytest.mark.asyncio
async def test_falha_ao_apagar_chunks_antigos_e_logada_mas_nao_bloqueia(monkeypatch):
    async def _fake_delete_falha(collection, document_id):
        raise RuntimeError(
            'Bad Request: Index required but not found for "document_id" of one of the following types: [keyword]'
        )

    chamou_ingest = {}

    async def _fake_ingest(**kwargs):
        chamou_ingest.update(kwargs)
        return ["ponto-1"]

    monkeypatch.setattr("app.rag.ingestion.delete_document_chunks", _fake_delete_falha)
    monkeypatch.setattr("app.rag.ingestion.ingest_document", _fake_ingest)

    eventos = []
    with structlog.testing.capture_logs() as cap:
        await auto_ingest_document(
            doc_id="doc-1", tenant_id="tenant-1", titulo="Petição Teste",
            tipo="PETICAO", texto="Conteúdo real da petição pra indexar.",
        )
        eventos = cap

    avisos = [e for e in eventos if e.get("event") == "auto_ingest_delete_chunks_falhou"]
    assert len(avisos) == 1, f"esperava exatamente 1 warning logado, achou: {eventos}"
    assert avisos[0]["document_id"] == "doc-1"
    assert avisos[0]["collection"] == "peticoes_afj"
    assert "document_id" in avisos[0]["error"]

    # Non-blocking: mesmo com delete_document_chunks falhando, o ingest
    # segue normalmente (a aprovação do documento nunca é impedida).
    assert chamou_ingest.get("content") == "Conteúdo real da petição pra indexar."
    assert chamou_ingest.get("collection") == "peticoes_afj"


@pytest.mark.asyncio
async def test_documento_generico_usa_collection_documentos_clientes(monkeypatch):
    async def _fake_delete_ok(collection, document_id):
        return None

    chamou_ingest = {}

    async def _fake_ingest(**kwargs):
        chamou_ingest.update(kwargs)
        return []

    monkeypatch.setattr("app.rag.ingestion.delete_document_chunks", _fake_delete_ok)
    monkeypatch.setattr("app.rag.ingestion.ingest_document", _fake_ingest)

    await auto_ingest_document(
        doc_id="doc-2", tenant_id="tenant-1", titulo="Contrato Teste",
        tipo="CONTRATO", texto="Conteúdo do contrato.", client_id="cliente-1",
    )

    assert chamou_ingest.get("collection") == "documentos_clientes"
    assert chamou_ingest.get("metadata", {}).get("client_id") == "cliente-1"
