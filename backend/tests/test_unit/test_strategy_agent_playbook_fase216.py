"""Fase 216 — playbooks de agentes por área injetados no prompt do
strategy_agent: nova seção "ORIENTAÇÃO INTERNA DO ESCRITÓRIO PARA ESTA
ÁREA", ao lado do histórico de êxito (Fase 208.1) já existente. Confirma
que o playbook aparece quando configurado, que a ausência não quebra o
agente (fallback), e que os dois blocos (208.1 + 216) coexistem no mesmo
prompt sem um clobar o outro."""
import uuid

import pytest

from app.agents.base.result import AgentStatus
from app.agents.brain.context import AgentContext
from app.agents.strategy.strategy_agent import StrategyAgent
from app.db.base import AsyncSessionLocal
from app.models.agent_playbook import AgentAreaPlaybook
from app.models.process import LegalProcess
from app.models.tenant import Tenant

pytestmark = pytest.mark.anyio


@pytest.fixture
async def tenant_com_playbook():
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant 216", slug=f"teste-216-agent-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        db.add(AgentAreaPlaybook(
            tenant_id=tenant.id, area_direito="Civil",
            texto="Sempre checar prescrição antes de propor a tese principal.",
        ))
        db.add(LegalProcess(
            numero_cnj=f"{uuid.uuid4().hex[:7]}-00.2026.0.00.0000", tribunal="TJSP",
            tenant_id=tenant.id, area_direito="Civil", desfecho="EXITO",
        ))
        await db.commit()
        tid = tenant.id
    yield tid
    async with AsyncSessionLocal() as db:
        await db.execute(AgentAreaPlaybook.__table__.delete().where(AgentAreaPlaybook.tenant_id == tid))
        await db.execute(LegalProcess.__table__.delete().where(LegalProcess.tenant_id == tid))
        await db.execute(Tenant.__table__.delete().where(Tenant.id == tid))
        await db.commit()


async def test_prompt_inclui_playbook_quando_configurado(tenant_com_playbook, monkeypatch):
    prompts_capturados = []

    async def fake_call_claude(messages, system, max_tokens=4000, temperature=0.4):
        prompts_capturados.append(messages[0]["content"])
        return "análise gerada", 100, 200, 0.02

    import app.agents.strategy.strategy_agent as mod
    monkeypatch.setattr(mod, "call_claude", fake_call_claude)

    async with AsyncSessionLocal() as db:
        agent = StrategyAgent(db=db)
        ctx = AgentContext(
            task_type="strategy", tenant_id=tenant_com_playbook,
            task_input={"fatos": "fatos do caso", "area_direito": "Civil",
                        "tipo_acao": "Indenizatória", "objetivo": "reparação"},
        )
        result = await agent.execute(ctx)

    assert result.status == AgentStatus.SUCCESS
    assert result.output["playbook_aplicado"] is True
    assert "ORIENTAÇÃO INTERNA DO ESCRITÓRIO PARA ESTA ÁREA" in prompts_capturados[0]
    assert "Sempre checar prescrição antes de propor a tese principal." in prompts_capturados[0]
    # regressão: o bloco de histórico de êxito (208.1) continua presente,
    # o playbook não substitui/clobera a seção já existente.
    assert "HISTÓRICO DE ÊXITO DO ESCRITÓRIO NESTA ÁREA" in prompts_capturados[0]


async def test_sem_playbook_nao_quebra_e_usa_fallback(monkeypatch):
    async def fake_call_claude(messages, system, max_tokens=4000, temperature=0.4):
        return "análise", 10, 10, 0.001

    import app.agents.strategy.strategy_agent as mod
    monkeypatch.setattr(mod, "call_claude", fake_call_claude)

    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant 216b", slug=f"teste-216-agent-b-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
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
                                task_input={"fatos": "fatos", "area_direito": "Trabalhista"})
            result = await agent.execute(ctx)
        assert result.status == AgentStatus.SUCCESS
        assert result.output["playbook_aplicado"] is False
        assert "Nenhuma orientação específica cadastrada" in prompts_capturados[0]
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(Tenant.__table__.delete().where(Tenant.id == tid))
            await db.commit()
