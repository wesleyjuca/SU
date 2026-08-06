"""Fase 130 — petition_agent passa a sinalizar truncamento de LLM e a rodar
verificação automática de citações (antes só existiam como bugs/gaps: stop_reason
descartado, citacao_check.verificar_citacoes() nunca chamada pelo próprio agente)."""
import pytest

from app.agents.brain.context import AgentContext
from app.agents.petition.petition_agent import PetitionAgent


def _ctx():
    return AgentContext(task_type="test", task_input={
        "tipo_peticao": "PETICAO_INICIAL",
        "processo": {"tribunal": "TJCE", "area_direito": "CIVIL"},
    })


@pytest.mark.asyncio
async def test_execute_sinaliza_truncamento(monkeypatch):
    import app.agents.petition.petition_agent as pa_mod

    async def _fake_call_claude(messages, system, max_tokens=8096, temperature=0.3):
        return "Petição gerada, mas cortada no meio...", 100, 200, 0.05

    monkeypatch.setattr(pa_mod, "call_claude", _fake_call_claude)
    pa_mod.last_call_truncated_ctx.set(True)

    async def _fake_verificar_citacoes(texto, tribunal=None):
        return []

    monkeypatch.setattr("app.services.citacao_check.verificar_citacoes", _fake_verificar_citacoes)

    agent = PetitionAgent()
    result = await agent.execute(_ctx())

    assert any("truncado" in w.lower() for w in result.output["warnings"])


@pytest.mark.asyncio
async def test_execute_sem_truncamento_nao_gera_aviso(monkeypatch):
    import app.agents.petition.petition_agent as pa_mod

    async def _fake_call_claude(messages, system, max_tokens=8096, temperature=0.3):
        return "Petição completa.", 100, 200, 0.05

    monkeypatch.setattr(pa_mod, "call_claude", _fake_call_claude)
    pa_mod.last_call_truncated_ctx.set(False)
    monkeypatch.setattr("app.services.citacao_check.verificar_citacoes", lambda *a, **k: _empty())

    agent = PetitionAgent()
    result = await agent.execute(_ctx())

    assert not any("truncado" in w.lower() for w in result.output["warnings"])


async def _empty():
    return []


@pytest.mark.asyncio
async def test_execute_verifica_citacoes_automaticamente(monkeypatch):
    """Antes desta fase, uma citação fabricada mas bem-formatada passava pra
    aprovação sem NENHUMA checagem automática — verificar_citacoes só existia
    como botão manual separado que o revisor podia esquecer de clicar."""
    import app.agents.petition.petition_agent as pa_mod

    async def _fake_call_claude(messages, system, max_tokens=8096, temperature=0.3):
        return "Nos termos da Lei nº 9.999/1999...", 100, 200, 0.05

    monkeypatch.setattr(pa_mod, "call_claude", _fake_call_claude)
    pa_mod.last_call_truncated_ctx.set(False)

    async def _fake_verificar_citacoes(texto, tribunal=None):
        assert tribunal == "TJCE"  # tribunal do processo repassado corretamente
        return [{"referencia": "9999/1999", "tipo": "LEI", "status": "nao_encontrada", "titulo": None}]

    monkeypatch.setattr("app.services.citacao_check.verificar_citacoes", _fake_verificar_citacoes)

    agent = PetitionAgent()
    result = await agent.execute(_ctx())

    assert result.output["citacoes"] == [
        {"referencia": "9999/1999", "tipo": "LEI", "status": "nao_encontrada", "titulo": None}
    ]
    assert any("9999/1999" in w and "nao_encontrada" in w for w in result.output["warnings"])


@pytest.mark.asyncio
async def test_execute_citacao_confirmada_nao_gera_aviso(monkeypatch):
    import app.agents.petition.petition_agent as pa_mod

    async def _fake_call_claude(messages, system, max_tokens=8096, temperature=0.3):
        return "Nos termos da Lei nº 8.078/1990...", 100, 200, 0.05

    monkeypatch.setattr(pa_mod, "call_claude", _fake_call_claude)
    pa_mod.last_call_truncated_ctx.set(False)

    async def _fake_verificar_citacoes(texto, tribunal=None):
        return [{"referencia": "8078/1990", "tipo": "LEI", "status": "confirmada", "titulo": "CDC"}]

    monkeypatch.setattr("app.services.citacao_check.verificar_citacoes", _fake_verificar_citacoes)

    agent = PetitionAgent()
    result = await agent.execute(_ctx())

    assert not any("8078/1990" in w for w in result.output["warnings"])


@pytest.mark.asyncio
async def test_execute_verificar_citacoes_falha_nao_derruba_peticao(monkeypatch):
    """Fail-soft: um erro inesperado na verificação de citação (rede down pros
    2 provedores, bug) nunca deve impedir a petição de chegar à aprovação."""
    import app.agents.petition.petition_agent as pa_mod

    async def _fake_call_claude(messages, system, max_tokens=8096, temperature=0.3):
        return "Petição gerada.", 100, 200, 0.05

    monkeypatch.setattr(pa_mod, "call_claude", _fake_call_claude)
    pa_mod.last_call_truncated_ctx.set(False)

    def _fake_verificar_citacoes(*a, **k):
        raise RuntimeError("erro inesperado")

    monkeypatch.setattr("app.services.citacao_check.verificar_citacoes", _fake_verificar_citacoes)

    agent = PetitionAgent()
    result = await agent.execute(_ctx())

    assert result.status.value == "AWAITING_APPROVAL"
    assert result.output["citacoes"] == []


# ─── Fase 140.1.1 — mensagens de erro diagnosticáveis (não engolidas) ──────

@pytest.mark.asyncio
async def test_execute_falha_na_chamada_claude_propaga_com_prefixo(monkeypatch):
    """A chamada Claude não tinha try/except próprio — o erro cru do SDK
    chegava em AgentRun.error_message sem dizer ONDE falhou. Agora vira
    RuntimeError com prefixo diagnosticável, ainda propagado (BaseAgent.run()
    continua decidindo o status final — não vira fail-soft silencioso)."""
    import app.agents.petition.petition_agent as pa_mod

    async def _fake_call_claude_falha(messages, system, max_tokens=8096, temperature=0.3):
        raise RuntimeError("rate limit exceeded")

    monkeypatch.setattr(pa_mod, "call_claude", _fake_call_claude_falha)

    agent = PetitionAgent()
    with pytest.raises(RuntimeError) as exc_info:
        await agent.execute(_ctx())

    assert "Falha ao gerar petição via IA" in str(exc_info.value)
    assert "rate limit exceeded" in str(exc_info.value)


@pytest.mark.asyncio
async def test_execute_via_run_falha_na_ia_vira_agentrun_failed_diagnosticavel():
    """Ponta a ponta via BaseAgent.run() (o wrapper real usado em produção):
    confirma que o erro prefixado chega inteiro em AgentResult.error, não é
    engolido nem truncado pelo loop de retry."""
    import app.agents.petition.petition_agent as pa_mod

    class _FailingAgent(PetitionAgent):
        max_retries = 0

    async def _fake_call_claude_falha(messages, system, max_tokens=8096, temperature=0.3):
        raise ConnectionError("timeout ao chamar Anthropic")

    orig = pa_mod.call_claude
    pa_mod.call_claude = _fake_call_claude_falha
    try:
        agent = _FailingAgent()
        result = await agent.run(_ctx())
    finally:
        pa_mod.call_claude = orig

    assert result.status.value == "FAILED"
    assert "Falha ao gerar petição via IA" in result.error
    assert "timeout ao chamar Anthropic" in result.error


@pytest.mark.asyncio
async def test_execute_falha_ao_salvar_documento_propaga_com_prefixo(monkeypatch):
    """DB save (_salvar_documento) não tinha try/except próprio — agora
    propaga com prefixo dizendo que a falha foi ao SALVAR, não ao GERAR
    (mensagens diferentes ajudam a distinguir as duas causas mais prováveis
    de uma execução FAILED de petition_agent)."""
    import app.agents.petition.petition_agent as pa_mod

    async def _fake_call_claude(messages, system, max_tokens=8096, temperature=0.3):
        return "Petição gerada.", 100, 200, 0.05

    monkeypatch.setattr(pa_mod, "call_claude", _fake_call_claude)
    pa_mod.last_call_truncated_ctx.set(False)

    async def _fake_verificar_citacoes(texto, tribunal=None):
        return []

    monkeypatch.setattr("app.services.citacao_check.verificar_citacoes", _fake_verificar_citacoes)

    class _FakeDBQuebrado:
        def add(self, obj):
            pass

        async def flush(self):
            raise RuntimeError("violação de FK: process_id não existe")

    agent = PetitionAgent(db=_FakeDBQuebrado())
    with pytest.raises(RuntimeError) as exc_info:
        await agent.execute(_ctx())

    assert "Falha ao salvar petição no banco" in str(exc_info.value)
    assert "violação de FK" in str(exc_info.value)
