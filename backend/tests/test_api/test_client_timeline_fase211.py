"""Fase 211 (evolução de produto proposta na Fase 209) — timeline unificada
do Cliente 360: GET /clients/{id}/timeline agrega interações, marcos
processuais, pagamentos recebidos e petições protocoladas numa lista
cronológica única. Postgres real: confirma que os 4 tipos de evento
aparecem, ordenação por data desc, e isolamento cross-tenant."""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.api.v1.clients import client_timeline
from app.db.base import AsyncSessionLocal
from app.models.client import Client, ClientInteraction
from app.models.document import Document
from app.models.financial import FinancialEntry
from app.models.process import LegalProcess
from app.models.tenant import Tenant
from app.models.user import User

pytestmark = pytest.mark.anyio


class _CurrentUser:
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id


@pytest.fixture
async def cenario():
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant 211 timeline", slug=f"teste-211-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        adv = User(
            email=f"adv-211-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
            full_name="Advogado Teste 211", role="ADVOGADO", tenant_id=tenant.id,
        )
        cliente = Client(tipo="PF", nome_completo="Cliente Timeline 211", tenant_id=tenant.id)
        db.add_all([adv, cliente])
        await db.flush()

        interacao = ClientInteraction(
            client_id=cliente.id, tenant_id=tenant.id, tipo="LIGACAO",
            descricao="Ligou sobre o processo", created_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
        )
        processo = LegalProcess(
            numero_cnj=f"{uuid.uuid4().hex[:7]}-00.2026.0.00.0000", tribunal="TJSP",
            tenant_id=tenant.id, responsavel_id=adv.id, client_id=cliente.id, desfecho="EXITO",
            created_at=datetime(2026, 2, 1, tzinfo=timezone.utc), updated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        pagamento = FinancialEntry(
            tipo="RECEITA", descricao="Honorário pago", valor=Decimal("1000.00"), status="PAGO",
            data_pagamento=date(2026, 3, 10), client_id=cliente.id, tenant_id=tenant.id,
        )
        doc = Document(
            titulo="Petição inicial", tipo="PETICAO", status="PROTOCOLADO", client_id=cliente.id,
            tenant_id=tenant.id, protocolado_em=datetime(2026, 2, 15, tzinfo=timezone.utc),
        )
        db.add_all([interacao, processo, pagamento, doc])
        await db.commit()
        ids = {"tenant": tenant.id, "adv": adv.id, "cliente": cliente.id}
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(FinancialEntry.__table__.delete().where(FinancialEntry.tenant_id == ids["tenant"]))
        await db.execute(Document.__table__.delete().where(Document.tenant_id == ids["tenant"]))
        await db.execute(LegalProcess.__table__.delete().where(LegalProcess.tenant_id == ids["tenant"]))
        await db.execute(ClientInteraction.__table__.delete().where(ClientInteraction.tenant_id == ids["tenant"]))
        await db.execute(Client.__table__.delete().where(Client.tenant_id == ids["tenant"]))
        await db.execute(User.__table__.delete().where(User.id == ids["adv"]))
        await db.execute(Tenant.__table__.delete().where(Tenant.id == ids["tenant"]))
        await db.commit()


async def test_timeline_junta_os_4_tipos_de_evento_ordenados(cenario):
    async with AsyncSessionLocal() as db:
        eventos = await client_timeline(
            client_id=str(cenario["cliente"]), limit=50,
            current_user=_CurrentUser(cenario["tenant"]), db=db,
        )
    tipos = {e["tipo"] for e in eventos}
    assert tipos == {"interacao", "processo", "financeiro", "documento"}
    # processo aparece 2x (aberto + desfecho) — total 5 eventos
    assert len(eventos) == 5
    datas = [e["data"] for e in eventos]
    assert datas == sorted(datas, reverse=True)


async def test_timeline_outro_tenant_nao_encontrado(cenario):
    async with AsyncSessionLocal() as db:
        with pytest.raises(Exception):
            await client_timeline(
                client_id=str(cenario["cliente"]), limit=50,
                current_user=_CurrentUser(uuid.uuid4()), db=db,
            )
