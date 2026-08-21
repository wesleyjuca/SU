"""Fase 206.3 — comparativo de período em Relatórios: `date_from`/`date_to`
opcionais em GET /system/analytics/gestao. Postgres real: confirma que cada
bloco de métrica filtra pelo campo de data certo (data_pagamento pra
rentabilidade, created_at pra produtividade "novos no período", updated_at
como proxy pra "quando o desfecho foi registrado") e que sem período o
comportamento é idêntico ao de antes desta fase (histórico completo)."""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.api.v1.system import analytics_gestao
from app.db.base import AsyncSessionLocal
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
        tenant = Tenant(name="Tenant 206.3", slug=f"teste-206-3-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        adv = User(
            email=f"adv-206-3-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
            full_name="Advogado Teste 206.3", role="ADVOGADO", tenant_id=tenant.id,
        )
        db.add(adv)
        await db.flush()

        dentro = date(2026, 6, 15)
        fora = date(2026, 1, 5)
        dt_dentro = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
        dt_fora = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)

        fin_dentro = FinancialEntry(
            tipo="RECEITA", descricao="dentro do período", valor=Decimal("1000.00"),
            status="PAGO", data_pagamento=dentro, tenant_id=tenant.id,
        )
        fin_fora = FinancialEntry(
            tipo="RECEITA", descricao="fora do período", valor=Decimal("500.00"),
            status="PAGO", data_pagamento=fora, tenant_id=tenant.id,
        )
        proc_dentro = LegalProcess(
            numero_cnj=f"{uuid.uuid4().hex[:7]}-00.2026.0.00.0000", tribunal="TJSP",
            tenant_id=tenant.id, responsavel_id=adv.id,
            desfecho="EXITO", created_at=dt_dentro, updated_at=dt_dentro,
        )
        proc_fora = LegalProcess(
            numero_cnj=f"{uuid.uuid4().hex[:7]}-00.2026.0.00.0000", tribunal="TJSP",
            tenant_id=tenant.id, responsavel_id=adv.id,
            desfecho="DERROTA", created_at=dt_fora, updated_at=dt_fora,
        )
        db.add_all([fin_dentro, fin_fora, proc_dentro, proc_fora])
        await db.commit()
        ids = {"tenant": tenant.id, "adv": adv.id}
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(LegalProcess.__table__.delete().where(LegalProcess.tenant_id == ids["tenant"]))
        await db.execute(FinancialEntry.__table__.delete().where(FinancialEntry.tenant_id == ids["tenant"]))
        await db.execute(User.__table__.delete().where(User.id == ids["adv"]))
        await db.execute(Tenant.__table__.delete().where(Tenant.id == ids["tenant"]))
        await db.commit()


async def test_sem_periodo_conta_o_historico_completo(cenario):
    async with AsyncSessionLocal() as db:
        resp = await analytics_gestao(
            date_from=None, date_to=None,
            current_user=_CurrentUser(cenario["tenant"]), db=db,
        )
    total_resultado = sum(c["resultado"] for c in resp["rentabilidade_clientes"])
    assert total_resultado == 1500.0
    assert resp["taxa_exito"]["total_com_desfecho"] == 2


async def test_com_periodo_filtra_so_o_que_cai_dentro(cenario):
    async with AsyncSessionLocal() as db:
        resp = await analytics_gestao(
            date_from=date(2026, 6, 1), date_to=date(2026, 6, 30),
            current_user=_CurrentUser(cenario["tenant"]), db=db,
        )
    total_resultado = sum(c["resultado"] for c in resp["rentabilidade_clientes"])
    assert total_resultado == 1000.0
    assert resp["taxa_exito"]["total_com_desfecho"] == 1
    assert resp["taxa_exito"]["win_rate"] == 100.0
    adv_row = next(a for a in resp["produtividade_advogados"] if a["advogado"] == "Advogado Teste 206.3")
    assert adv_row["processos"] == 1  # só o processo criado dentro do período


async def test_periodo_anterior_captura_o_que_o_periodo_atual_exclui(cenario):
    async with AsyncSessionLocal() as db:
        resp = await analytics_gestao(
            date_from=date(2026, 1, 1), date_to=date(2026, 1, 31),
            current_user=_CurrentUser(cenario["tenant"]), db=db,
        )
    total_resultado = sum(c["resultado"] for c in resp["rentabilidade_clientes"])
    assert total_resultado == 500.0
    assert resp["taxa_exito"]["total_com_desfecho"] == 1
    assert resp["taxa_exito"]["win_rate"] == 0.0
