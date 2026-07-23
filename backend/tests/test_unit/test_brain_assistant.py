"""Bloco F / F5 — testes do assistente do Cérebro (mocks; sem rede)."""
import pytest

from app.services import brain_assistant as ba


@pytest.mark.asyncio
async def test_montar_system_prompt_inclui_fatos(monkeypatch):
    # Sem Qdrant/infra reais → RAG e infra retornam "" graciosamente
    async def _sem_rag(pergunta):
        return ""
    async def _sem_infra(db):
        return ""
    monkeypatch.setattr(ba, "_rag_docs", _sem_rag)
    monkeypatch.setattr(ba, "_infra_resumo", _sem_infra)

    prompt = await ba.montar_system_prompt(db=None, pergunta="como funciona a captura?")
    assert "ASSISTENTE ADMINISTRATIVO DO SISTEMA AFJ CORE" in prompt
    assert "Captura de processos" in prompt


@pytest.mark.asyncio
async def test_montar_system_prompt_agrega_infra_e_rag(monkeypatch):
    async def _rag(pergunta):
        return "TRECHOS DE DOCUMENTAÇÃO (RAG):\n- exemplo"
    async def _infra(db):
        return "SNAPSHOT DE INFRA (tempo real):\n{\"celery\": {\"ok\": true}}"
    monkeypatch.setattr(ba, "_rag_docs", _rag)
    monkeypatch.setattr(ba, "_infra_resumo", _infra)

    prompt = await ba.montar_system_prompt(db=None, pergunta="status?")
    assert "SNAPSHOT DE INFRA" in prompt and "TRECHOS DE DOCUMENTAÇÃO" in prompt


@pytest.mark.asyncio
async def test_responder_stream_repassa_eventos(monkeypatch):
    # Mocka call_llm_stream para não tocar provedor
    async def fake_stream(mensagens, system="", max_tokens=2048, temperature=0.2):
        assert "ASSISTENTE" in system   # system prompt montado foi passado
        yield ("delta", "Olá")
        yield ("delta", " mundo")
        yield ("done", {"cost_usd": 0.002})

    import app.integrations.llm_client as llm
    monkeypatch.setattr(llm, "call_llm_stream", fake_stream)

    async def _sem(_x=None):
        return ""
    monkeypatch.setattr(ba, "_rag_docs", _sem)
    async def _seminfra(db):
        return ""
    monkeypatch.setattr(ba, "_infra_resumo", _seminfra)

    eventos = []
    async for ev in ba.responder_stream(db=None, historico=[{"role": "user", "content": "oi"}], pergunta="oi"):
        eventos.append(ev)
    tipos = [t for t, _ in eventos]
    assert tipos == ["delta", "delta", "done"]
    assert "".join(d for t, d in eventos if t == "delta") == "Olá mundo"


@pytest.mark.asyncio
async def test_reindex_sem_openai_key(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    r = await ba.reindexar_documentacao()
    assert r["ok"] is False and "OPENAI_API_KEY" in r["motivo"]
