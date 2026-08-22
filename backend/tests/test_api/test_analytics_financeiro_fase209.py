"""Fase 209 (achado do walkthrough real via Playwright) — GET /system/analytics/
financeiro quebrava com `TypeError: float() argument must be a string or a real
number, not 'Row'` sempre que o tenant tinha pelo menos 1 FinancialEntry.
Causa raiz: a query de totais rotulava a soma agregada como `.label("t")`, mas
`Row.t` é um atributo interno depreciado do SQLAlchemy (alias pra tupla da
própria linha) — `r.t` retornava a linha inteira, não o valor agregado.
Reproduzido com Postgres real; o dashboard nunca tinha exercitado esse
endpoint num walkthrough de verdade antes desta fase."""
import uuid
from datetime import date
from decimal import Decimal

import pytest

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
async def cenario():
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant 209 financeiro", slug=f"teste-209-fin-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        adv = User(
            email=f"adv-209-fin-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
            full_name="Advogado Teste 209", role="ADVOGADO", tenant_id=tenant.id,
        )
        db.add(adv)
        await db.flush()

        entradas = [
            FinancialEntry(tipo="RECEITA", descricao="honorário pago", valor=Decimal("1500.00"),
                            status="PAGO", data_pagamento=date(2026, 6, 1), tenant_id=tenant.id),
            FinancialEntry(tipo="RECEITA", descricao="honorário pendente", valor=Decimal("800.00"),
                            status="PENDENTE", data_vencimento=date(2026, 8, 1), tenant_id=tenant.id),
            FinancialEntry(tipo="DESPESA", descricao="aluguel pago", valor=Decimal("300.00"),
                            status="PAGO", data_pagamento=date(2026, 6, 5), tenant_id=tenant.id),
        ]
        db.add_all(entradas)
        await db.commit()
        ids = {"tenant": tenant.id, "adv": adv.id}
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(FinancialEntry.__table__.delete().where(FinancialEntry.tenant_id == ids["tenant"]))
        await db.execute(User.__table__.delete().where(User.id == ids["adv"]))
        await db.execute(Tenant.__table__.delete().where(Tenant.id == ids["tenant"]))
        await db.commit()


async def test_nao_quebra_com_lancamentos_financeiros_reais(cenario):
    async with AsyncSessionLocal() as db:
        resp = await analytics_financeiro(
            meses=6, force_refresh=True,
            current_user=_CurrentUser(cenario["tenant"]), db=db,
        )
    assert resp["summary"]["receitas_pagas"] == 1500.0
    assert resp["summary"]["receitas_pendentes"] == 800.0
    assert resp["summary"]["despesas_pagas"] == 300.0
    assert resp["summary"]["despesas_pendentes"] == 0.0
