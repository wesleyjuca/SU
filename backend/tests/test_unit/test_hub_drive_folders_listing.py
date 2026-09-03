"""Fase 258 — GET /integrations/hub/{provider}/folders: listagem real de
pastas do Drive via API (substitui o antigo fluxo de colar link/ID), e
POST /integrations/hub/google_drive_doutrina/sync-now (necessário pro
critério de aceite "salvar arquivo → pesquisar novamente" ser verificável
sem esperar a rodada diária do Celery Beat)."""
import pytest
from fastapi import HTTPException

from app.api.v1.integrations_hub import hub_list_folders, hub_drive_sync_now
from app.integrations.google_drive.client import DriveApiError


class _FakeUser:
    tenant_id = "tenant-1"


class _FakeInteg:
    def __init__(self, status="CONECTADA", extra_data=None):
        self.status = status
        self.extra_data = extra_data or {}


@pytest.mark.asyncio
async def test_hub_list_folders_provider_invalido_rejeita_com_422():
    with pytest.raises(HTTPException) as exc:
        await hub_list_folders("stripe", parent_id=None, current_user=_FakeUser(), db=None)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_hub_list_folders_sem_conexao_rejeita_com_422(monkeypatch):
    from app.services import integration_hub as ih

    async def _sem_credencial(db, tenant_id, provider):
        return None
    monkeypatch.setattr(ih, "get_credentials", _sem_credencial)

    with pytest.raises(HTTPException) as exc:
        await hub_list_folders("google_drive_doutrina", parent_id=None, current_user=_FakeUser(), db=None)
    assert exc.value.status_code == 422
    assert "Conecte" in exc.value.detail


@pytest.mark.asyncio
async def test_hub_list_folders_sucesso_devolve_pastas(monkeypatch):
    from app.services import integration_hub as ih

    async def _com_credencial(db, tenant_id, provider):
        return {"access_token": "token-fake"}
    monkeypatch.setattr(ih, "get_credentials", _com_credencial)

    async def _fake_listar(access_token, parent_id=None):
        assert access_token == "token-fake"
        return [{"id": "f1", "name": "Doutrina", "parents": None}]

    import app.integrations.google_drive.client as client_mod
    monkeypatch.setattr(client_mod, "listar_pastas", _fake_listar)

    result = await hub_list_folders("google_drive_doutrina", parent_id=None, current_user=_FakeUser(), db=None)
    assert result == {"pastas": [{"id": "f1", "name": "Doutrina", "parents": None}]}


@pytest.mark.asyncio
async def test_hub_list_folders_erro_classificado_vira_status_diferenciado(monkeypatch):
    from app.services import integration_hub as ih

    async def _com_credencial(db, tenant_id, provider):
        return {"access_token": "token-fake"}
    monkeypatch.setattr(ih, "get_credentials", _com_credencial)

    async def _fake_listar_403(access_token, parent_id=None):
        raise DriveApiError("escopo_insuficiente", 403, "reconecte")

    import app.integrations.google_drive.client as client_mod
    monkeypatch.setattr(client_mod, "listar_pastas", _fake_listar_403)

    with pytest.raises(HTTPException) as exc:
        await hub_list_folders("google_workspace", parent_id=None, current_user=_FakeUser(), db=None)
    assert exc.value.status_code == 403
    assert "reconecte" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_hub_list_folders_404_pasta_removida(monkeypatch):
    from app.services import integration_hub as ih

    async def _com_credencial(db, tenant_id, provider):
        return {"access_token": "token-fake"}
    monkeypatch.setattr(ih, "get_credentials", _com_credencial)

    async def _fake_listar_404(access_token, parent_id=None):
        raise DriveApiError("pasta_nao_encontrada", 404, "sumiu")

    import app.integrations.google_drive.client as client_mod
    monkeypatch.setattr(client_mod, "listar_pastas", _fake_listar_404)

    with pytest.raises(HTTPException) as exc:
        await hub_list_folders("google_drive_doutrina", parent_id="pasta-x", current_user=_FakeUser(), db=None)
    assert exc.value.status_code == 404


# ─── POST .../sync-now ──────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_sync_now_sem_conexao_rejeita_com_422(monkeypatch):
    from app.services import integration_hub as ih

    async def _sem_integ(db, tenant_id, provider):
        return None
    monkeypatch.setattr(ih, "get_integration", _sem_integ)

    with pytest.raises(HTTPException) as exc:
        await hub_drive_sync_now(current_user=_FakeUser(), db=None)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_sync_now_sem_pasta_configurada_rejeita_com_422(monkeypatch):
    from app.services import integration_hub as ih

    async def _integ_sem_pasta(db, tenant_id, provider):
        return _FakeInteg(status="CONECTADA", extra_data={})
    monkeypatch.setattr(ih, "get_integration", _integ_sem_pasta)

    with pytest.raises(HTTPException) as exc:
        await hub_drive_sync_now(current_user=_FakeUser(), db=None)
    assert exc.value.status_code == 422
    assert "pasta" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_sync_now_dispara_so_pro_tenant_do_chamador(monkeypatch):
    from app.services import integration_hub as ih

    async def _integ_ok(db, tenant_id, provider):
        return _FakeInteg(status="CONECTADA", extra_data={"folder_id": "f1"})
    monkeypatch.setattr(ih, "get_integration", _integ_ok)

    chamada = {}

    async def _fake_sync(db, tenant_id=None):
        chamada["tenant_id"] = tenant_id
        return {"tenants_sincronizados": 1, "processados": 3, "pulados": 0, "falhas": 0}

    import app.workers.tasks.google_drive_sync as sync_mod
    monkeypatch.setattr(sync_mod, "executar_sync_drive_doutrina", _fake_sync)

    result = await hub_drive_sync_now(current_user=_FakeUser(), db=None)
    assert chamada["tenant_id"] == "tenant-1"
    assert result["processados"] == 3
    assert "concluída" in result["message"].lower()
