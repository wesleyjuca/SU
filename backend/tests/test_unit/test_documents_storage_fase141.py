"""Fase 141 — storage de documentos migrando de base64-no-Postgres pra
object storage S3-compatível. Caracterização dos 2 caminhos de
`POST /documents/upload` (sem S3 configurado = comportamento legado
inalterado; com S3 configurado = key salva, arquivo_url nulo; falha do S3
= 502 sem gravar linha), e do novo `GET /documents/{id}/original` (linha
legada, linha S3, documento só-texto, isolamento por tenant)."""
import base64
import io
import uuid

import pytest
from fastapi import BackgroundTasks, HTTPException, UploadFile
from starlette.datastructures import Headers

from app.api.v1.documents import upload_document, download_document_original
from app.models.document import Document


class _FakeUser:
    def __init__(self, id="u1", tenant_id="t1"):
        self.id = id
        self.tenant_id = tenant_id


class _FakeResult:
    def __init__(self, scalar=None):
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar


class _FakeDB:
    def __init__(self, execute_result=None):
        self._execute_result = execute_result
        self.added = []
        self.flushed = False

    async def execute(self, query):
        return self._execute_result if self._execute_result is not None else _FakeResult()

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        import datetime
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()
            if getattr(obj, "created_at", None) is None:
                obj.created_at = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
            if getattr(obj, "status", None) is None:
                obj.status = "RASCUNHO"
            if getattr(obj, "versao", None) is None:
                obj.versao = 1
            if getattr(obj, "gerado_por_ia", None) is None:
                obj.gerado_por_ia = False
        self.flushed = True


def _upload_file(content: bytes, filename="arquivo.txt", content_type="text/plain") -> UploadFile:
    return UploadFile(io.BytesIO(content), filename=filename, headers=Headers({"content-type": content_type}))


# ─── upload_document — sem S3 configurado (caminho legado inalterado) ──────

@pytest.mark.asyncio
async def test_upload_sem_s3_grava_base64_inline(monkeypatch):
    monkeypatch.setattr("app.integrations.object_storage.is_configured", lambda: False)
    db = _FakeDB()
    resp = await upload_document(
        BackgroundTasks(), file=_upload_file(b"conteudo de teste"),
        titulo="Doc Legado", tipo="OUTROS", current_user=_FakeUser(), db=db,
    )
    assert resp.status == "RASCUNHO"
    assert len(db.added) == 1
    doc = db.added[0]
    assert doc.arquivo_url is not None and doc.arquivo_url.startswith("data:text/plain;base64,")
    assert doc.arquivo_storage_key is None
    assert doc.arquivo_mimetype == "text/plain"
    assert doc.arquivo_size_bytes == len(b"conteudo de teste")
    assert base64.b64decode(doc.arquivo_url.split(",", 1)[1]) == b"conteudo de teste"


# ─── upload_document — com S3 configurado (mock de object_storage) ─────────

@pytest.mark.asyncio
async def test_upload_com_s3_configurado_grava_storage_key(monkeypatch):
    monkeypatch.setattr("app.integrations.object_storage.is_configured", lambda: True)

    async def _fake_upload_bytes(**kwargs):
        return f"documents/{kwargs['tenant_id']}/{kwargs['document_id']}/{kwargs['filename']}"

    monkeypatch.setattr("app.integrations.object_storage.upload_bytes", _fake_upload_bytes)

    db = _FakeDB()
    resp = await upload_document(
        BackgroundTasks(), file=_upload_file(b"pdf fake", filename="contrato.pdf", content_type="application/pdf"),
        titulo="Doc S3", tipo="CONTRATO", current_user=_FakeUser(tenant_id="t1"), db=db,
    )
    assert resp.status == "RASCUNHO"
    doc = db.added[0]
    assert doc.arquivo_url is None
    assert doc.arquivo_storage_key == f"documents/t1/{doc.id}/contrato.pdf"
    assert doc.arquivo_mimetype == "application/pdf"
    assert doc.arquivo_size_bytes == len(b"pdf fake")


@pytest.mark.asyncio
async def test_upload_com_s3_falha_retorna_502_sem_gravar_linha(monkeypatch):
    from app.integrations.object_storage import ObjectStorageError

    monkeypatch.setattr("app.integrations.object_storage.is_configured", lambda: True)

    async def _fake_upload_bytes_falha(**kwargs):
        raise ObjectStorageError("bucket indisponível")

    monkeypatch.setattr("app.integrations.object_storage.upload_bytes", _fake_upload_bytes_falha)

    db = _FakeDB()
    with pytest.raises(HTTPException) as exc_info:
        await upload_document(
            BackgroundTasks(), file=_upload_file(b"conteudo"), titulo="Doc Falho", tipo="OUTROS",
            current_user=_FakeUser(), db=db,
        )
    assert exc_info.value.status_code == 502
    assert db.added == []  # nenhuma linha Document gravada — sem fallback silencioso


# ─── GET /{doc_id}/original ─────────────────────────────────────────────────

def _doc_legado(conteudo=b"texto original", content_type="text/plain", tenant_id="t1"):
    data_url = f"data:{content_type};base64," + base64.b64encode(conteudo).decode()
    return Document(
        id=uuid.uuid4(), titulo="Doc", tenant_id=tenant_id, arquivo_url=data_url,
        arquivo_mimetype=content_type, metadata_json={"filename": "original.txt"},
    )


def _doc_s3(storage_key="documents/t1/d1/a.pdf", tenant_id="t1"):
    return Document(
        id=uuid.uuid4(), titulo="Doc", tenant_id=tenant_id, arquivo_storage_key=storage_key,
        arquivo_mimetype="application/pdf", metadata_json={"filename": "original.pdf"},
    )


@pytest.mark.asyncio
async def test_original_linha_legada_decodifica_base64():
    doc = _doc_legado(conteudo=b"conteudo legado")
    db = _FakeDB(execute_result=_FakeResult(scalar=doc))
    resp = await download_document_original(str(doc.id), current_user=_FakeUser(), db=db)
    assert resp.body == b"conteudo legado"
    assert resp.media_type == "text/plain"


@pytest.mark.asyncio
async def test_original_linha_s3_busca_via_object_storage(monkeypatch):
    doc = _doc_s3()

    async def _fake_get_bytes(key):
        assert key == doc.arquivo_storage_key
        return b"bytes do s3"

    monkeypatch.setattr("app.integrations.object_storage.get_bytes", _fake_get_bytes)
    db = _FakeDB(execute_result=_FakeResult(scalar=doc))
    resp = await download_document_original(str(doc.id), current_user=_FakeUser(), db=db)
    assert resp.body == b"bytes do s3"
    assert resp.media_type == "application/pdf"


@pytest.mark.asyncio
async def test_original_s3_falha_retorna_502(monkeypatch):
    from app.integrations.object_storage import ObjectStorageError

    doc = _doc_s3()

    async def _fake_get_bytes_falha(key):
        raise ObjectStorageError("s3 fora do ar")

    monkeypatch.setattr("app.integrations.object_storage.get_bytes", _fake_get_bytes_falha)
    db = _FakeDB(execute_result=_FakeResult(scalar=doc))
    with pytest.raises(HTTPException) as exc_info:
        await download_document_original(str(doc.id), current_user=_FakeUser(), db=db)
    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_original_documento_so_texto_404():
    doc = Document(id=uuid.uuid4(), titulo="Só texto", tenant_id="t1", conteudo_texto="oi", metadata_json={})
    db = _FakeDB(execute_result=_FakeResult(scalar=doc))
    with pytest.raises(HTTPException) as exc_info:
        await download_document_original(str(doc.id), current_user=_FakeUser(), db=db)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_original_nao_encontrado_404():
    db = _FakeDB(execute_result=_FakeResult(scalar=None))
    with pytest.raises(Exception):
        await download_document_original(str(uuid.uuid4()), current_user=_FakeUser(), db=db)
