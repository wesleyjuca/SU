"""Fase 138.2 / Fase 258 — endpoint PUT /integrations/hub/{provider}/folder:
exige conexão prévia (Google OAuth já feito), recebe o folder_id JÁ RESOLVIDO
pela seleção no picker (Fase 258 — nunca mais um link/ID colado, o antigo
DriveFolderBody/hub_set_drive_folder/extrair_folder_id saiu do caminho de
escrita), grava em `extra_data` (não é segredo). Generalizado pra funcionar
tanto com `google_drive_doutrina` (pasta de pesquisa) quanto
`google_workspace` (pasta de salvamento, nova nesta fase)."""
import pytest
from fastapi import HTTPException

from app.api.v1.integrations_hub import hub_set_folder, FolderBody


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
        await hub_set_folder(
            "google_drive_doutrina", FolderBody(folder_id="1a2B3c4D5e6F7g8H9i0J"),
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
        await hub_set_folder(
            "google_drive_doutrina", FolderBody(folder_id="1a2B3c4D5e6F7g8H9i0J"),
            current_user=_FakeUser(), db=_FakeDB(),
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_folder_id_vazio_rejeita_com_422(monkeypatch):
    from app.services import integration_hub as ih

    async def _get(db, tenant_id, provider):
        return _FakeInteg()
    monkeypatch.setattr(ih, "get_integration", _get)

    with pytest.raises(HTTPException) as exc:
        await hub_set_folder(
            "google_drive_doutrina", FolderBody(folder_id="   "),
            current_user=_FakeUser(), db=_FakeDB(),
        )
    assert exc.value.status_code == 422
    assert "Selecione uma pasta" in exc.value.detail


@pytest.mark.asyncio
async def test_provider_invalido_rejeita_com_422():
    with pytest.raises(HTTPException) as exc:
        await hub_set_folder(
            "stripe", FolderBody(folder_id="1a2B3c4D5e6F7g8H9i0J"),
            current_user=_FakeUser(), db=_FakeDB(),
        )
    assert exc.value.status_code == 422
    assert "sem configuração de pasta" in exc.value.detail


@pytest.mark.asyncio
async def test_folder_valido_grava_em_extra_data_e_preserva_o_resto(monkeypatch):
    from app.services import integration_hub as ih

    integ = _FakeInteg(extra_data={"algo_ja_existente": "valor"})

    async def _get(db, tenant_id, provider):
        return integ
    monkeypatch.setattr(ih, "get_integration", _get)

    db = _FakeDB()
    result = await hub_set_folder(
        "google_drive_doutrina",
        FolderBody(folder_id="1a2B3c4D5e6F7g8H9i0J", folder_name="Doutrina 2026"),
        current_user=_FakeUser(), db=db,
    )

    assert result["folder_id"] == "1a2B3c4D5e6F7g8H9i0J"
    assert result["folder_name"] == "Doutrina 2026"
    assert integ.extra_data == {
        "algo_ja_existente": "valor", "folder_id": "1a2B3c4D5e6F7g8H9i0J", "folder_name": "Doutrina 2026",
    }
    assert db.committed is True
    assert "todo dia" in result["message"]


@pytest.mark.asyncio
async def test_folder_name_omitido_nao_grava_chave(monkeypatch):
    from app.services import integration_hub as ih

    integ = _FakeInteg(extra_data={})

    async def _get(db, tenant_id, provider):
        return integ
    monkeypatch.setattr(ih, "get_integration", _get)

    await hub_set_folder(
        "google_drive_doutrina", FolderBody(folder_id="1a2B3c4D5e6F7g8H9i0J"),
        current_user=_FakeUser(), db=_FakeDB(),
    )
    assert integ.extra_data == {"folder_id": "1a2B3c4D5e6F7g8H9i0J"}
    assert "folder_name" not in integ.extra_data


@pytest.mark.asyncio
async def test_google_workspace_tambem_aceito(monkeypatch):
    """Fase 258 — o endpoint não é mais hardcoded só pra google_drive_
    doutrina; google_workspace (pasta de salvamento) usa o mesmo caminho,
    com mensagem de sucesso diferente."""
    from app.services import integration_hub as ih

    integ = _FakeInteg()

    async def _get(db, tenant_id, provider):
        assert provider == "google_workspace"
        return integ
    monkeypatch.setattr(ih, "get_integration", _get)

    result = await hub_set_folder(
        "google_workspace", FolderBody(folder_id="1a2B3c4D5e6F7g8H9i0J", folder_name="Petições"),
        current_user=_FakeUser(), db=_FakeDB(),
    )
    assert result["folder_id"] == "1a2B3c4D5e6F7g8H9i0J"
    assert "salvamento" in result["message"]
