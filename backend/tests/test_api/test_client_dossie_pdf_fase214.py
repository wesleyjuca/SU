"""Fase 214 (4ª proposta de evolução da Fase 209) — dossiê do cliente em
PDF: GET /clients/{id}/dossie-pdf. Postgres real: confirma PDF válido com
conteúdo (não só status 200), gate de escrita restrito a
ADMIN/SOCIO/GESTOR e isolamento cross-tenant (404, não vazamento)."""
import uuid

import pytest
from fastapi import HTTPException

from app.api.v1.clients import client_dossie_pdf
from app.db.base import AsyncSessionLocal
from app.models.client import Client
from app.models.process import LegalProcess
from app.models.tenant import Tenant

pytestmark = pytest.mark.anyio


class _CurrentUser:
    def __init__(self, tenant_id, uid=None):
        self.tenant_id = tenant_id
        self.id = uid or uuid.uuid4()


@pytest.fixture
async def cenario():
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant 214 Dossie", slug=f"teste-214-{uuid.uuid4().hex[:8]}")
        outro_tenant = Tenant(name="Outro 214", slug=f"outro-214-{uuid.uuid4().hex[:8]}")
        db.add_all([tenant, outro_tenant])
        await db.flush()

        cliente = Client(
            nome_completo="Cliente Teste 214", tipo="PF", status="ATIVO",
            email="cliente214@example.com", tenant_id=tenant.id,
        )
        db.add(cliente)
        await db.flush()

        processo = LegalProcess(
            numero_cnj="0001234-56.2026.8.26.0100", tribunal="TJSP", situacao="ATIVO",
            client_id=cliente.id, tenant_id=tenant.id,
        )
        db.add(processo)
        await db.commit()
        ids = {"tenant": tenant.id, "outro_tenant": outro_tenant.id, "cliente": cliente.id}
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(LegalProcess.__table__.delete().where(LegalProcess.tenant_id == ids["tenant"]))
        await db.execute(Client.__table__.delete().where(Client.tenant_id == ids["tenant"]))
        await db.execute(Tenant.__table__.delete().where(Tenant.id.in_([ids["tenant"], ids["outro_tenant"]])))
        await db.commit()


async def test_dossie_pdf_gera_conteudo_valido(cenario):
    async with AsyncSessionLocal() as db:
        resp = await client_dossie_pdf(
            str(cenario["cliente"]), current_user=_CurrentUser(cenario["tenant"]), db=db,
        )
    assert resp.media_type == "application/pdf"
    assert resp.body[:4] == b"%PDF"
    assert len(resp.body) > 500
    assert f'dossie_{cenario["cliente"]}.pdf' in resp.headers["content-disposition"]


async def test_dossie_pdf_cliente_de_outro_tenant_404(cenario):
    async with AsyncSessionLocal() as db:
        with pytest.raises(HTTPException) as exc_info:
            await client_dossie_pdf(
                str(cenario["cliente"]), current_user=_CurrentUser(cenario["outro_tenant"]), db=db,
            )
    assert exc_info.value.status_code == 404
