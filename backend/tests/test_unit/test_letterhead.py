"""Fase 143 — app/services/letterhead.py::resolve_logo_data_url — resolve o
logo do timbrado do escritório (S3 quando migrado, base64 legado senão),
sem que app/utils/pdf_builder.py precise mudar (continua recebendo um
data:...;base64,... completo nos dois casos)."""
import base64

import pytest

from app.models.tenant import TenantConfig
from app.services.letterhead import resolve_logo_data_url


def _cfg(logo_url=None, logo_storage_key=None, logo_mimetype=None):
    return TenantConfig(tenant_id="t1", logo_url=logo_url, logo_storage_key=logo_storage_key, logo_mimetype=logo_mimetype)


@pytest.mark.asyncio
async def test_sem_cfg_devolve_none():
    assert await resolve_logo_data_url(None) is None


@pytest.mark.asyncio
async def test_sem_storage_key_devolve_logo_url_legado():
    cfg = _cfg(logo_url="data:image/png;base64,QUJD")
    assert await resolve_logo_data_url(cfg) == "data:image/png;base64,QUJD"


@pytest.mark.asyncio
async def test_sem_storage_key_e_sem_logo_url_devolve_none():
    cfg = _cfg()
    assert await resolve_logo_data_url(cfg) is None


@pytest.mark.asyncio
async def test_com_storage_key_busca_bytes_e_remonta_data_url(monkeypatch):
    cfg = _cfg(logo_storage_key="tenants/t1/logo.png", logo_mimetype="image/png")

    async def _fake_get_bytes(key):
        assert key == "tenants/t1/logo.png"
        return b"bytes do logo"

    monkeypatch.setattr("app.integrations.object_storage.get_bytes", _fake_get_bytes)

    result = await resolve_logo_data_url(cfg)
    expected = "data:image/png;base64," + base64.b64encode(b"bytes do logo").decode()
    assert result == expected


@pytest.mark.asyncio
async def test_com_storage_key_sem_mimetype_usa_fallback_png(monkeypatch):
    cfg = _cfg(logo_storage_key="tenants/t1/logo.png", logo_mimetype=None)

    async def _fake_get_bytes(key):
        return b"x"

    monkeypatch.setattr("app.integrations.object_storage.get_bytes", _fake_get_bytes)
    result = await resolve_logo_data_url(cfg)
    assert result.startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_falha_no_s3_devolve_none(monkeypatch):
    from app.integrations.object_storage import ObjectStorageError

    cfg = _cfg(logo_storage_key="tenants/t1/logo.png", logo_mimetype="image/png")

    async def _fake_get_bytes_falha(key):
        raise ObjectStorageError("s3 fora do ar")

    monkeypatch.setattr("app.integrations.object_storage.get_bytes", _fake_get_bytes_falha)
    assert await resolve_logo_data_url(cfg) is None
