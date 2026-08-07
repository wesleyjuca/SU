"""Fase 141 — app/workers/tasks/ocr_tasks.py (zero cobertura antes desta
fase). Cobre o branch novo (bytes vindos do object storage quando
arquivo_storage_key está setado) e o branch legado (data URL base64 em
arquivo_url), mesmo padrão de monkeypatch de AsyncSessionLocal já usado em
test_audit_attribution.py."""
import base64
import uuid
from types import SimpleNamespace

import pytest

import app.db.base as dbbase
from app.agents.base.result import AgentStatus
from app.models.document import Document
from app.workers.tasks import ocr_tasks


class _FakeSession:
    def __init__(self, doc):
        self.doc = doc
        self.committed = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, query):
        return SimpleNamespace(scalar_one_or_none=lambda: self.doc)

    async def commit(self):
        self.committed += 1


def _fake_ocr_agent_success(captured, texto="texto extraído via OCR"):
    class _FakeOCRAgent:
        UNAVAILABLE = "[OCR não disponível — instale pdfplumber e pytesseract]"

        def __init__(self, db=None):
            self.db = db

        async def execute(self, ctx):
            captured["ctx"] = ctx
            return SimpleNamespace(
                status=AgentStatus.SUCCESS,
                output={"texto_extraido": texto, "caracteres": len(texto), "palavras": len(texto.split())},
                error=None,
            )
    return _FakeOCRAgent


def _doc_s3(storage_key="documents/t1/d1/scan.pdf", mimetype="application/pdf"):
    return Document(
        id=uuid.uuid4(), titulo="Escaneado", tipo="OUTROS", tenant_id="11111111-1111-1111-1111-111111111111",
        arquivo_storage_key=storage_key, arquivo_mimetype=mimetype,
        metadata_json={"filename": "scan.pdf", "content_type": mimetype},
        conteudo_texto=None, client_id=None, created_by=None,
    )


def _doc_legado(conteudo=b"%PDF fake", content_type="application/pdf"):
    data_url = f"data:{content_type};base64," + base64.b64encode(conteudo).decode()
    return Document(
        id=uuid.uuid4(), titulo="Escaneado Legado", tipo="OUTROS", tenant_id="11111111-1111-1111-1111-111111111111",
        arquivo_url=data_url, metadata_json={"filename": "scan.pdf", "content_type": content_type},
        conteudo_texto=None, client_id=None, created_by=None,
    )


@pytest.mark.asyncio
async def test_ocr_busca_bytes_do_object_storage_quando_storage_key_setado(monkeypatch):
    doc = _doc_s3()
    session = _FakeSession(doc)
    monkeypatch.setattr(dbbase, "AsyncSessionLocal", lambda: session)

    called = {}

    async def _fake_get_bytes(key):
        called["key"] = key
        return b"bytes crus do s3"

    monkeypatch.setattr("app.integrations.object_storage.get_bytes", _fake_get_bytes)

    captured = {}
    monkeypatch.setattr(
        "app.agents.ocr.ocr_agent.OCRAgent", _fake_ocr_agent_success(captured, texto="conteudo reconhecido")
    )
    monkeypatch.setattr("app.rag.auto_ingest.auto_ingest_document", lambda *a, **k: None)

    await ocr_tasks._process_ocr(str(doc.id), "11111111-1111-1111-1111-111111111111")

    assert called["key"] == doc.arquivo_storage_key
    expected_b64 = base64.b64encode(b"bytes crus do s3").decode()
    assert captured["ctx"].task_input["file_bytes_b64"] == expected_b64
    assert captured["ctx"].task_input["content_type"] == "application/pdf"
    assert doc.conteudo_texto == "conteudo reconhecido"
    assert doc.metadata_json["ocr"]["status"] == "CONCLUIDO"
    assert session.committed >= 1


@pytest.mark.asyncio
async def test_ocr_object_storage_falha_marca_arquivo_indisponivel(monkeypatch):
    doc = _doc_s3()
    session = _FakeSession(doc)
    monkeypatch.setattr(dbbase, "AsyncSessionLocal", lambda: session)

    from app.integrations.object_storage import ObjectStorageError

    async def _fake_get_bytes_falha(key):
        raise ObjectStorageError("s3 indisponível")

    monkeypatch.setattr("app.integrations.object_storage.get_bytes", _fake_get_bytes_falha)

    await ocr_tasks._process_ocr(str(doc.id), "11111111-1111-1111-1111-111111111111")

    assert doc.metadata_json["ocr"]["status"] == "FALHOU"
    assert doc.metadata_json["ocr"]["erro"] == "arquivo indisponível"


@pytest.mark.asyncio
async def test_ocr_caminho_legado_continua_usando_parse_data_url(monkeypatch):
    """Regressão: documento pré-Fase 141 (sem arquivo_storage_key) precisa
    continuar funcionando exatamente como antes — via o data URL inline."""
    doc = _doc_legado(conteudo=b"conteudo binario legado")
    session = _FakeSession(doc)
    monkeypatch.setattr(dbbase, "AsyncSessionLocal", lambda: session)

    called_object_storage = {"sim": False}

    async def _fake_get_bytes(key):
        called_object_storage["sim"] = True
        return b""

    monkeypatch.setattr("app.integrations.object_storage.get_bytes", _fake_get_bytes)

    captured = {}
    monkeypatch.setattr(
        "app.agents.ocr.ocr_agent.OCRAgent", _fake_ocr_agent_success(captured, texto="texto do legado")
    )
    monkeypatch.setattr("app.rag.auto_ingest.auto_ingest_document", lambda *a, **k: None)

    await ocr_tasks._process_ocr(str(doc.id), "11111111-1111-1111-1111-111111111111")

    assert called_object_storage["sim"] is False  # nunca toca object_storage pra doc legado
    expected_b64 = base64.b64encode(b"conteudo binario legado").decode()
    assert captured["ctx"].task_input["file_bytes_b64"] == expected_b64
    assert doc.metadata_json["ocr"]["status"] == "CONCLUIDO"


@pytest.mark.asyncio
async def test_ocr_documento_nao_encontrado_nao_lanca(monkeypatch):
    session = _FakeSession(doc=None)
    monkeypatch.setattr(dbbase, "AsyncSessionLocal", lambda: session)
    await ocr_tasks._process_ocr(str(uuid.uuid4()), "11111111-1111-1111-1111-111111111111")  # não deve lançar
    assert session.committed == 0
