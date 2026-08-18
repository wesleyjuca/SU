"""Fase 141 — cliente de object storage S3-compatível (app/integrations/
object_storage.py). Mock direto do cliente aioboto3 (sem `moto`, mesmo
padrão AsyncMock/monkeypatch já usado no resto da suíte)."""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.integrations import object_storage


def _patch_settings(monkeypatch, **kwargs):
    from app.config import settings
    for key, value in {
        "S3_BUCKET": "meu-bucket", "S3_ACCESS_KEY_ID": "AKIA...", "S3_SECRET_ACCESS_KEY": "segredo",
        "S3_ENDPOINT_URL": "", "S3_REGION": "auto", "S3_ADDRESSING_STYLE": "path",
        **kwargs,
    }.items():
        monkeypatch.setattr(settings, key, value)


# ─── is_configured() ────────────────────────────────────────────────────────

def test_is_configured_true_quando_credenciais_presentes(monkeypatch):
    _patch_settings(monkeypatch)
    assert object_storage.is_configured() is True


def test_is_configured_false_sem_bucket(monkeypatch):
    _patch_settings(monkeypatch, S3_BUCKET="")
    assert object_storage.is_configured() is False


def test_is_configured_false_sem_credenciais(monkeypatch):
    _patch_settings(monkeypatch, S3_ACCESS_KEY_ID="", S3_SECRET_ACCESS_KEY="")
    assert object_storage.is_configured() is False


# ─── build_key() ─────────────────────────────────────────────────────────────

def test_build_key_formato_esperado():
    tid = uuid.uuid4()
    did = uuid.uuid4()
    key = object_storage.build_key(tid, did, "contrato.pdf")
    assert key == f"documents/{tid}/{did}/contrato.pdf"


def test_build_key_sanitiza_path_traversal():
    key = object_storage.build_key("t1", "d1", "../../etc/passwd")
    assert "../" not in key
    assert key.startswith("documents/t1/d1/")


def test_build_key_sanitiza_caracteres_especiais():
    key = object_storage.build_key("t1", "d1", "relatório final (v2).docx")
    assert key == "documents/t1/d1/relat_rio_final__v2_.docx"


def test_build_key_filename_vazio_usa_fallback():
    key = object_storage.build_key("t1", "d1", "")
    assert key == "documents/t1/d1/arquivo"


# ─── upload_bytes() / get_bytes() — sucesso (mock do cliente S3) ──────────────

class _FakeAsyncCtxClient:
    def __init__(self, client):
        self._client = client

    async def __aenter__(self):
        return self._client

    async def __aexit__(self, *a):
        return False


class _FakeSession:
    def __init__(self, client):
        self._client = client

    def client(self, *a, **k):
        return _FakeAsyncCtxClient(self._client)


@pytest.mark.asyncio
async def test_upload_bytes_chama_put_object_com_bucket_key_content_type(monkeypatch):
    _patch_settings(monkeypatch)
    fake_client = MagicMock()
    fake_client.put_object = AsyncMock(return_value={})
    monkeypatch.setattr("aioboto3.Session", lambda: _FakeSession(fake_client))

    tid, did = uuid.uuid4(), uuid.uuid4()
    key = await object_storage.upload_bytes(tid, did, "peticao.pdf", "application/pdf", b"conteudo")

    assert key == f"documents/{tid}/{did}/peticao.pdf"
    fake_client.put_object.assert_awaited_once()
    _, kwargs = fake_client.put_object.call_args
    assert kwargs["Bucket"] == "meu-bucket"
    assert kwargs["Key"] == key
    assert kwargs["Body"] == b"conteudo"
    assert kwargs["ContentType"] == "application/pdf"


@pytest.mark.asyncio
async def test_upload_bytes_falha_vira_object_storage_error(monkeypatch):
    _patch_settings(monkeypatch)
    fake_client = MagicMock()
    fake_client.put_object = AsyncMock(side_effect=RuntimeError("conexão recusada"))
    monkeypatch.setattr("aioboto3.Session", lambda: _FakeSession(fake_client))

    with pytest.raises(object_storage.ObjectStorageError):
        await object_storage.upload_bytes(uuid.uuid4(), uuid.uuid4(), "a.pdf", "application/pdf", b"x")


@pytest.mark.asyncio
async def test_get_bytes_le_o_corpo_da_resposta(monkeypatch):
    _patch_settings(monkeypatch)

    class _FakeBody:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def read(self):
            return b"bytes originais"

    fake_client = MagicMock()
    fake_client.get_object = AsyncMock(return_value={"Body": _FakeBody()})
    monkeypatch.setattr("aioboto3.Session", lambda: _FakeSession(fake_client))

    raw = await object_storage.get_bytes("documents/t1/d1/a.pdf")
    assert raw == b"bytes originais"


@pytest.mark.asyncio
async def test_get_bytes_falha_vira_object_storage_error(monkeypatch):
    _patch_settings(monkeypatch)
    fake_client = MagicMock()
    fake_client.get_object = AsyncMock(side_effect=RuntimeError("404"))
    monkeypatch.setattr("aioboto3.Session", lambda: _FakeSession(fake_client))

    with pytest.raises(object_storage.ObjectStorageError):
        await object_storage.get_bytes("documents/t1/d1/a.pdf")


@pytest.mark.asyncio
async def test_delete_bytes_chama_delete_object_com_bucket_e_key(monkeypatch):
    _patch_settings(monkeypatch)
    fake_client = MagicMock()
    fake_client.delete_object = AsyncMock(return_value={})
    monkeypatch.setattr("aioboto3.Session", lambda: _FakeSession(fake_client))

    await object_storage.delete_bytes("documents/t1/d1/a.pdf")

    fake_client.delete_object.assert_awaited_once()
    _, kwargs = fake_client.delete_object.call_args
    assert kwargs["Bucket"] == "meu-bucket"
    assert kwargs["Key"] == "documents/t1/d1/a.pdf"


@pytest.mark.asyncio
async def test_delete_bytes_falha_vira_object_storage_error(monkeypatch):
    _patch_settings(monkeypatch)
    fake_client = MagicMock()
    fake_client.delete_object = AsyncMock(side_effect=RuntimeError("conexão recusada"))
    monkeypatch.setattr("aioboto3.Session", lambda: _FakeSession(fake_client))

    with pytest.raises(object_storage.ObjectStorageError):
        await object_storage.delete_bytes("documents/t1/d1/a.pdf")


@pytest.mark.asyncio
async def test_generate_presigned_url_inclui_content_disposition(monkeypatch):
    _patch_settings(monkeypatch)
    fake_client = MagicMock()
    fake_client.generate_presigned_url = AsyncMock(return_value="https://s3.example.com/signed")
    monkeypatch.setattr("aioboto3.Session", lambda: _FakeSession(fake_client))

    url = await object_storage.generate_presigned_url("documents/t1/d1/a.pdf", filename="contrato.pdf", expires_in=300)

    assert url == "https://s3.example.com/signed"
    _, kwargs = fake_client.generate_presigned_url.call_args
    assert kwargs["Params"]["ResponseContentDisposition"] == 'attachment; filename="contrato.pdf"'
    assert kwargs["ExpiresIn"] == 300


@pytest.mark.asyncio
async def test_generate_presigned_url_sem_filename_nao_seta_disposition(monkeypatch):
    _patch_settings(monkeypatch)
    fake_client = MagicMock()
    fake_client.generate_presigned_url = AsyncMock(return_value="https://s3.example.com/signed")
    monkeypatch.setattr("aioboto3.Session", lambda: _FakeSession(fake_client))

    await object_storage.generate_presigned_url("documents/t1/d1/a.pdf")

    _, kwargs = fake_client.generate_presigned_url.call_args
    assert "ResponseContentDisposition" not in kwargs["Params"]
