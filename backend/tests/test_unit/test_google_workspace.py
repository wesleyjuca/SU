"""Fase 139 — google_workspace.py: get_valid_token agora é por TENANT (conta
única do escritório), delegando pro hub genérico de credenciais (mesmo
mecanismo já usado por google_drive_doutrina, Fase 138.2)."""
import pytest

from app.services.google_workspace import get_valid_token, GoogleNotConnected


@pytest.mark.asyncio
async def test_get_valid_token_sem_conexao_levanta_not_connected(monkeypatch):
    import app.services.google_workspace as gw

    async def _sem_credencial(db, tenant_id, provider):
        assert provider == "google_workspace"
        return None

    monkeypatch.setattr(gw.integration_hub, "get_credentials", _sem_credencial)

    with pytest.raises(GoogleNotConnected):
        await get_valid_token(db=None, tenant_id="tenant-a")


@pytest.mark.asyncio
async def test_get_valid_token_devolve_access_token(monkeypatch):
    import app.services.google_workspace as gw

    async def _com_credencial(db, tenant_id, provider):
        assert tenant_id == "tenant-a"
        assert provider == "google_workspace"
        return {"access_token": "TOKEN_ESCRITORIO", "oauth_refresh_token": "r1"}

    monkeypatch.setattr(gw.integration_hub, "get_credentials", _com_credencial)

    token = await get_valid_token(db=None, tenant_id="tenant-a")
    assert token == "TOKEN_ESCRITORIO"


@pytest.mark.asyncio
async def test_get_valid_token_credenciais_sem_access_token_levanta_not_connected(monkeypatch):
    """Defesa em profundidade: se por algum motivo `get_credentials` devolver
    um dict sem `access_token` (dado corrompido/parcial), trata como
    desconectado em vez de propagar um KeyError."""
    import app.services.google_workspace as gw

    async def _credencial_incompleta(db, tenant_id, provider):
        return {"oauth_refresh_token": "r1"}

    monkeypatch.setattr(gw.integration_hub, "get_credentials", _credencial_incompleta)

    with pytest.raises(GoogleNotConnected):
        await get_valid_token(db=None, tenant_id="tenant-a")
