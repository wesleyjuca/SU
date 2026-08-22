"""Fase 215 (5ª proposta de evolução da Fase 209) — simulação de honorários
vs. histórico real: GET /financial/honorarios-historico. Postgres real:
confirma que só RECEITA/HONORARIOS/PAGO conta, filtros de tipo_acao/desfecho
reduzem a amostra, amostra pequena (n<3) é sinalizada sem esconder os
números, área sem histórico devolve mensagem (não erro), lançamento sem
process_id fica de fora, e isolamento cross-tenant."""
import uuid
from decimal import Decimal

import pytest

from app.api.v1.financial import honorarios_historico
from app.db.base import AsyncSessionLocal
from app.models.client import Client
from app.models.financial import FinancialEntry
from app.models.process import LegalProcess
from app.models.tenant import Tenant

pytestmark = pytest.mark.anyio


class _CurrentUser:
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id


@pytest.fixture
async def cenario():
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant 215", slug=f"teste-215-{uuid.uuid4().hex[:8]}")
        outro_tenant = Tenant(name="Outro 215", slug=f"outro-215-{uuid.uuid4().hex[:8]}")
        db.add_all([tenant, outro_tenant])
        await db.flush()

        cliente = Client(tipo="PF", nome_completo="Cliente 215", tenant_id=tenant.id)
        db.add(cliente)
        await db.flush()

        proc_civil_exito = LegalProcess(
            tribunal="TJSP", area_direito="CIVIL", tipo_acao="Indenizatoria", desfecho="EXITO",
            situacao="ENCERRADO", client_id=cliente.id, tenant_id=tenant.id,
        )
        proc_civil_acordo = LegalProcess(
            tribunal="TJSP", area_direito="CIVIL", tipo_acao="Indenizatoria", desfecho="ACORDO",
            situacao="ENCERRADO", client_id=cliente.id, tenant_id=tenant.id,
        )
        proc_trabalhista = LegalProcess(
            tribunal="TRT", area_direito="TRABALHISTA", tipo_acao="Rescisoria", desfecho="EXITO",
            situacao="ENCERRADO", client_id=cliente.id, tenant_id=tenant.id,
        )
        db.add_all([proc_civil_exito, proc_civil_acordo, proc_trabalhista])
        await db.flush()

        db.add_all([
            # Conta: RECEITA/HONORARIOS/PAGO, CIVIL/EXITO — 3000
            FinancialEntry(tipo="RECEITA", categoria="HONORARIOS", descricao="hon 1", valor=Decimal("3000"),
                            status="PAGO", process_id=proc_civil_exito.id, client_id=cliente.id, tenant_id=tenant.id),
            # Conta: RECEITA/HONORARIOS/PAGO, CIVIL/ACORDO — 5000
            FinancialEntry(tipo="RECEITA", categoria="HONORARIOS", descricao="hon 2", valor=Decimal("5000"),
                            status="PAGO", process_id=proc_civil_acordo.id, client_id=cliente.id, tenant_id=tenant.id),
            # Conta: RECEITA/HONORARIOS/PAGO, TRABALHISTA — 8000
            FinancialEntry(tipo="RECEITA", categoria="HONORARIOS", descricao="hon 3", valor=Decimal("8000"),
                            status="PAGO", process_id=proc_trabalhista.id, client_id=cliente.id, tenant_id=tenant.id),
            # Não conta: DESPESA
            FinancialEntry(tipo="DESPESA", categoria="HONORARIOS", descricao="despesa", valor=Decimal("999999"),
                            status="PAGO", process_id=proc_civil_exito.id, client_id=cliente.id, tenant_id=tenant.id),
            # Não conta: status PENDENTE
            FinancialEntry(tipo="RECEITA", categoria="HONORARIOS", descricao="pendente", valor=Decimal("999999"),
                            status="PENDENTE", process_id=proc_civil_exito.id, client_id=cliente.id, tenant_id=tenant.id),
            # Não conta: categoria diferente
            FinancialEntry(tipo="RECEITA", categoria="CUSTAS", descricao="custas", valor=Decimal("999999"),
                            status="PAGO", process_id=proc_civil_exito.id, client_id=cliente.id, tenant_id=tenant.id),
            # Não conta: sem process_id (não há como saber a área)
            FinancialEntry(tipo="RECEITA", categoria="HONORARIOS", descricao="sem processo", valor=Decimal("999999"),
                            status="PAGO", process_id=None, client_id=cliente.id, tenant_id=tenant.id),
        ])
        await db.commit()
        ids = {"tenant": tenant.id, "outro_tenant": outro_tenant.id, "cliente": cliente.id}
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(FinancialEntry.__table__.delete().where(FinancialEntry.tenant_id == ids["tenant"]))
        await db.execute(LegalProcess.__table__.delete().where(LegalProcess.tenant_id == ids["tenant"]))
        await db.execute(Client.__table__.delete().where(Client.id == ids["cliente"]))
        await db.execute(Tenant.__table__.delete().where(Tenant.id.in_([ids["tenant"], ids["outro_tenant"]])))
        await db.commit()


async def test_media_mediana_min_max_area_civil(cenario):
    async with AsyncSessionLocal() as db:
        resp = await honorarios_historico(
            area_direito="CIVIL", tipo_acao=None, desfecho=None,
            current_user=_CurrentUser(cenario["tenant"]), db=db,
        )
    assert resp["n"] == 2
    assert resp["media"] == 4000.0
    assert resp["mediana"] == 4000.0
    assert resp["minimo"] == 3000.0
    assert resp["maximo"] == 5000.0
    assert resp["amostra_pequena"] is True


async def test_filtro_desfecho_reduz_amostra(cenario):
    async with AsyncSessionLocal() as db:
        resp = await honorarios_historico(
            area_direito="CIVIL", tipo_acao=None, desfecho="EXITO",
            current_user=_CurrentUser(cenario["tenant"]), db=db,
        )
    assert resp["n"] == 1
    assert resp["media"] == 3000.0
    assert resp["amostra_pequena"] is True
    assert "cautela" in resp["mensagem"]


async def test_area_sem_historico_devolve_mensagem(cenario):
    async with AsyncSessionLocal() as db:
        resp = await honorarios_historico(
            area_direito="PENAL", tipo_acao=None, desfecho=None,
            current_user=_CurrentUser(cenario["tenant"]), db=db,
        )
    assert resp["n"] == 0
    assert resp["media"] is None
    assert resp["mensagem"] is not None


async def test_isolamento_cross_tenant(cenario):
    async with AsyncSessionLocal() as db:
        resp = await honorarios_historico(
            area_direito="CIVIL", tipo_acao=None, desfecho=None,
            current_user=_CurrentUser(cenario["outro_tenant"]), db=db,
        )
    assert resp["n"] == 0
