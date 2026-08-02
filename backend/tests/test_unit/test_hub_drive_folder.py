"""Fase 138.2 — endpoint PUT /integrations/hub/google_drive_doutrina/folder:
exige conexão prévia (Google OAuth já feito), valida o ID da pasta extraído
da URL/ID colado pelo ADMIN, grava em `extra_data` (não é segredo)."""
import pytest
from fastapi import HTTPException

from app.api.v1.integrations_hub import hub_set_drive_folder, DriveFolderBody


class _FakeDB:
    def __init__(self):
        self.committed = False

    async def commit(self):
        self.committed = True


class _FakeUser:
    tenant_id = "tenant-1"


class _FakeInteg:
    def __init__(self, credentials_enc="enc", extra_data=None):
        self.credentials_enc = credentials_enc
        self.extra_data = extra_data or {}


@pytest.mark.asyncio
async def test_sem_conexao_previa_rejeita(monkeypatch):
    from app.services import integration_hub as ih

    async def _get(db, tenant_id, provider):
        return None
    monkeypatch.setattr(ih, "get_integration", _get)

    with pytest.raises(HTTPException) as exc:
        await hub_set_drive_folder(
            DriveFolderBody(folder="1a2B3c4D5e6F7g8H9i0J"),
            current_user=_FakeUser(), db=_FakeDB(),
        )
    assert exc.value.status_code == 422
    assert "Conecte" in exc.value.detail


@pytest.mark.asyncio
async def test_conectado_mas_sem_credentials_enc_rejeita(monkeypatch):
    """Registro existe (ex.: desconectado depois) mas sem token — mesma
    rejeição de "conecte primeiro", não um erro genérico."""
    from app.services import integration_hub as ih

    async def _get(db, tenant_id, provider):
        return _FakeInteg(credentials_enc=None)
    monkeypatch.setattr(ih, "get_integration", _get)

    with pytest.raises(HTTPException) as exc:
        await hub_set_drive_folder(
            DriveFolderBody(folder="1a2B3c4D5e6F7g8H9i0J"),
            current_user=_FakeUser(), db=_FakeDB(),
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_folder_invalido_rejeita_com_422(monkeypatch):
    from app.services import integration_hub as ih

    async def _get(db, tenant_id, provider):
        return _FakeInteg()
    monkeypatch.setattr(ih, "get_integration", _get)

    with pytest.raises(HTTPException) as exc:
        await hub_set_drive_folder(
            DriveFolderBody(folder="não é uma pasta do drive"),
            current_user=_FakeUser(), db=_FakeDB(),
        )
    assert exc.value.status_code == 422
    assert "ID da pasta" in exc.value.detail


@pytest.mark.asyncio
async def test_folder_valido_grava_em_extra_data_e_preserva_o_resto(monkeypatch):
    from app.services import integration_hub as ih

    integ = _FakeInteg(extra_data={"algo_ja_existente": "valor"})

    async def _get(db, tenant_id, provider):
        return integ
    monkeypatch.setattr(ih, "get_integration", _get)

    db = _FakeDB()
    url = "https://drive.google.com/drive/u/0/folders/1a2B3c4D5e6F7g8H9i0J?usp=sharing"
    result = await hub_set_drive_folder(
        DriveFolderBody(folder=url), current_user=_FakeUser(), db=db,
    )

    assert result["folder_id"] == "1a2B3c4D5e6F7g8H9i0J"
    assert integ.extra_data == {"algo_ja_existente": "valor", "folder_id": "1a2B3c4D5e6F7g8H9i0J"}
    assert db.committed is True


@pytest.mark.asyncio
async def test_folder_id_cru_tambem_aceito(monkeypatch):
    from app.services import integration_hub as ih

    async def _get(db, tenant_id, provider):
        return _FakeInteg()
    monkeypatch.setattr(ih, "get_integration", _get)

    result = await hub_set_drive_folder(
        DriveFolderBody(folder="  1a2B3c4D5e6F7g8H9i0J  "), current_user=_FakeUser(), db=_FakeDB(),
    )
    assert result["folder_id"] == "1a2B3c4D5e6F7g8H9i0J"
