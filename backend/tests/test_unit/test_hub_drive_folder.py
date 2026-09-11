"""Fase 138.2 / Fase 258 / Fase pós-262 — endpoints de pasta do Google Drive.

`PUT /integrations/hub/{provider}/folder` configura a pasta ÚNICA de
salvamento — hoje só `google_workspace` (Fase pós-262: `google_drive_doutrina`
deixou de usar este endpoint, porque passou a suportar MÚLTIPLAS pastas de
pesquisa simultâneas — achado real: "a busca não percorre todas as pastas
compartilhadas"). `POST`/`DELETE .../google_drive_doutrina/folders` são os
novos endpoints de múltiplas pastas."""
import pytest
from fastapi import HTTPException

from app.api.v1.integrations_hub import (
    hub_set_folder, hub_add_pasta_doutrina, hub_remove_pasta_doutrina, FolderBody,
)
from app.services.integration_hub import pastas_drive_doutrina


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


# ─── pastas_drive_doutrina() — leitura retrocompatível ────────────────────────

def test_pastas_drive_doutrina_extra_data_vazio():
    assert pastas_drive_doutrina(None) == []
    assert pastas_drive_doutrina({}) == []


def test_pastas_drive_doutrina_le_formato_legado_folder_id_solto():
    assert pastas_drive_doutrina({"folder_id": "abc", "folder_name": "Doutrina"}) == [
        {"folder_id": "abc", "folder_name": "Doutrina"}
    ]


def test_pastas_drive_doutrina_le_lista_nova():
    extra = {"folders": [{"folder_id": "a", "folder_name": "X"}, {"folder_id": "b", "folder_name": "Y"}]}
    assert pastas_drive_doutrina(extra) == extra["folders"]


def test_pastas_drive_doutrina_prioriza_lista_nova_sobre_legado():
    extra = {"folder_id": "legado", "folders": [{"folder_id": "novo", "folder_name": "Novo"}]}
    assert pastas_drive_doutrina(extra) == [{"folder_id": "novo", "folder_name": "Novo"}]


def test_pastas_drive_doutrina_ignora_entrada_malformada():
    extra = {"folders": [{"folder_id": "a"}, {"sem_folder_id": True}, "string_invalida"]}
    assert pastas_drive_doutrina(extra) == [{"folder_id": "a"}]


# ─── PUT /{provider}/folder — restrito a google_workspace (pasta única) ──────

@pytest.mark.asyncio
async def test_put_folder_rejeita_google_drive_doutrina():
    """Fase pós-262 — doutrina não usa mais este endpoint (múltiplas pastas)."""
    with pytest.raises(HTTPException) as exc:
        await hub_set_folder(
            "google_drive_doutrina", FolderBody(folder_id="1a2B3c4D5e6F7g8H9i0J"),
            current_user=_FakeUser(), db=_FakeDB(),
        )
    assert exc.value.status_code == 422
    assert "múltiplas pastas" in exc.value.detail


@pytest.mark.asyncio
async def test_put_folder_rejeita_provider_invalido():
    with pytest.raises(HTTPException) as exc:
        await hub_set_folder(
            "stripe", FolderBody(folder_id="1a2B3c4D5e6F7g8H9i0J"),
            current_user=_FakeUser(), db=_FakeDB(),
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_put_folder_sem_conexao_previa_rejeita(monkeypatch):
    from app.services import integration_hub as ih

    async def _get(db, tenant_id, provider):
        return None
    monkeypatch.setattr(ih, "get_integration", _get)

    with pytest.raises(HTTPException) as exc:
        await hub_set_folder(
            "google_workspace", FolderBody(folder_id="1a2B3c4D5e6F7g8H9i0J"),
            current_user=_FakeUser(), db=_FakeDB(),
        )
    assert exc.value.status_code == 422
    assert "Conecte" in exc.value.detail


@pytest.mark.asyncio
async def test_put_folder_valido_grava_em_extra_data_e_preserva_o_resto(monkeypatch):
    from app.services import integration_hub as ih

    integ = _FakeInteg(extra_data={"algo_ja_existente": "valor"})

    async def _get(db, tenant_id, provider):
        return integ
    monkeypatch.setattr(ih, "get_integration", _get)

    db = _FakeDB()
    result = await hub_set_folder(
        "google_workspace",
        FolderBody(folder_id="1a2B3c4D5e6F7g8H9i0J", folder_name="Petições"),
        current_user=_FakeUser(), db=db,
    )

    assert result["folder_id"] == "1a2B3c4D5e6F7g8H9i0J"
    assert integ.extra_data == {
        "algo_ja_existente": "valor", "folder_id": "1a2B3c4D5e6F7g8H9i0J", "folder_name": "Petições",
    }
    assert db.committed is True
    assert "salvamento" in result["message"]


# ─── POST/DELETE .../google_drive_doutrina/folders — múltiplas pastas ────────

@pytest.mark.asyncio
async def test_add_pasta_doutrina_sem_conexao_previa_rejeita(monkeypatch):
    from app.services import integration_hub as ih

    async def _get(db, tenant_id, provider):
        return None
    monkeypatch.setattr(ih, "get_integration", _get)

    with pytest.raises(HTTPException) as exc:
        await hub_add_pasta_doutrina(
            FolderBody(folder_id="a"), current_user=_FakeUser(), db=_FakeDB(),
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_add_pasta_doutrina_primeira_pasta(monkeypatch):
    from app.services import integration_hub as ih

    integ = _FakeInteg(extra_data={})

    async def _get(db, tenant_id, provider):
        return integ
    monkeypatch.setattr(ih, "get_integration", _get)

    db = _FakeDB()
    result = await hub_add_pasta_doutrina(
        FolderBody(folder_id="a", folder_name="Doutrina Cível"), current_user=_FakeUser(), db=db,
    )
    assert result["pastas"] == [{"folder_id": "a", "folder_name": "Doutrina Cível"}]
    assert integ.extra_data == {"folders": [{"folder_id": "a", "folder_name": "Doutrina Cível"}]}
    assert db.committed is True


@pytest.mark.asyncio
async def test_add_pasta_doutrina_segunda_pasta_acumula(monkeypatch):
    """Achado real desta fase: 1 pasta só não bastava — adicionar uma 2ª
    pasta soma à lista, não substitui a 1ª."""
    from app.services import integration_hub as ih

    integ = _FakeInteg(extra_data={"folders": [{"folder_id": "a", "folder_name": "Cível"}]})

    async def _get(db, tenant_id, provider):
        return integ
    monkeypatch.setattr(ih, "get_integration", _get)

    result = await hub_add_pasta_doutrina(
        FolderBody(folder_id="b", folder_name="Penal"), current_user=_FakeUser(), db=_FakeDB(),
    )
    assert result["pastas"] == [
        {"folder_id": "a", "folder_name": "Cível"}, {"folder_id": "b", "folder_name": "Penal"},
    ]


@pytest.mark.asyncio
async def test_add_pasta_doutrina_ja_existente_nao_duplica_atualiza_nome(monkeypatch):
    from app.services import integration_hub as ih

    integ = _FakeInteg(extra_data={"folders": [{"folder_id": "a", "folder_name": "Nome antigo"}]})

    async def _get(db, tenant_id, provider):
        return integ
    monkeypatch.setattr(ih, "get_integration", _get)

    result = await hub_add_pasta_doutrina(
        FolderBody(folder_id="a", folder_name="Nome novo"), current_user=_FakeUser(), db=_FakeDB(),
    )
    assert result["pastas"] == [{"folder_id": "a", "folder_name": "Nome novo"}]


@pytest.mark.asyncio
async def test_add_pasta_doutrina_migra_formato_legado(monkeypatch):
    """Um extra_data com o par legado `folder_id`/`folder_name` soltos (de
    antes desta fase) some ao adicionar — evita 2 fontes de verdade
    divergentes no banco."""
    from app.services import integration_hub as ih

    integ = _FakeInteg(extra_data={"folder_id": "legado", "folder_name": "Antiga"})

    async def _get(db, tenant_id, provider):
        return integ
    monkeypatch.setattr(ih, "get_integration", _get)

    await hub_add_pasta_doutrina(
        FolderBody(folder_id="nova", folder_name="Nova"), current_user=_FakeUser(), db=_FakeDB(),
    )
    assert "folder_id" not in integ.extra_data
    assert "folder_name" not in integ.extra_data
    assert integ.extra_data["folders"] == [
        {"folder_id": "legado", "folder_name": "Antiga"}, {"folder_id": "nova", "folder_name": "Nova"},
    ]


@pytest.mark.asyncio
async def test_remove_pasta_doutrina_integracao_inexistente_404(monkeypatch):
    from app.services import integration_hub as ih

    async def _get(db, tenant_id, provider):
        return None
    monkeypatch.setattr(ih, "get_integration", _get)

    with pytest.raises(HTTPException) as exc:
        await hub_remove_pasta_doutrina("a", current_user=_FakeUser(), db=_FakeDB())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_remove_pasta_doutrina_remove_so_a_pasta_certa(monkeypatch):
    from app.services import integration_hub as ih

    integ = _FakeInteg(extra_data={"folders": [
        {"folder_id": "a", "folder_name": "Cível"}, {"folder_id": "b", "folder_name": "Penal"},
    ]})

    async def _get(db, tenant_id, provider):
        return integ
    monkeypatch.setattr(ih, "get_integration", _get)

    result = await hub_remove_pasta_doutrina("a", current_user=_FakeUser(), db=_FakeDB())
    assert result["pastas"] == [{"folder_id": "b", "folder_name": "Penal"}]
    assert integ.extra_data["folders"] == [{"folder_id": "b", "folder_name": "Penal"}]
