"""Fase 208.2 — CRM previsão de caixa: GET /crm/previsao-caixa combina
pipeline ponderado (Opportunity aberta × probabilidade, bucketado por
expected_close) com receita já PENDENTE (FinancialEntry), por mês, próximos
6 meses. Postgres real: confirma que só oportunidades ABERTAS contam pro
pipeline, só receita PENDENTE conta pro previsto, e que datas fora da janela
de 6 meses não aparecem em nenhum bucket."""
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.api.v1.crm import previsao_caixa
from app.db.base import AsyncSessionLocal
from app.models.client import Client
from app.models.crm import Opportunity
from app.models.financial import FinancialEntry
from app.models.tenant import Tenant

pytestmark = pytest.mark.anyio


class _CurrentUser:
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id


def _add_months(d: date, n: int) -> date:
    y, m = d.year, d.month + n
    while m > 12:
        m -= 12
        y += 1
    return date(y, m, 1)


@pytest.fixture
async def cenario():
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant 208.2", slug=f"teste-208-2-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        cliente = Client(tipo="PF", nome_completo="Cliente 208.2", tenant_id=tenant.id)
        db.add(cliente)
        await db.flush()

        hoje = date.today()
        fora_da_janela = _add_months(hoje, 7)

        db.add_all([
            # Conta: aberta, dentro da janela — 1000 * 50% = 500
            Opportunity(tenant_id=tenant.id, client_id=cliente.id, titulo="Aberta dentro",
                        valor_estimado=Decimal("1000.00"), estagio="PROPOSTA", probabilidade=50,
                        expected_close=hoje),
            # Não conta: GANHO (fechada) mesmo com expected_close dentro da janela
            Opportunity(tenant_id=tenant.id, client_id=cliente.id, titulo="Ganha",
                        valor_estimado=Decimal("500.00"), estagio="GANHO", probabilidade=100,
                        expected_close=hoje),
            # Não conta: fora da janela de 6 meses
            Opportunity(tenant_id=tenant.id, client_id=cliente.id, titulo="Fora da janela",
                        valor_estimado=Decimal("2000.00"), estagio="NEGOCIACAO", probabilidade=80,
                        expected_close=fora_da_janela),
            # Conta: receita RECEITA/PENDENTE dentro da janela — 300
            FinancialEntry(tipo="RECEITA", descricao="honorarios previstos", valor=Decimal("300.00"),
                            status="PENDENTE", data_vencimento=hoje, client_id=cliente.id, tenant_id=tenant.id),
            # Não conta: já PAGO
            FinancialEntry(tipo="RECEITA", descricao="honorarios pagos", valor=Decimal("999.00"),
                            status="PAGO", data_vencimento=hoje, data_pagamento=hoje,
                            client_id=cliente.id, tenant_id=tenant.id),
            # Não conta: DESPESA (mesmo PENDENTE)
            FinancialEntry(tipo="DESPESA", descricao="custas", valor=Decimal("100.00"),
                            status="PENDENTE", data_vencimento=hoje, client_id=cliente.id, tenant_id=tenant.id),
        ])
        await db.commit()
        ids = {"tenant": tenant.id, "cliente": cliente.id}
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(Opportunity.__table__.delete().where(Opportunity.tenant_id == ids["tenant"]))
        await db.execute(FinancialEntry.__table__.delete().where(FinancialEntry.tenant_id == ids["tenant"]))
        await db.execute(Client.__table__.delete().where(Client.id == ids["cliente"]))
        await db.execute(Tenant.__table__.delete().where(Tenant.id == ids["tenant"]))
        await db.commit()


async def test_previsao_combina_pipeline_ponderado_e_receita_pendente(cenario):
    async with AsyncSessionLocal() as db:
        resp = await previsao_caixa(current_user=_CurrentUser(cenario["tenant"]), db=db)

    assert len(resp["meses"]) == 6
    mes_atual = resp["meses"][0]
    hoje = date.today()
    assert mes_atual["mes"] == f"{hoje.year:04d}-{hoje.month:02d}"
    assert mes_atual["pipeline_ponderado"] == 500.0
    assert mes_atual["receita_prevista"] == 300.0
    assert mes_atual["total"] == 800.0

    # Nenhum bucket (incluindo o último, mês 6) deve conter a oportunidade
    # de 7 meses no futuro — fora da janela.
    total_pipeline_janela = sum(m["pipeline_ponderado"] for m in resp["meses"])
    assert total_pipeline_janela == 500.0


async def test_sem_dados_devolve_6_meses_zerados(cenario):
    async with AsyncSessionLocal() as db:
        outro_tenant = Tenant(name="Vazio 208.2", slug=f"vazio-208-2-{uuid.uuid4().hex[:8]}")
        db.add(outro_tenant)
        await db.commit()
        tid = outro_tenant.id
    try:
        async with AsyncSessionLocal() as db:
            resp = await previsao_caixa(current_user=_CurrentUser(tid), db=db)
        assert len(resp["meses"]) == 6
        assert all(m["pipeline_ponderado"] == 0.0 and m["receita_prevista"] == 0.0 for m in resp["meses"])
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(Tenant.__table__.delete().where(Tenant.id == tid))
            await db.commit()
