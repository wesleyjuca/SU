"""Fase 182 — Google Docs/Sheets via a Drive API já autorizada (drive.file):
os dois novos endpoints (drive-save-doc, financial export/google-sheets)
devem devolver 422 — nunca vazar um 500 — quando o Google Workspace do
escritório não está habilitado/conectado, mesmo padrão de erro já usado
pelo /drive-save existente.

Fase 184 — os mesmos dois endpoints, agora com o Google Workspace
conectado (mockado): devem gravar uma AuditLog com resource_type/
resource_id (mesmo padrão de approvals.py, Fase 174.8) e, no export
financeiro, avisar (não bloquear) quando alguma descrição parecer conter
CPF/CNPJ."""
import uuid

import pytest
from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.models.financial import FinancialEntry
from app.models.tenant import TenantConfig

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


async def _get_tenant_id(client, auth_headers: dict) -> uuid.UUID:
    res = await client.get("/api/v1/users/me", headers=auth_headers)
    assert res.status_code == 200
    return uuid.UUID(res.json()["tenant_id"])


async def _habilitar_google_workspace(tenant_id: uuid.UUID) -> bool:
    """Liga cfg.modules_enabled.google_workspace pro teste e devolve o valor
    anterior (pra restaurar no finally — não deixar rastro em ambiente real)."""
    async with AsyncSessionLocal() as db:
        cfg = (await db.execute(
            select(TenantConfig).where(TenantConfig.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if not cfg:
            cfg = TenantConfig(tenant_id=tenant_id, modules_enabled={})
            db.add(cfg)
        anterior = dict(cfg.modules_enabled or {})
        modules = dict(cfg.modules_enabled or {})
        modules["google_workspace"] = True
        cfg.modules_enabled = modules
        await db.commit()
        return anterior


async def _restaurar_modules_enabled(tenant_id: uuid.UUID, anterior: dict):
    async with AsyncSessionLocal() as db:
        cfg = (await db.execute(
            select(TenantConfig).where(TenantConfig.tenant_id == tenant_id)
        )).scalar_one_or_none()
        if cfg:
            cfg.modules_enabled = anterior
            await db.commit()


@pytest.fixture
async def google_workspace_habilitado(client, auth_headers, monkeypatch):
    """Liga o módulo pro tenant do usuário de teste + mocka as chamadas HTTP
    reais ao Google (get_valid_token/drive_upload_doc/drive_upload_sheet) —
    o que está sob teste aqui é a bookkeeping (audit trail/aviso de PII), não
    a integração HTTP em si (já coberta por test_google_workspace.py)."""
    tenant_id = await _get_tenant_id(client, auth_headers)
    anterior = await _habilitar_google_workspace(tenant_id)

    import app.services.google_workspace as gw

    async def _fake_token(db, tid):
        return "token-fake-184"

    async def _fake_upload_doc(token, nome, html):
        return {"id": "gdoc-fake-id", "link": "https://docs.google.com/doc-fake"}

    async def _fake_upload_sheet(token, nome, csv_bytes):
        return {"id": "gsheet-fake-id", "link": "https://sheets.google.com/sheet-fake"}

    monkeypatch.setattr(gw, "get_valid_token", _fake_token)
    monkeypatch.setattr(gw, "drive_upload_doc", _fake_upload_doc)
    monkeypatch.setattr(gw, "drive_upload_sheet", _fake_upload_sheet)

    try:
        yield tenant_id
    finally:
        await _restaurar_modules_enabled(tenant_id, anterior)


async def test_drive_save_doc_grava_audit_log_com_resource(client, auth_headers, google_workspace_habilitado):
    tenant_id = google_workspace_habilitado
    async with AsyncSessionLocal() as db:
        doc = Document(titulo="Doc de teste 184", conteudo_html="<p>oi</p>", status="RASCUNHO", tenant_id=tenant_id)
        db.add(doc)
        await db.commit()
        doc_id = doc.id

    try:
        res = await client.post(f"/api/v1/integrations/google/drive-save-doc/{doc_id}", headers=auth_headers)
        assert res.status_code == 201

        async with AsyncSessionLocal() as db:
            log = (await db.execute(
                select(AuditLog).where(
                    AuditLog.action == "GOOGLE_EXPORT:DOCUMENT_AS_DOC",
                    AuditLog.resource_id == doc_id,
                )
            )).scalars().first()
            assert log is not None
            assert log.resource_type == "DOCUMENT"
            assert log.tenant_id == tenant_id
            assert log.new_value.get("google_doc_id") == "gdoc-fake-id"
    finally:
        async with AsyncSessionLocal() as db:
            d = await db.get(Document, doc_id)
            if d:
                await db.delete(d)
                await db.commit()


async def test_export_financial_google_sheets_grava_audit_log(client, auth_headers, google_workspace_habilitado):
    tenant_id = google_workspace_habilitado
    res = await client.post("/api/v1/financial/export/google-sheets", headers=auth_headers)
    assert res.status_code == 201
    assert "aviso_pii" not in res.json() or not res.json()["aviso_pii"]

    async with AsyncSessionLocal() as db:
        log = (await db.execute(
            select(AuditLog).where(
                AuditLog.action == "GOOGLE_EXPORT:FINANCIAL_SHEET",
                AuditLog.tenant_id == tenant_id,
            ).order_by(AuditLog.id.desc())
        )).scalars().first()
        assert log is not None
        assert log.resource_type == "FINANCIAL_EXPORT"
        assert log.new_value.get("google_sheet_id") == "gsheet-fake-id"


async def test_export_financial_google_sheets_avisa_pii_sem_bloquear(client, auth_headers, google_workspace_habilitado):
    tenant_id = google_workspace_habilitado
    async with AsyncSessionLocal() as db:
        entry = FinancialEntry(
            tipo="DESPESA", descricao="Pagamento a Fulano CPF 123.456.789-01",
            valor=100, status="PENDENTE", tenant_id=tenant_id,
        )
        db.add(entry)
        await db.commit()
        entry_id = entry.id

    try:
        res = await client.post("/api/v1/financial/export/google-sheets", headers=auth_headers)
        assert res.status_code == 201
        body = res.json()
        assert body.get("aviso_pii"), "esperava aviso_pii quando uma descrição tem CPF-like"

        async with AsyncSessionLocal() as db:
            log = (await db.execute(
                select(AuditLog).where(
                    AuditLog.action == "GOOGLE_EXPORT:FINANCIAL_SHEET",
                    AuditLog.tenant_id == tenant_id,
                ).order_by(AuditLog.id.desc())
            )).scalars().first()
            assert log.contains_pii is True
    finally:
        async with AsyncSessionLocal() as db:
            e = await db.get(FinancialEntry, entry_id)
            if e:
                await db.delete(e)
                await db.commit()
