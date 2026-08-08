"""Fase 143 — TenantConfig.logo_url migrando de base64-no-Postgres pra
object storage S3-compatível (mesmo padrão do Document.arquivo_url na Fase
141). Cobre os 2 caminhos de POST /tenant/logo-upload, a resolução de
presigned URL fresca (_resolve_cached_logo_url), PUT /tenant/branding
limpando a storage key quando uma URL literal é setada, e o cap de
tamanho novo em BrandingUpdate."""
import uuid

import pytest
from fastapi import HTTPException, UploadFile
from pydantic import ValidationError
from starlette.datastructures import Headers

from app.api.v1.tenant import (
    upload_logo, update_branding, _resolve_cached_logo_url, BrandingUpdate,
)
from app.models.tenant import Tenant, TenantConfig


class _FakeUser:
    def __init__(self, id="u1", tenant_id=None, role="ADMIN"):
        self.id = id
        self.tenant_id = tenant_id
        self.role = role


class _FakeResult:
    def __init__(self, scalar=None):
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar


class _FakeDB:
    def __init__(self, tenant_row, config_row):
        self._results = [_FakeResult(scalar=tenant_row), _FakeResult(scalar=config_row)]
        self.added = []

    async def execute(self, query):
        return self._results.pop(0) if self._results else _FakeResult()

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        pass


def _tenant_and_config(**config_kwargs):
    # ORM defaults (mapped_column(default=...)) só se aplicam num flush real
    # contra um Engine — construindo o objeto direto em Python, precisam ser
    # passados explicitamente aqui.
    defaults = {
        "primary_color": "#C9A84C", "secondary_color": "#1A1A1A",
        "accent_color": "#F5F0E8", "app_name": "AFJ CORE",
    }
    defaults.update(config_kwargs)
    tenant = Tenant(id=uuid.uuid4(), name="Escritorio Teste", slug="teste")
    config = TenantConfig(id=uuid.uuid4(), tenant_id=tenant.id, **defaults)
    return tenant, config


def _upload_file(content=b"fake png bytes", filename="logo.png", content_type="image/png"):
    import io
    return UploadFile(io.BytesIO(content), filename=filename, headers=Headers({"content-type": content_type}))


# ─── POST /tenant/logo-upload ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_sem_s3_mantem_caminho_legado_base64(monkeypatch):
    monkeypatch.setattr("app.integrations.object_storage.is_configured", lambda: False)
    tenant, config = _tenant_and_config()
    db = _FakeDB(tenant, config)

    resp = await upload_logo(file=_upload_file(), current_user=_FakeUser(tenant_id=tenant.id), db=db)

    assert resp["logo_url"].startswith("data:image/png;base64,")
    assert config.logo_url == resp["logo_url"]
    assert config.logo_storage_key is None
    assert config.logo_mimetype is None


@pytest.mark.asyncio
async def test_upload_com_s3_configurado_grava_storage_key(monkeypatch):
    monkeypatch.setattr("app.integrations.object_storage.is_configured", lambda: True)

    async def _fake_upload_bytes(**kwargs):
        return f"tenants/{kwargs['tenant_id']}/logo.png"

    async def _fake_presigned(key, filename=None, expires_in=300):
        return f"https://s3.example.com/{key}?sig=abc"

    monkeypatch.setattr("app.integrations.object_storage.upload_bytes", _fake_upload_bytes)
    monkeypatch.setattr("app.integrations.object_storage.generate_presigned_url", _fake_presigned)

    tenant, config = _tenant_and_config()
    db = _FakeDB(tenant, config)

    resp = await upload_logo(file=_upload_file(), current_user=_FakeUser(tenant_id=tenant.id), db=db)

    assert config.logo_url is None
    assert config.logo_storage_key == f"tenants/{tenant.id}/logo.png"
    assert config.logo_mimetype == "image/png"
    assert resp["logo_url"] == f"https://s3.example.com/tenants/{tenant.id}/logo.png?sig=abc"


@pytest.mark.asyncio
async def test_upload_com_s3_falha_retorna_502(monkeypatch):
    from app.integrations.object_storage import ObjectStorageError

    monkeypatch.setattr("app.integrations.object_storage.is_configured", lambda: True)

    async def _fake_upload_bytes_falha(**kwargs):
        raise ObjectStorageError("bucket indisponível")

    monkeypatch.setattr("app.integrations.object_storage.upload_bytes", _fake_upload_bytes_falha)

    tenant, config = _tenant_and_config()
    db = _FakeDB(tenant, config)

    with pytest.raises(HTTPException) as exc_info:
        await upload_logo(file=_upload_file(), current_user=_FakeUser(tenant_id=tenant.id), db=db)
    assert exc_info.value.status_code == 502
    assert config.logo_storage_key is None  # nao gravou nada parcial


@pytest.mark.asyncio
async def test_upload_content_type_invalido_400():
    tenant, config = _tenant_and_config()
    db = _FakeDB(tenant, config)
    with pytest.raises(HTTPException) as exc_info:
        await upload_logo(
            file=_upload_file(content_type="application/pdf"),
            current_user=_FakeUser(tenant_id=tenant.id), db=db,
        )
    assert exc_info.value.status_code == 400


# ─── _resolve_cached_logo_url ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_cached_sem_storage_key_usa_logo_url_do_cache():
    result = await _resolve_cached_logo_url({"logo_url": "data:image/png;base64,QUJD", "logo_storage_key": None})
    assert result == "data:image/png;base64,QUJD"


@pytest.mark.asyncio
async def test_resolve_cached_com_storage_key_gera_presigned_fresca(monkeypatch):
    async def _fake_presigned(key, filename=None, expires_in=300):
        assert key == "tenants/t1/logo.png"
        assert expires_in == 3600
        return "https://s3.example.com/fresh-url"

    monkeypatch.setattr("app.integrations.object_storage.generate_presigned_url", _fake_presigned)
    result = await _resolve_cached_logo_url({"logo_storage_key": "tenants/t1/logo.png", "logo_url": None})
    assert result == "https://s3.example.com/fresh-url"


@pytest.mark.asyncio
async def test_resolve_cached_falha_presign_devolve_none(monkeypatch):
    from app.integrations.object_storage import ObjectStorageError

    async def _fake_presigned_falha(key, filename=None, expires_in=300):
        raise ObjectStorageError("s3 fora do ar")

    monkeypatch.setattr("app.integrations.object_storage.generate_presigned_url", _fake_presigned_falha)
    result = await _resolve_cached_logo_url({"logo_storage_key": "tenants/t1/logo.png", "logo_url": None})
    assert result is None


# ─── PUT /tenant/branding — limpa storage key quando URL literal é setada ──

@pytest.mark.asyncio
async def test_branding_url_literal_limpa_storage_key_existente(monkeypatch):
    tenant, config = _tenant_and_config(
        logo_storage_key="tenants/t1/logo-antigo.png", logo_mimetype="image/png", logo_url=None,
    )
    db = _FakeDB(tenant, config)

    body = BrandingUpdate(logo_url="https://exemplo.com/logo-novo.png")
    resp = await update_branding(body, current_user=_FakeUser(tenant_id=tenant.id), db=db)

    assert config.logo_url == "https://exemplo.com/logo-novo.png"
    assert config.logo_storage_key is None
    assert config.logo_mimetype is None
    assert resp.logo_url == "https://exemplo.com/logo-novo.png"


@pytest.mark.asyncio
async def test_branding_sem_logo_url_no_body_preserva_storage_key(monkeypatch):
    async def _fake_presigned(key, filename=None, expires_in=300):
        return "https://s3.example.com/preservado"

    monkeypatch.setattr("app.integrations.object_storage.generate_presigned_url", _fake_presigned)

    tenant, config = _tenant_and_config(
        logo_storage_key="tenants/t1/logo.png", logo_mimetype="image/png", logo_url=None,
        primary_color="#000000",
    )
    db = _FakeDB(tenant, config)

    body = BrandingUpdate(primary_color="#111111")
    resp = await update_branding(body, current_user=_FakeUser(tenant_id=tenant.id), db=db)

    assert config.logo_storage_key == "tenants/t1/logo.png"  # intocado
    assert resp.logo_url == "https://s3.example.com/preservado"


# ─── BrandingUpdate — cap de tamanho ────────────────────────────────────────

def test_branding_update_rejeita_string_acima_do_cap():
    with pytest.raises(ValidationError):
        BrandingUpdate(logo_url="x" * 4_000_001)


def test_branding_update_aceita_string_dentro_do_cap():
    body = BrandingUpdate(logo_url="x" * 100)
    assert len(body.logo_url) == 100
