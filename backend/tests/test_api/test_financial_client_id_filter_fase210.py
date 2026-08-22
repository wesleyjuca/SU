"""Fase 210 (achado da auditoria adversarial da Fase 209) — `GET /financial`
nunca declarava o parâmetro `client_id`: FastAPI o descartava silenciosamente
e a navegação contextual do Cliente 360 (Fase 205.3) devolvia TODOS os
lançamentos do tenant em vez de só os do cliente. Confirmado empiricamente
via HTTP real que não vazava dado cross-tenant — só não filtrava (own-tenant
over-fetch, não um leak)."""
import uuid
from decimal import Decimal

import pytest

from app.api.v1.financial import list_entries
from app.db.base import AsyncSessionLocal
from app.models.client import Client
from app.models.financial import FinancialEntry
from app.models.tenant import Tenant
from app.models.user import User

pytestmark = pytest.mark.anyio


class _CurrentUser:
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id


@pytest.fixture
async def cenario():
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant 210 financeiro", slug=f"teste-210-fin-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        adv = User(
            email=f"adv-210-fin-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
            full_name="Advogado Teste 210", role="ADVOGADO", tenant_id=tenant.id,
        )
        cliente_a = Client(tipo="PF", nome_completo="Cliente A 210", tenant_id=tenant.id)
        cliente_b = Client(tipo="PF", nome_completo="Cliente B 210", tenant_id=tenant.id)
        db.add_all([adv, cliente_a, cliente_b])
        await db.flush()

        entradas = [
            FinancialEntry(tipo="RECEITA", descricao="do cliente A", valor=Decimal("100.00"),
                            status="PAGO", client_id=cliente_a.id, tenant_id=tenant.id),
            FinancialEntry(tipo="RECEITA", descricao="do cliente B", valor=Decimal("200.00"),
                            status="PAGO", client_id=cliente_b.id, tenant_id=tenant.id),
            FinancialEntry(tipo="DESPESA", descricao="sem cliente", valor=Decimal("50.00"),
                            status="PAGO", tenant_id=tenant.id),
        ]
        db.add_all(entradas)
        await db.commit()
        ids = {"tenant": tenant.id, "adv": adv.id, "cliente_a": cliente_a.id, "cliente_b": cliente_b.id}
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(FinancialEntry.__table__.delete().where(FinancialEntry.tenant_id == ids["tenant"]))
        await db.execute(Client.__table__.delete().where(Client.tenant_id == ids["tenant"]))
        await db.execute(User.__table__.delete().where(User.id == ids["adv"]))
        await db.execute(Tenant.__table__.delete().where(Tenant.id == ids["tenant"]))
        await db.commit()


async def test_client_id_filtra_so_os_lancamentos_do_cliente(cenario):
    async with AsyncSessionLocal() as db:
        resp = await list_entries(
            client_id=str(cenario["cliente_a"]),
            current_user=_CurrentUser(cenario["tenant"]), db=db,
        )
    assert len(resp) == 1
    assert resp[0].descricao == "do cliente A"


async def test_sem_client_id_devolve_todos_do_tenant(cenario):
    async with AsyncSessionLocal() as db:
        resp = await list_entries(current_user=_CurrentUser(cenario["tenant"]), db=db)
    assert len(resp) == 3
