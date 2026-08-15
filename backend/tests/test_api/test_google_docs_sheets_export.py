"""Fase 182 — Google Docs/Sheets via a Drive API já autorizada (drive.file):
os dois novos endpoints (drive-save-doc, financial export/google-sheets)
devem devolver 422 — nunca vazar um 500 — quando o Google Workspace do
escritório não está habilitado/conectado, mesmo padrão de erro já usado
pelo /drive-save existente."""
import pytest
import uuid


pytestmark = pytest.mark.anyio


async def test_drive_save_doc_sem_google_conectado_e_422(client, auth_headers: dict):
    doc_id = str(uuid.uuid4())
    res = await client.post(
        f"/api/v1/integrations/google/drive-save-doc/{doc_id}",
        headers=auth_headers,
    )
    assert res.status_code == 422


async def test_export_financial_google_sheets_sem_google_conectado_e_422(client, auth_headers: dict):
    res = await client.post(
        "/api/v1/financial/export/google-sheets",
        headers=auth_headers,
    )
    assert res.status_code == 422
