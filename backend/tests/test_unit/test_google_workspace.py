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


# ─── Fase 258 — pasta de salvamento (parent_folder_id) ─────────────────────
@pytest.mark.asyncio
async def test_drive_upload_pdf_com_parent_folder_id_inclui_parents(monkeypatch):
    import app.services.google_workspace as gw

    monkeypatch.setattr(gw.httpx, "AsyncClient", lambda **k: _FakeUploadClient())

    await gw.drive_upload_pdf("token-fake", "Petição", b"%PDF-fake", parent_folder_id="pasta-123")

    body = _FakeUploadClient.last_call["content"].decode(errors="replace")
    metadata = json.loads(body.split("\r\n\r\n")[1].split("\r\n--")[0])
    assert metadata == {"name": "Petição.pdf", "mimeType": "application/pdf", "parents": ["pasta-123"]}


@pytest.mark.asyncio
async def test_drive_upload_pdf_sem_parent_folder_id_nao_inclui_parents(monkeypatch):
    """Regressão: quem não configurar pasta de salvamento continua com o
    comportamento de antes desta fase (raiz do Drive, sem chave `parents`)."""
    import app.services.google_workspace as gw

    monkeypatch.setattr(gw.httpx, "AsyncClient", lambda **k: _FakeUploadClient())

    await gw.drive_upload_pdf("token-fake", "Petição", b"%PDF-fake")

    body = _FakeUploadClient.last_call["content"].decode(errors="replace")
    metadata = json.loads(body.split("\r\n\r\n")[1].split("\r\n--")[0])
    assert "parents" not in metadata


@pytest.mark.asyncio
async def test_drive_upload_doc_com_parent_folder_id_inclui_parents(monkeypatch):
    import app.services.google_workspace as gw

    monkeypatch.setattr(gw.httpx, "AsyncClient", lambda **k: _FakeUploadClient())

    await gw.drive_upload_doc("token-fake", "Contrato", "<p>x</p>", parent_folder_id="pasta-456")

    body = _FakeUploadClient.last_call["content"].decode()
    metadata = json.loads(body.split("\r\n\r\n")[1].split("\r\n--")[0])
    assert metadata["parents"] == ["pasta-456"]


@pytest.mark.asyncio
async def test_drive_upload_sheet_com_parent_folder_id_inclui_parents(monkeypatch):
    import app.services.google_workspace as gw

    monkeypatch.setattr(gw.httpx, "AsyncClient", lambda **k: _FakeUploadClient())

    await gw.drive_upload_sheet("token-fake", "financeiro", b"a,b\n1,2", parent_folder_id="pasta-789")

    body = _FakeUploadClient.last_call["content"]
    assert b'"parents": ["pasta-789"]' in body


@pytest.mark.asyncio
async def test_get_configured_folder_id_sem_integracao_devolve_none(monkeypatch):
    import app.services.google_workspace as gw

    async def _sem_integ(db, tenant_id, provider):
        return None
    monkeypatch.setattr(gw.integration_hub, "get_integration", _sem_integ)

    assert await gw.get_configured_folder_id(db=None, tenant_id="tenant-a") is None


@pytest.mark.asyncio
async def test_get_configured_folder_id_le_extra_data(monkeypatch):
    import app.services.google_workspace as gw

    class _FakeInteg:
        extra_data = {"folder_id": "pasta-configurada"}

    async def _com_integ(db, tenant_id, provider):
        assert provider == "google_workspace"
        return _FakeInteg()
    monkeypatch.setattr(gw.integration_hub, "get_integration", _com_integ)

    assert await gw.get_configured_folder_id(db=None, tenant_id="tenant-a") == "pasta-configurada"


def test_classificar_erro_upload_drive_traduz_401():
    import httpx
    import app.services.google_workspace as gw

    resp = httpx.Response(401, json={"error": {"errors": [{"reason": "authError"}]}}, request=httpx.Request("POST", "https://example.com"))
    exc = httpx.HTTPStatusError("erro", request=resp.request, response=resp)

    status, detail = gw.classificar_erro_upload_drive(exc)
    assert status == 401
    assert "token" in detail.lower() or "reconecte" in detail.lower()


def test_classificar_erro_upload_drive_traduz_404_pasta_removida():
    import httpx
    import app.services.google_workspace as gw

    resp = httpx.Response(404, json={}, request=httpx.Request("POST", "https://example.com"))
    exc = httpx.HTTPStatusError("erro", request=resp.request, response=resp)

    status, detail = gw.classificar_erro_upload_drive(exc)
    assert status == 404
    assert "não encontrada" in detail.lower() or "removida" in detail.lower()
