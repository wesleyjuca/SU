"""Fase 196/198.B — resposta de IA em streaming nos agentes (débito técnico G).

Achado da Fase 197 (teste geral): a Fase 196 original implementou
streaming dentro de `BaseAgent.ask_llm()`, mas NENHUM dos 19 agentes reais
chama esse método — todos chamam `call_claude`/`call_llm` direto e
replicam o bookkeeping manualmente (padrão da Fase 125). Streaming nunca
ativava de verdade, confirmado ao vivo (disparo HTTP real contra Celery
real — zero eventos AGENT_RUN_DELTA publicados).

Fix (Fase 198.B): streaming se move pra dentro de `call_llm()`
(llm_client.py) — o único ponto que TODO agente já passa por baixo,
direto ou via `ask_llm()`. Gate via contextvar `agent_stream_ctx`, setado
por `execute_chain_step()` (orchestrator.py) só pra disparo direto (chain
de 1 passo) com `triggered_by` conhecido — nenhum agente individual
precisa saber disso."""
import uuid
from typing import ClassVar

import pytest

from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext
from app.integrations.anthropic_client import call_claude
import app.integrations.llm_client as llm_client_mod


class _StubAgent(BaseAgent):
    """Só chama `ask_llm()` — cobre o caminho que já existia."""
    name: ClassVar[str] = "stub_agent"
    description: ClassVar[str] = "Agente de teste"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        content = await self.ask_llm(ctx, prompt="oi")
        return AgentResult(status=AgentStatus.SUCCESS, agent_name=self.name, output={"content": content})

    async def _register_tools(self):
        return []


class _DirectCallAgent(BaseAgent):
    """Mimetiza o padrão REAL dos 19 agentes de produção (Fase 125): chama
    `call_claude` direto, nunca `self.ask_llm()`. É exatamente o caminho
    que o achado da Fase 197 mostrou que nunca streamava antes do fix."""
    name: ClassVar[str] = "direct_call_agent"
    description: ClassVar[str] = "Agente de teste — padrão real (call_claude direto)"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        content, tokens_in, tokens_out, cost = await call_claude(
            messages=[{"role": "user", "content": "oi"}], system="",
        )
        ctx.add_tokens(tokens_in + tokens_out, cost)
        return AgentResult(status=AgentStatus.SUCCESS, agent_name=self.name, output={"content": content})

    async def _register_tools(self):
        return []


async def _fake_call_llm_stream(messages, system, model=None, max_tokens=8096, temperature=0.3, provider=None):
    yield ("delta", "Olá, ")
    yield ("delta", "tudo bem?")
    yield ("done", {"input_tokens": 12, "output_tokens": 7, "cost_usd": 0.002})


def _capture_publish(monkeypatch):
    publicados = []

    async def fake_publish_event(user_id, event_type, data):
        publicados.append((user_id, event_type, data))

    import app.api.v1.ws as ws_mod
    monkeypatch.setattr(ws_mod, "publish_event", fake_publish_event)
    return publicados


@pytest.mark.asyncio
async def test_call_llm_com_agent_stream_ctx_publica_deltas_e_acumula_conteudo(monkeypatch):
    monkeypatch.setattr(llm_client_mod, "call_llm_stream", _fake_call_llm_stream)
    publicados = _capture_publish(monkeypatch)

    token = llm_client_mod.agent_stream_ctx.set({
        "user_id": "user-1", "run_id": "run-1", "agent_name": "algum_agente",
    })
    try:
        content, in_t, out_t, cost = await llm_client_mod.call_llm([{"role": "user", "content": "oi"}])
    finally:
        llm_client_mod.agent_stream_ctx.reset(token)

    assert content == "Olá, tudo bem?"
    assert (in_t, out_t) == (12, 7)
    assert cost == pytest.approx(0.002)

    deltas = [d for (_, tipo, d) in publicados if tipo == "AGENT_RUN_DELTA"]
    assert len(deltas) == 2
    assert deltas[0]["delta"] == "Olá, "
    assert deltas[1]["delta"] == "tudo bem?"
    assert all(d["run_id"] == "run-1" and d["agent_name"] == "algum_agente" for d in deltas)
    assert all(uid == "user-1" for (uid, _, _) in publicados)


@pytest.mark.asyncio
async def test_call_llm_sem_agent_stream_ctx_nunca_streama(monkeypatch):
    """Sem o contextvar setado (fluxo normal — chain multi-passo, ou
    qualquer chamada fora de um agente), call_llm nunca toca call_llm_stream."""
    async def _explode(*a, **k):
        raise AssertionError("call_llm_stream não deveria ser chamado sem agent_stream_ctx")
    monkeypatch.setattr(llm_client_mod, "call_llm_stream", _explode)

    async def fake_anthropic(api_key, messages, system, model, max_tokens, temperature):
        return "resposta normal", 3, 4, "stop"
    monkeypatch.setattr(llm_client_mod, "_call_anthropic", fake_anthropic)

    assert llm_client_mod.agent_stream_ctx.get() is None
    content, in_t, out_t, cost = await llm_client_mod.call_llm([{"role": "user", "content": "oi"}])
    assert content == "resposta normal"


@pytest.mark.asyncio
async def test_agente_com_call_claude_direto_streama_transparente(monkeypatch):
    """O teste que prova o achado da Fase 197 fechado: um agente no padrão
    REAL de produção (call_claude direto, nunca ask_llm) agora streama sem
    nenhuma mudança nele — só porque `agent_stream_ctx` está setado."""
    monkeypatch.setattr(llm_client_mod, "call_llm_stream", _fake_call_llm_stream)
    publicados = _capture_publish(monkeypatch)

    ctx = AgentContext(task_type="test", triggered_by=uuid.uuid4(), run_id=uuid.uuid4())
    token = llm_client_mod.agent_stream_ctx.set({
        "user_id": str(ctx.triggered_by), "run_id": str(ctx.run_id), "agent_name": "direct_call_agent",
    })
    try:
        agent = _DirectCallAgent()
        result = await agent.run(ctx)
    finally:
        llm_client_mod.agent_stream_ctx.reset(token)

    assert result.status == AgentStatus.SUCCESS
    assert result.output["content"] == "Olá, tudo bem?"
    deltas = [d for (_, tipo, d) in publicados if tipo == "AGENT_RUN_DELTA"]
    assert len(deltas) == 2
    assert all(d["agent_name"] == "direct_call_agent" for d in deltas)


@pytest.mark.asyncio
async def test_ask_llm_tambem_streama_transparente_via_call_claude(monkeypatch):
    """ask_llm() não tem mais lógica de streaming própria — herda o
    comportamento de call_claude -> call_llm como qualquer outro chamador."""
    monkeypatch.setattr(llm_client_mod, "call_llm_stream", _fake_call_llm_stream)
    publicados = _capture_publish(monkeypatch)

    ctx = AgentContext(task_type="test", triggered_by=uuid.uuid4(), run_id=uuid.uuid4())
    token = llm_client_mod.agent_stream_ctx.set({
        "user_id": str(ctx.triggered_by), "run_id": str(ctx.run_id), "agent_name": "stub_agent",
    })
    try:
        agent = _StubAgent()
        content = await agent.ask_llm(ctx, prompt="oi")
    finally:
        llm_client_mod.agent_stream_ctx.reset(token)

    assert content == "Olá, tudo bem?"
    assert ctx.total_tokens == 19
    deltas = [d for (_, tipo, d) in publicados if tipo == "AGENT_RUN_DELTA"]
    assert len(deltas) == 2


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def add(self, obj):
        pass

    async def commit(self):
        pass

    async def rollback(self):
        pass


@pytest.mark.asyncio
async def test_execute_chain_step_seta_agent_stream_ctx_so_pra_chain_de_1_passo(monkeypatch):
    """Roda o loop real do orquestrador (mesmo harness da Fase 169.1,
    test_agent_chaining.py) pra confirmar que `agent_stream_ctx` só fica
    setado DURANTE o run de um disparo direto (1 passo), e nunca pra
    chain multi-passo — e que é resetado logo depois (não vaza pro
    próximo passo/chamada)."""
    import app.agents.brain.orchestrator as orch
    import app.db.base as dbbase
    import app.db.redis as dbredis

    monkeypatch.setattr(dbbase, "AsyncSessionLocal", lambda: _FakeSession())

    async def _fake_redis():
        return None
    monkeypatch.setattr(dbredis, "get_redis", _fake_redis)

    stream_ctx_observado = []

    def _fake_resolve(route):
        class FakeAgent:
            name = route

            def __init__(self, db=None, redis=None, qdrant=None):
                pass

            async def run(self, ctx):
                stream_ctx_observado.append(llm_client_mod.agent_stream_ctx.get())
                return AgentResult(status=AgentStatus.SUCCESS, agent_name=route, output={})
        return FakeAgent
    monkeypatch.setattr(orch, "resolve_agent_class", _fake_resolve)

    # Disparo direto (get_chain("generate_petition") == ["petition_agent"]).
    ctx_direto = AgentContext(task_type="generate_petition", triggered_by=uuid.uuid4())
    await orch.execute_chain_step(ctx_direto, ["petition_agent"], 0)
    assert stream_ctx_observado[0] is not None
    assert stream_ctx_observado[0]["agent_name"] == "petition_agent"
    assert llm_client_mod.agent_stream_ctx.get() is None  # resetado após o run

    # Chain multi-passo (get_chain("new_process_intake") tem 4 passos).
    chain = ["process_agent", "jurisprudence_agent", "strategy_agent", "crm_agent"]
    ctx_chain = AgentContext(task_type="new_process_intake", triggered_by=uuid.uuid4())
    await orch.execute_chain_step(ctx_chain, chain, 0)
    assert stream_ctx_observado[1] is None
