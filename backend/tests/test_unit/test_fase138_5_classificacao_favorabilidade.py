"""Fase 138.5 — classificação LLM (favoravel/area_direito) do pipeline STJ +
agregação de favorabilidade por relator (scroll Qdrant mockado)."""
import pytest

from app.workers.tasks.jurisprudencia_sync import (
    classificar_acordao,
    _extrair_classificacao,
)
from app.rag.aggregation import agregar_favorabilidade_por_relator


@pytest.mark.asyncio
async def test_classificar_acordao_sucesso(monkeypatch):
    async def _fake_call_llm(**kwargs):
        assert kwargs["model"] == "claude-haiku-4-5-20251001"
        return ('{"favoravel": true, "area_direito": "CIVIL"}', 100, 20, 0.001)

    monkeypatch.setattr("app.integrations.llm_client.call_llm", _fake_call_llm)

    resultado = await classificar_acordao("Trata-se de recurso especial...")
    assert resultado == {"favoravel": True, "area_direito": "CIVIL", "custo_usd": 0.001}


@pytest.mark.asyncio
async def test_classificar_acordao_json_malformado_retorna_none(monkeypatch):
    async def _fake_call_llm(**kwargs):
        return ("não sei responder isso", 50, 5, 0.0001)

    monkeypatch.setattr("app.integrations.llm_client.call_llm", _fake_call_llm)

    assert await classificar_acordao("texto qualquer") is None


@pytest.mark.asyncio
async def test_classificar_acordao_area_fora_do_vocabulario_retorna_none(monkeypatch):
    async def _fake_call_llm(**kwargs):
        return ('{"favoravel": true, "area_direito": "ESPORTE"}', 50, 10, 0.0001)

    monkeypatch.setattr("app.integrations.llm_client.call_llm", _fake_call_llm)

    assert await classificar_acordao("texto qualquer") is None


@pytest.mark.asyncio
async def test_classificar_acordao_llm_lanca_excecao_retorna_none(monkeypatch):
    async def _fake_call_llm(**kwargs):
        raise RuntimeError("timeout de rede")

    monkeypatch.setattr("app.integrations.llm_client.call_llm", _fake_call_llm)

    assert await classificar_acordao("texto qualquer") is None


@pytest.mark.asyncio
async def test_classificar_acordao_texto_vazio_nao_chama_llm(monkeypatch):
    chamou = {"sim": False}

    async def _fake_call_llm(**kwargs):
        chamou["sim"] = True
        return ("{}", 0, 0, 0.0)

    monkeypatch.setattr("app.integrations.llm_client.call_llm", _fake_call_llm)

    assert await classificar_acordao("   ") is None
    assert chamou["sim"] is False


def test_extrair_classificacao_com_cerca_markdown():
    resposta = '```json\n{"favoravel": false, "area_direito": "penal"}\n```'
    resultado = _extrair_classificacao(resposta)
    assert resultado == {"favoravel": False, "area_direito": "PENAL"}


def test_extrair_classificacao_campo_favoravel_ausente_retorna_none():
    assert _extrair_classificacao('{"area_direito": "CIVIL"}') is None


def test_extrair_classificacao_texto_vazio_retorna_none():
    assert _extrair_classificacao("") is None
    assert _extrair_classificacao(None) is None


class _FakeQdrantScroll:
    """Simula qdrant_client.scroll() com paginação em 2 páginas."""

    def __init__(self, paginas):
        self._paginas = paginas
        self._chamadas = 0

    async def scroll(self, collection_name, limit, offset, with_payload, with_vectors):
        pagina = self._paginas[self._chamadas]
        self._chamadas += 1
        return pagina

    class _Ponto:
        def __init__(self, payload):
            self.payload = payload


def _ponto(payload):
    return _FakeQdrantScroll._Ponto(payload)


@pytest.mark.asyncio
async def test_agregar_favorabilidade_por_relator_dedup_e_filtros():
    pagina1 = (
        [
            # 2 chunks do mesmo acórdão (mesmo document_id) — deve contar 1x
            _ponto({"relator": "Min. Fulano", "favoravel": True, "document_id": "doc-1"}),
            _ponto({"relator": "Min. Fulano", "favoravel": True, "document_id": "doc-1"}),
            # sem favoravel classificado (acórdão antigo, pré-138.5) — ignorado
            _ponto({"relator": "Min. Fulano", "document_id": "doc-2"}),
            # sem relator — ignorado
            _ponto({"favoravel": False, "document_id": "doc-3"}),
        ],
        "offset-2",
    )
    pagina2 = (
        [
            _ponto({"relator": "Min. Fulano", "favoravel": False, "document_id": "doc-4"}),
            _ponto({"relator": "Min. Beltrana", "favoravel": True, "document_id": "doc-5"}),
        ],
        None,
    )
    fake = _FakeQdrantScroll([pagina1, pagina2])

    resultado = await agregar_favorabilidade_por_relator(fake, "jurisprudencia")

    por_relator = {r["relator"]: r for r in resultado}
    assert por_relator["Min. Fulano"]["total"] == 2  # doc-1 (dedup) + doc-4
    assert por_relator["Min. Fulano"]["favoraveis"] == 1
    assert por_relator["Min. Fulano"]["taxa_favoravel"] == 0.5
    assert por_relator["Min. Beltrana"]["total"] == 1
    assert por_relator["Min. Beltrana"]["favoraveis"] == 1
    assert por_relator["Min. Beltrana"]["taxa_favoravel"] == 1.0
    # ordenado por total desc
    assert resultado[0]["relator"] == "Min. Fulano"


@pytest.mark.asyncio
async def test_agregar_favorabilidade_colecao_vazia_retorna_lista_vazia():
    fake = _FakeQdrantScroll([([], None)])
    resultado = await agregar_favorabilidade_por_relator(fake, "jurisprudencia")
    assert resultado == []


@pytest.mark.asyncio
async def test_endpoint_favorabilidade_sem_cache(monkeypatch):
    from app.api.v1.rag import rag_jurisprudencia_favorabilidade

    class _FakeUser:
        tenant_id = "t1"

    async def _fake_get_redis():
        return None

    fake_qdrant = _FakeQdrantScroll([([_ponto({"relator": "Min. X", "favoravel": True, "document_id": "d1"})], None)])

    async def _fake_get_qdrant():
        return fake_qdrant

    import app.db.redis as redis_mod
    import app.db.qdrant as qdrant_mod
    monkeypatch.setattr(redis_mod, "get_redis", _fake_get_redis)
    monkeypatch.setattr(qdrant_mod, "get_qdrant", _fake_get_qdrant)

    resp = await rag_jurisprudencia_favorabilidade(current_user=_FakeUser())
    assert resp["relatores"][0]["relator"] == "Min. X"


@pytest.mark.asyncio
async def test_endpoint_favorabilidade_qdrant_indisponivel_retorna_503(monkeypatch):
    from fastapi import HTTPException
    from app.api.v1.rag import rag_jurisprudencia_favorabilidade

    class _FakeUser:
        tenant_id = "t1"

    async def _fake_get_redis():
        return None

    async def _fake_get_qdrant():
        raise RuntimeError("qdrant off")

    import app.db.redis as redis_mod
    import app.db.qdrant as qdrant_mod
    monkeypatch.setattr(redis_mod, "get_redis", _fake_get_redis)
    monkeypatch.setattr(qdrant_mod, "get_qdrant", _fake_get_qdrant)

    with pytest.raises(HTTPException) as exc_info:
        await rag_jurisprudencia_favorabilidade(current_user=_FakeUser())
    assert exc_info.value.status_code == 503
