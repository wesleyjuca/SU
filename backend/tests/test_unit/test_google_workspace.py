"""Fase 139 — google_workspace.py: get_valid_token agora é por TENANT (conta
única do escritório), delegando pro hub genérico de credenciais (mesmo
mecanismo já usado por google_drive_doutrina, Fase 138.2)."""
import json

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


class _FakeUploadResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeUploadClient:
    """Captura a chamada de upload multipart pra inspecionar mimeType/conteúdo
    — mesmo padrão de fake client já usado em test_google_drive_client.py."""

    last_call = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, content=None):
        _FakeUploadClient.last_call = {"url": url, "headers": headers, "content": content}
        return _FakeUploadResponse({"id": "drive-file-id", "webViewLink": "https://drive.google.com/file-fake"})


@pytest.mark.asyncio
async def test_drive_upload_doc_converte_html_pra_google_doc(monkeypatch):
    """Fase 182 — upload de petição/contrato como Google Doc: a Drive API
    precisa receber mimeType de destino application/vnd.google-apps.document
    pra converter o HTML automaticamente (sem chamar a Docs API)."""
    import app.services.google_workspace as gw

    monkeypatch.setattr(gw.httpx, "AsyncClient", lambda **k: _FakeUploadClient())

    result = await gw.drive_upload_doc("token-fake", "Petição de Teste", "<p>conteúdo</p>")

    assert result == {"id": "drive-file-id", "link": "https://drive.google.com/file-fake"}
    body = _FakeUploadClient.last_call["content"].decode()
    metadata = json.loads(body.split("\r\n\r\n")[1].split("\r\n--")[0])
    assert metadata == {"name": "Petição de Teste", "mimeType": "application/vnd.google-apps.document"}
    assert "Content-Type: text/html" in body
    assert "<p>conteúdo</p>" in body


@pytest.mark.asyncio
async def test_drive_upload_sheet_converte_csv_pra_google_sheet(monkeypatch):
    """Fase 182 — export financeiro pro Sheets: mimeType de destino
    application/vnd.google-apps.spreadsheet converte o CSV automaticamente
    (sem chamar a Sheets API)."""
    import app.services.google_workspace as gw

    monkeypatch.setattr(gw.httpx, "AsyncClient", lambda **k: _FakeUploadClient())

    csv_bytes = "ID,Tipo\n1,RECEITA\n".encode("utf-8-sig")
    result = await gw.drive_upload_sheet("token-fake", "financeiro", csv_bytes)

    assert result == {"id": "drive-file-id", "link": "https://drive.google.com/file-fake"}
    body = _FakeUploadClient.last_call["content"]
    assert b'"mimeType": "application/vnd.google-apps.spreadsheet"' in body
    assert b"Content-Type: text/csv" in body
    assert csv_bytes in body


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
