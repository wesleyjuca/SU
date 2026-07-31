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
