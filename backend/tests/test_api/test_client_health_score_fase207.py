"""Fase 207.1 — score de saúde do cliente: GET /clients/{id}/health-score
combina 3 sinais já existentes (financeiro, engajamento, processual) num
score 0-100 puramente derivado (nenhum campo novo persistido). Postgres real:
confirma o score neutro sem histórico, e que cada sinal move o score na
direção esperada quando o dado existe."""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.api.v1.clients import client_health_score
from app.db.base import AsyncSessionLocal
from app.models.client import Client, ClientInteraction
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
        tenant = Tenant(name="Tenant 207.1", slug=f"teste-207-1-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        adv = User(
            email=f"adv-207-1-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
            full_name="Advogado Teste 207.1", role="ADVOGADO", tenant_id=tenant.id,
        )
        db.add(adv)
        await db.flush()
        cliente = Client(tipo="PF", nome_completo="Cliente Teste 207.1", tenant_id=tenant.id)
        db.add(cliente)
        await db.commit()
        ids = {"tenant": tenant.id, "adv": adv.id, "cliente": cliente.id}
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(LegalProcess.__table__.delete().where(LegalProcess.tenant_id == ids["tenant"]))
        await db.execute(FinancialEntry.__table__.delete().where(FinancialEntry.tenant_id == ids["tenant"]))
        await db.execute(ClientInteraction.__table__.delete().where(ClientInteraction.tenant_id == ids["tenant"]))
        await db.execute(Client.__table__.delete().where(Client.id == ids["cliente"]))
        await db.execute(User.__table__.delete().where(User.id == ids["adv"]))
        await db.execute(Tenant.__table__.delete().where(Tenant.id == ids["tenant"]))
        await db.commit()


async def test_sem_nenhum_historico_score_neutro(cenario):
    async with AsyncSessionLocal() as db:
        resp = await client_health_score(
            client_id=str(cenario["cliente"]), current_user=_CurrentUser(cenario["tenant"]), db=db,
        )
    # 40 (sem receita, nada atrasado) + 15 (sem interação, neutro) + 30 (sem desfecho, neutro) = 85
    assert resp["score"] == 85
    assert resp["banda"] == "saudavel"
    assert resp["componentes"]["financeiro"]["receita_total"] == 0
    assert resp["componentes"]["engajamento"]["dias_desde_ultima_interacao"] is None
    assert resp["componentes"]["processual"]["total_com_desfecho"] == 0


async def test_receita_atrasada_derruba_score_financeiro(cenario):
    async with AsyncSessionLocal() as db:
        db.add_all([
            FinancialEntry(
                tipo="RECEITA", descricao="honorarios", valor=Decimal("500.00"), status="PENDENTE",
                data_vencimento=date.today() - timedelta(days=10), client_id=cenario["cliente"], tenant_id=cenario["tenant"],
            ),
            FinancialEntry(
                tipo="RECEITA", descricao="honorarios pagos", valor=Decimal("500.00"), status="PAGO",
                data_vencimento=date.today() - timedelta(days=10), data_pagamento=date.today(),
                client_id=cenario["cliente"], tenant_id=cenario["tenant"],
            ),
        ])
        await db.commit()

    async with AsyncSessionLocal() as db:
        resp = await client_health_score(
            client_id=str(cenario["cliente"]), current_user=_CurrentUser(cenario["tenant"]), db=db,
        )
    # 1 de 2 receitas atrasada → 40 * (1 - 1/2) = 20
    assert resp["componentes"]["financeiro"]["pontos"] == 20
    assert resp["componentes"]["financeiro"]["receita_atrasada"] == 1
    assert resp["componentes"]["financeiro"]["receita_total"] == 2


async def test_interacao_recente_pontua_cheio_antiga_pontua_menos(cenario):
    async with AsyncSessionLocal() as db:
        db.add(ClientInteraction(
            client_id=cenario["cliente"], tenant_id=cenario["tenant"], tipo="EMAIL",
            descricao="contato recente", created_at=datetime.now(timezone.utc) - timedelta(days=5),
        ))
        await db.commit()
    async with AsyncSessionLocal() as db:
        resp = await client_health_score(
            client_id=str(cenario["cliente"]), current_user=_CurrentUser(cenario["tenant"]), db=db,
        )
    assert resp["componentes"]["engajamento"]["pontos"] == 30
    assert resp["componentes"]["engajamento"]["dias_desde_ultima_interacao"] == 5

    async with AsyncSessionLocal() as db:
        old = (await db.execute(
            ClientInteraction.__table__.select().where(ClientInteraction.client_id == cenario["cliente"])
        )).first()
        await db.execute(
            ClientInteraction.__table__.update()
            .where(ClientInteraction.id == old.id)
            .values(created_at=datetime.now(timezone.utc) - timedelta(days=200))
        )
        await db.commit()
    async with AsyncSessionLocal() as db:
        resp = await client_health_score(
            client_id=str(cenario["cliente"]), current_user=_CurrentUser(cenario["tenant"]), db=db,
        )
    assert resp["componentes"]["engajamento"]["pontos"] == 8


async def test_taxa_de_exito_processual(cenario):
    async with AsyncSessionLocal() as db:
        db.add_all([
            LegalProcess(
                numero_cnj=f"{uuid.uuid4().hex[:7]}-00.2026.0.00.0000", tribunal="TJSP",
                tenant_id=cenario["tenant"], responsavel_id=cenario["adv"], client_id=cenario["cliente"],
                desfecho="EXITO",
            ),
            LegalProcess(
                numero_cnj=f"{uuid.uuid4().hex[:7]}-00.2026.0.00.0000", tribunal="TJSP",
                tenant_id=cenario["tenant"], responsavel_id=cenario["adv"], client_id=cenario["cliente"],
                desfecho="DERROTA",
            ),
            LegalProcess(
                numero_cnj=f"{uuid.uuid4().hex[:7]}-00.2026.0.00.0000", tribunal="TJSP",
                tenant_id=cenario["tenant"], responsavel_id=cenario["adv"], client_id=cenario["cliente"],
                situacao="ATIVO",  # sem desfecho — não deve contar no denominador
            ),
        ])
        await db.commit()
    async with AsyncSessionLocal() as db:
        resp = await client_health_score(
            client_id=str(cenario["cliente"]), current_user=_CurrentUser(cenario["tenant"]), db=db,
        )
    assert resp["componentes"]["processual"]["total_com_desfecho"] == 2
    assert resp["componentes"]["processual"]["taxa_exito"] == 50.0
    assert resp["componentes"]["processual"]["pontos"] == 15


async def test_cliente_de_outro_tenant_nao_encontrado(cenario):
    async with AsyncSessionLocal() as db:
        outro_tenant = Tenant(name="Outro 207.1", slug=f"outro-207-1-{uuid.uuid4().hex[:8]}")
        db.add(outro_tenant)
        await db.commit()
        outro_id = outro_tenant.id
    try:
        from app.core.exceptions import NotFoundError
        async with AsyncSessionLocal() as db:
            with pytest.raises(NotFoundError):
                await client_health_score(
                    client_id=str(cenario["cliente"]), current_user=_CurrentUser(outro_id), db=db,
                )
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(Tenant.__table__.delete().where(Tenant.id == outro_id))
            await db.commit()
