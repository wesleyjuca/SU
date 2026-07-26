"""Fase 111 — as 4 etapas do review_agent (formal/consistência/risco/estilo)
rodam concorrentemente (asyncio.gather), não mais em sequência. Confirma
concorrência real (não só que os 4 resultados aparecem) e que o resultado
final (score/bloqueadores/etapas) fica idêntico ao comportamento anterior."""
import asyncio
import time

import pytest

import app.agents.review.review_agent as review_agent_mod
from app.agents.review.review_agent import ReviewAgent
from app.agents.base.result import AgentStatus
from app.agents.brain.context import AgentContext


@pytest.mark.asyncio
async def test_etapas_rodam_concorrentemente(monkeypatch):
    ordem_inicio = []
    ordem_fim = []

    async def fake_call_claude(messages, system, max_tokens=2000, temperature=0.1):
        prompt = messages[0]["content"]
        nome = "formal" if "FORMAL" in prompt else "consistencia" if "CONSISTÊNCIA" in prompt \
            else "risco" if "RISCO" in prompt else "estilo"
        ordem_inicio.append((nome, time.monotonic()))
        await asyncio.sleep(0.05)  # simula latência de rede/LLM
        ordem_fim.append((nome, time.monotonic()))
        return '{"issues": [], "aprovado": true, "nivel_risco": "BAIXO", "nota_redacao": 8}', 10, 20, 0.01

    monkeypatch.setattr(review_agent_mod, "call_claude", fake_call_claude)

    agent = ReviewAgent()
    ctx = AgentContext(task_type="review_document", task_input={
        "conteudo": "Excelentíssimo Senhor Doutor Juiz...",
        "tipo_documento": "PETICAO",
    })

    inicio = time.monotonic()
    res = await agent.execute(ctx)
    duracao = time.monotonic() - inicio

    # Concorrente: dura ~0.05s (a mais lenta), não ~0.20s (soma de 4x0.05s).
    assert duracao < 0.15, f"esperava rodar em paralelo, mas levou {duracao:.3f}s"
    assert len(ordem_inicio) == 4
    # Todas as 4 começaram antes de qualquer uma terminar — prova de concorrência real.
    primeiro_fim = min(t for _, t in ordem_fim)
    assert all(t <= primeiro_fim for _, t in ordem_inicio)
    assert res.status == AgentStatus.SUCCESS


@pytest.mark.asyncio
async def test_resultado_final_identico_ao_comportamento_sequencial(monkeypatch):
    """Mesmo com respostas diferentes por etapa, score/bloqueadores/etapas
    devem refletir corretamente cada uma (nada se perde ao rodar em paralelo)."""
    respostas = {
        "FORMAL": '{"issues": [{"descricao": "x", "gravidade": "MEDIA"}], "aprovado": true}',
        "CONSISTÊNCIA": '{"issues": [{"descricao": "[NÃO VERIFICADO] citação", "gravidade": "ALTA"}], "aprovado": false}',
        "RISCO": '{"nivel_risco": "ALTO", "riscos": ["r1"], "teses_alternativas": []}',
        "ESTILO": '{"issues": [], "nota_redacao": 6}',
    }

    async def fake_call_claude(messages, system, max_tokens=2000, temperature=0.1):
        prompt = messages[0]["content"]
        for chave, resp in respostas.items():
            if chave in prompt:
                return resp, 10, 20, 0.01
        raise AssertionError(f"prompt inesperado: {prompt[:50]}")

    monkeypatch.setattr(review_agent_mod, "call_claude", fake_call_claude)

    agent = ReviewAgent()
    ctx = AgentContext(task_type="review_document", task_input={
        "conteudo": "documento de teste",
        "tipo_documento": "PETICAO",
    })
    res = await agent.execute(ctx)

    assert res.output["etapas"]["consistencia"]["issues"][0]["gravidade"] == "ALTA"
    assert len(res.output["bloqueadores"]) == 1
    assert res.output["etapas"]["risco"]["nivel_risco"] == "ALTO"
    assert res.output["etapas"]["estilo"]["nota_redacao"] == 6
    # score: 100 - 30(NAO VERIFICADO) - 15(ALTO) - round((10-6)*1.5)=6 - 5(1 issue formal) = 44
    assert res.output["score"] == 44
