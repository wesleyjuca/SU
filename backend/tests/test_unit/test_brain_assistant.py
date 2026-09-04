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
    """Fase pós-260.3 — mensagem atualizada: sem chave central NEM BYOK
    (user_id=None aqui não resolve nenhuma), ainda falha honesto."""
    from app.config import settings
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    r = await ba.reindexar_documentacao()
    assert r["ok"] is False and "chave OpenAI" in r["motivo"]


@pytest.mark.asyncio
async def test_reindex_usa_byok_quando_sem_chave_central(monkeypatch):
    """Fase pós-260.3 — achado real: `reindexar_documentacao()` só olhava
    `settings.OPENAI_API_KEY` (central), ignorando BYOK do usuário que
    disparou a reindexação — mesma classe de bug já corrigida em
    `rag/embeddings.py` (Fase pós-259), nunca aplicada aqui. Confirma que,
    com uma credencial BYOK openai resolvível (simulada aqui via
    monkeypatch de `_resolve_byok_openai_key`, sem precisar de Postgres
    real pra este teste unitário — cobertura HTTP/Postgres real completa
    já feita via script standalone), a reindexação prossegue em vez de
    recusar de saída."""
    from app.config import settings
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")

    import app.rag.embeddings as embeddings_mod
    monkeypatch.setattr(embeddings_mod, "_resolve_byok_openai_key", lambda: ("sk-byok-fake", None))

    chamados = []

    async def _fake_ingest_document(**kwargs):
        chamados.append(kwargs.get("metadata", {}).get("fonte"))

    import app.rag.ingestion as ingestion_mod
    monkeypatch.setattr(ingestion_mod, "ingest_document", _fake_ingest_document)

    r = await ba.reindexar_documentacao()
    assert r["ok"] is True
    assert r["arquivos_indexados"] == len(chamados) > 0


@pytest.mark.asyncio
async def test_rag_docs_nao_bloqueia_mais_por_falta_de_chave_central(monkeypatch):
    """Fase pós-260.3 — antes, `_rag_docs()` retornava "" direto se
    `OPENAI_API_KEY` central estivesse vazia, mesmo com BYOK disponível
    (o contextvar nunca chegava a ser consultado). Agora o guard só olha
    se o Qdrant está configurado — a resolução de chave (central ou BYOK)
    fica inteiramente a cargo de `retrieve()`/`embed_text()`, que já
    fazem essa checagem sozinhos."""
    from app.config import settings
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "QDRANT_URL", "http://qdrant-real-fake:6333")
    monkeypatch.setattr(settings, "QDRANT_API_KEY", "")

    chamou_retrieve = {}

    async def _fake_get_qdrant():
        return object()

    async def _fake_retrieve(q, pergunta, collections, k):
        chamou_retrieve["ok"] = True
        return [{"text": "trecho de teste"}]

    import app.db.qdrant as qdrant_mod
    import app.rag.retrieval as retrieval_mod
    monkeypatch.setattr(qdrant_mod, "get_qdrant", _fake_get_qdrant)
    monkeypatch.setattr(retrieval_mod, "retrieve", _fake_retrieve)

    resultado = await ba._rag_docs("pergunta de teste")
    assert chamou_retrieve.get("ok") is True
    assert "trecho de teste" in resultado
