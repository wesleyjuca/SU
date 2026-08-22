"""Fase 208.1 — win-rate histórico no strategy_agent: nova seção do prompt e
campos taxa_exito_area/total_processos_area no retorno, calculados a partir
de LegalProcess.desfecho do próprio tenant (não jurisprudência externa)."""
import uuid

import pytest

from app.agents.base.result import AgentStatus
from app.agents.brain.context import AgentContext
from app.agents.strategy.strategy_agent import StrategyAgent
from app.db.base import AsyncSessionLocal
from app.models.process import LegalProcess
from app.models.tenant import Tenant

pytestmark = pytest.mark.anyio


@pytest.fixture
async def tenant_com_processos():
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant 208.1", slug=f"teste-208-1-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        db.add_all([
            LegalProcess(numero_cnj=f"{uuid.uuid4().hex[:7]}-00.2026.0.00.0000", tribunal="TJSP",
                         tenant_id=tenant.id, area_direito="Trabalhista", desfecho="EXITO"),
            LegalProcess(numero_cnj=f"{uuid.uuid4().hex[:7]}-00.2026.0.00.0000", tribunal="TJSP",
                         tenant_id=tenant.id, area_direito="Trabalhista", desfecho="DERROTA"),
            LegalProcess(numero_cnj=f"{uuid.uuid4().hex[:7]}-00.2026.0.00.0000", tribunal="TJSP",
                         tenant_id=tenant.id, area_direito="Trabalhista", desfecho="ACORDO"),
            LegalProcess(numero_cnj=f"{uuid.uuid4().hex[:7]}-00.2026.0.00.0000", tribunal="TJSP",
                         tenant_id=tenant.id, area_direito="Cível", situacao="ATIVO"),  # sem desfecho
        ])
        await db.commit()
        tid = tenant.id
    yield tid
    async with AsyncSessionLocal() as db:
        await db.execute(LegalProcess.__table__.delete().where(LegalProcess.tenant_id == tid))
        await db.execute(Tenant.__table__.delete().where(Tenant.id == tid))
        await db.commit()


async def test_prompt_inclui_e_retorno_expoe_taxa_exito_area(tenant_com_processos, monkeypatch):
    prompts_capturados = []

    async def fake_call_claude(messages, system, max_tokens=4000, temperature=0.4):
        prompts_capturados.append(messages[0]["content"])
        return "análise gerada", 100, 200, 0.02

    import app.agents.strategy.strategy_agent as mod
    monkeypatch.setattr(mod, "call_claude", fake_call_claude)

    async with AsyncSessionLocal() as db:
        agent = StrategyAgent(db=db)
        ctx = AgentContext(
            task_type="strategy", tenant_id=tenant_com_processos,
            task_input={"fatos": "fatos do caso", "area_direito": "Trabalhista",
                        "tipo_acao": "Reclamação", "objetivo": "indenização"},
        )
        result = await agent.execute(ctx)

    assert result.status == AgentStatus.SUCCESS
    assert result.output["taxa_exito_area"] == pytest.approx(66.7, abs=0.1)  # 2 de 3 (EXITO+ACORDO)
    assert result.output["total_processos_area"] == 3
    assert "HISTÓRICO DE ÊXITO DO ESCRITÓRIO NESTA ÁREA" in prompts_capturados[0]
    assert "66.7%" in prompts_capturados[0]


async def test_sem_processos_com_desfecho_na_area_sinaliza_ausencia(tenant_com_processos, monkeypatch):
    async def fake_call_claude(messages, system, max_tokens=4000, temperature=0.4):
        return "análise", 10, 10, 0.001

    import app.agents.strategy.strategy_agent as mod
    monkeypatch.setattr(mod, "call_claude", fake_call_claude)

    async with AsyncSessionLocal() as db:
        agent = StrategyAgent(db=db)
        ctx = AgentContext(
            task_type="strategy", tenant_id=tenant_com_processos,
            task_input={"fatos": "fatos", "area_direito": "Tributário"},
        )
        result = await agent.execute(ctx)

    assert result.output["taxa_exito_area"] is None
    assert result.output["total_processos_area"] == 0


async def test_amostra_pequena_sinaliza_cautela_no_prompt(monkeypatch):
    async def fake_call_claude(messages, system, max_tokens=4000, temperature=0.4):
        return "análise", 10, 10, 0.001

    import app.agents.strategy.strategy_agent as mod
    monkeypatch.setattr(mod, "call_claude", fake_call_claude)

    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant 208.1b", slug=f"teste-208-1b-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        db.add(LegalProcess(numero_cnj=f"{uuid.uuid4().hex[:7]}-00.2026.0.00.0000", tribunal="TJSP",
                             tenant_id=tenant.id, area_direito="Penal", desfecho="EXITO"))
        await db.commit()
        tid = tenant.id

    prompts_capturados = []

    async def fake_call_claude_2(messages, system, max_tokens=4000, temperature=0.4):
        prompts_capturados.append(messages[0]["content"])
        return "análise", 10, 10, 0.001
    monkeypatch.setattr(mod, "call_claude", fake_call_claude_2)

    try:
        async with AsyncSessionLocal() as db:
            agent = StrategyAgent(db=db)
            ctx = AgentContext(task_type="strategy", tenant_id=tid,
                                task_input={"fatos": "fatos", "area_direito": "Penal"})
            result = await agent.execute(ctx)
        assert result.output["total_processos_area"] == 1
        assert "amostra pequena" in prompts_capturados[0]
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(LegalProcess.__table__.delete().where(LegalProcess.tenant_id == tid))
            await db.execute(Tenant.__table__.delete().where(Tenant.id == tid))
            await db.commit()
