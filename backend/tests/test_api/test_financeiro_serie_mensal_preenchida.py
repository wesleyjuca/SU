"""Rodada pós-166a43c (achado de disposição de tela, Fase 5 do plano
faseado) — `GET /system/analytics/financeiro` e `GET /financial/monthly`
só incluíam meses com ALGUM lançamento na série retornada. Um tenant com
atividade financeira em só 1 dos 6 meses pedidos devolvia uma série de
1 item — e o gráfico de barras (`MiniFinancialChart`/`FinanceiroCharts`,
largura fixa do card) renderizava essa única categoria cercada de espaço
em branco, tanto em `/dashboard` quanto em `/financeiro`. Confirmado ao
vivo via Playwright antes/depois da correção.

Prova: com um único lançamento PAGO no mês atual, os dois endpoints
precisam devolver a janela COMPLETA de meses (6), não só o mês com dado."""
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.api.v1.financial import monthly_summary
from app.api.v1.system import analytics_financeiro
from app.db.base import AsyncSessionLocal
from app.models.financial import FinancialEntry
from app.models.tenant import Tenant
from app.models.user import User

pytestmark = pytest.mark.anyio


class _CurrentUser:
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id


@pytest.fixture
async def cenario_um_mes():
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant serie mensal", slug=f"teste-serie-mensal-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        adv = User(
            email=f"adv-serie-mensal-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
            full_name="Advogado Teste Serie Mensal", role="ADVOGADO", tenant_id=tenant.id,
        )
        db.add(adv)
        await db.flush()

        hoje = date.today()
        db.add(FinancialEntry(
            tipo="RECEITA", descricao="honorário do mês corrente", valor=Decimal("1000.00"),
            status="PAGO", data_pagamento=hoje, tenant_id=tenant.id,
        ))
        await db.commit()
        ids = {"tenant": tenant.id, "adv": adv.id}
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(FinancialEntry.__table__.delete().where(FinancialEntry.tenant_id == ids["tenant"]))
        await db.execute(User.__table__.delete().where(User.id == ids["adv"]))
        await db.execute(Tenant.__table__.delete().where(Tenant.id == ids["tenant"]))
        await db.commit()


async def test_analytics_financeiro_preenche_janela_de_6_meses(cenario_um_mes):
    async with AsyncSessionLocal() as db:
        resp = await analytics_financeiro(
            meses=6, force_refresh=True,
            current_user=_CurrentUser(cenario_um_mes["tenant"]), db=db,
        )
    mensal = resp["mensal"]
    assert len(mensal) == 6, f"esperava 6 meses na janela, veio {len(mensal)}: {mensal}"
    # meses sem lançamento vêm com zero, não ausentes da lista.
    com_dado = [m for m in mensal if m["receitas"] > 0]
    assert len(com_dado) == 1
    sem_dado = [m for m in mensal if m is not com_dado[0]]
    assert all(m["receitas"] == 0 and m["despesas"] == 0 for m in sem_dado)


async def test_financial_monthly_preenche_janela_de_6_meses(cenario_um_mes):
    async with AsyncSessionLocal() as db:
        resp = await monthly_summary(current_user=_CurrentUser(cenario_um_mes["tenant"]), db=db)
    dados = resp["data"]
    assert len(dados) == 6, f"esperava 6 meses na janela, veio {len(dados)}: {dados}"
    com_dado = [m for m in dados if m["receitas"] > 0]
    assert len(com_dado) == 1
    assert com_dado[0]["receitas"] == 1000.0
    # ordem cronológica (mesma ordem que o gráfico espera no eixo X).
    assert dados == sorted(dados, key=lambda m: m["mes"])
