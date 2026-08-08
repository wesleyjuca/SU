"""Fase 71 — testes da fundação dos agentes (BaseAgent) com mocks.

Sem DB, sem Qdrant, sem provedor de IA: call_claude é mockado via
monkeypatch no módulo anthropic_client.
"""
import pytest

from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext


class EchoAgent(BaseAgent):
    name = "echo_agent"
    description = "agente de teste"

    async def execute(self, ctx):
        return AgentResult(status=AgentStatus.SUCCESS, agent_name=self.name, output={"eco": ctx.task_input})


class EmptyAgent(BaseAgent):
    name = "empty_agent"
    description = "sucesso sem output"

    async def execute(self, ctx):
        return AgentResult(status=AgentStatus.SUCCESS, agent_name=self.name)


class StrictEmptyAgent(EmptyAgent):
    name = "strict_empty_agent"
    strict_validation = True


class CriticalAgent(EchoAgent):
    name = "critical_agent"
    criticality = "HIGH"


class FlakyAgent(BaseAgent):
    name = "flaky_agent"
    description = "falha uma vez, depois funciona"
    calls = 0

    async def execute(self, ctx):
        type(self).calls += 1
        if type(self).calls == 1:
            raise RuntimeError("falha transitória")
        return AgentResult(status=AgentStatus.SUCCESS, agent_name=self.name, output={"ok": True})


class LLMAgent(BaseAgent):
    name = "llm_agent"
    description = "usa ask_llm"
    max_cost_usd_per_run = 0.50

    async def execute(self, ctx):
        texto = await self.ask_llm(ctx, "Resuma o processo.")
        return AgentResult(status=AgentStatus.SUCCESS, agent_name=self.name, output={"texto": texto})


@pytest.mark.asyncio
async def test_run_success_e_auditoria():
    ctx = AgentContext(task_type="echo", task_input={"a": 1})
    result = await EchoAgent().run(ctx)
    assert result.status == AgentStatus.SUCCESS
    assert result.output == {"eco": {"a": 1}}
    assert "echo_agent" in ctx.agents_invoked
    acoes = [e["action"] for e in ctx.audit_events]
    assert "AGENT_START" in acoes and "AGENT_COMPLETE" in acoes


@pytest.mark.asyncio
async def test_validate_registra_problema_sem_derrubar():
    result = await EmptyAgent().run(AgentContext(task_type="t"))
    assert result.status == AgentStatus.SUCCESS  # não-estrito: só registra
    assert result.metadata.get("validation_issues")


@pytest.mark.asyncio
async def test_strict_validation_vira_partial():
    result = await StrictEmptyAgent().run(AgentContext(task_type="t"))
    assert result.status == AgentStatus.PARTIAL
    assert result.metadata.get("validation_issues")


@pytest.mark.asyncio
async def test_criticality_high_exige_aprovacao():
    result = await CriticalAgent().run(AgentContext(task_type="t", task_input={}))
    assert result.status == AgentStatus.AWAITING_APPROVAL
    # Depois de aprovado, executa normalmente
    ctx_aprovado = AgentContext(task_type="t", task_input={})
    ctx_aprovado.approved = True
    result2 = await CriticalAgent().run(ctx_aprovado)
    assert result2.status == AgentStatus.SUCCESS


@pytest.mark.asyncio
async def test_retry_recupera_falha_transitoria():
    FlakyAgent.calls = 0
    result = await FlakyAgent().run(AgentContext(task_type="t"))
    assert result.status == AgentStatus.SUCCESS
    assert FlakyAgent.calls == 2


@pytest.mark.asyncio
async def test_ask_llm_contabiliza_tokens_e_custo(monkeypatch):
    async def fake_call_claude(messages, system="", model=None, max_tokens=8096, temperature=0.3):
        assert "assistente jurídico" in system  # AFJ_LEGAL_SYSTEM_PROMPT herdado
        return "resumo ok", 100, 50, 0.01

    import app.integrations.anthropic_client as ac
    monkeypatch.setattr(ac, "call_claude", fake_call_claude)

    ctx = AgentContext(task_type="t")
    result = await LLMAgent().run(ctx)
    assert result.status == AgentStatus.SUCCESS
    assert result.output["texto"] == "resumo ok"
    assert ctx.total_tokens == 150
    assert ctx.total_cost_usd == pytest.approx(0.01)


@pytest.mark.asyncio
async def test_ask_llm_cap_por_run_bloqueia_sem_retry(monkeypatch):
    chamadas = {"n": 0}

    async def fake_call_claude(**kwargs):
        chamadas["n"] += 1
        return "x", 1, 1, 0.0

    import app.integrations.anthropic_client as ac
    monkeypatch.setattr(ac, "call_claude", fake_call_claude)

    ctx = AgentContext(task_type="t")
    ctx.total_cost_usd = 0.60  # acima do cap de 0.50 do LLMAgent
    result = await LLMAgent().run(ctx)
    assert result.status == AgentStatus.FAILED
    assert "Cap de custo" in (result.error or "")
    assert chamadas["n"] == 0  # o provedor NUNCA foi chamado (nem em retry)


@pytest.mark.asyncio
async def test_build_messages_few_shot():
    msgs = BaseAgent.build_messages("entrada real", few_shot=[("ex-in", "ex-out")])
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[-1]["content"] == "entrada real"


@pytest.mark.asyncio
async def test_recall_sem_qdrant_retorna_vazio():
    ctx = AgentContext(task_type="t")
    assert await EchoAgent(qdrant=None).recall(ctx, "consulta") == []


@pytest.mark.asyncio
async def test_recall_encaminha_tenant_id_pro_retrieve(monkeypatch):
    """Fase 144 — regressão do vazamento cross-tenant: recall() precisa
    repassar ctx.tenant_id pro retrieve(), senão o filtro de coleção
    privada (peticoes_afj/memorias_afj/documentos_clientes/doutrina_privada)
    nunca é aplicado (retrieval.py só filtra `if tenant_id`)."""
    chamadas = {}

    async def fake_retrieve(qdrant_client, query, collections=None, k=5, tenant_id=None):
        chamadas["tenant_id"] = tenant_id
        return []

    import app.rag.retrieval as retrieval_module
    monkeypatch.setattr(retrieval_module, "retrieve", fake_retrieve)

    tenant_id = "11111111-1111-1111-1111-111111111111"
    ctx = AgentContext(task_type="t", tenant_id=tenant_id)
    await EchoAgent(qdrant=object()).recall(ctx, "consulta", collections=["peticoes_afj"])

    assert chamadas["tenant_id"] == tenant_id
