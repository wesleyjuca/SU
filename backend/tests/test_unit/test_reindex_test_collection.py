"""Fase 4.3 Parte 1 — reindexar_amostra_teste/buscar_teste (embeddings_compare.py).

Confirma o invariante de segurança central desta fase: NUNCA escreve
(upsert/delete) nas 7 collections reais de produção, só lê (scroll) delas —
toda escrita vai pra collection descartável `_test_bge_m3_{collection}`.
`sentence-transformers` não está instalado neste sandbox — injeta um módulo
fake em `sys.modules` (mesmo padrão da Fase 4.2) antes do import lazy dentro
de `embed_batch_local`/`embed_text_local`.
"""
import asyncio
import sys
import types


class _FakeVector(list):
    def tolist(self):
        return list(self)


class _FakeSentenceTransformer:
    def __init__(self, name):
        self.name = name

    def encode(self, texts, normalize_embeddings=True):
        if isinstance(texts, str):
            return _FakeVector([1.0, 0.0])
        return [_FakeVector([1.0, 0.0]) for _ in texts]


def setup_module(module):
    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = _FakeSentenceTransformer
    sys.modules["sentence_transformers"] = fake_module


class _FakePoint:
    def __init__(self, payload):
        self.payload = payload


class _FakeCollectionsResult:
    def __init__(self, names):
        self.collections = [types.SimpleNamespace(name=n) for n in names]


class _FakeSearchHit:
    def __init__(self, text, score):
        self.payload = {"text": text}
        self.score = score


class _FakeQdrant:
    def __init__(self, scroll_points=None, existing_collections=None):
        self._scroll_points = scroll_points or []
        self._existing = set(existing_collections or [])
        self.scroll_calls = []
        self.upsert_calls = []
        self.delete_calls = []
        self.create_collection_calls = []
        self.search_calls = []

    async def get_collections(self):
        # Espelha o shape real do qdrant-client: um objeto com .collections
        # (lista) — NÃO diretamente iterável do jeito que dá `.name` (pydantic
        # BaseModel itera como (campo, valor), não os itens de `.collections`).
        return _FakeCollectionsResult(self._existing)

    async def scroll(self, collection_name, limit, with_payload, with_vectors):
        self.scroll_calls.append(collection_name)
        return self._scroll_points[:limit], None

    async def create_collection(self, collection_name, vectors_config):
        self.create_collection_calls.append(collection_name)
        self._existing.add(collection_name)

    async def upsert(self, collection_name, points):
        self.upsert_calls.append((collection_name, len(points)))

    async def delete(self, collection_name, **kw):
        self.delete_calls.append(collection_name)

    async def search(self, collection_name, query_vector, limit, with_payload=True):
        self.search_calls.append(collection_name)
        return [_FakeSearchHit(f"resultado-{i}", 1.0 - i * 0.1) for i in range(min(limit, 3))]


def _patch_qdrant(monkeypatch_mod, fake_client):
    async def fake_get_qdrant():
        return fake_client
    monkeypatch_mod.get_qdrant = fake_get_qdrant


def test_reindexar_amostra_teste_rejeita_collection_desconhecida():
    from app.services import embeddings_compare as ec
    result = asyncio.run(ec.reindexar_amostra_teste("collection_que_nao_existe", limite=10))
    assert result["ok"] is False
    assert "desconhecida" in result["detail"].lower()


def test_reindexar_amostra_teste_rejeita_limite_nao_positivo():
    from app.services import embeddings_compare as ec
    result = asyncio.run(ec.reindexar_amostra_teste("peticoes_afj", limite=0))
    assert result["ok"] is False


def test_reindexar_amostra_teste_nunca_escreve_na_collection_real():
    from app.services import embeddings_compare as ec

    pontos = [_FakePoint({"text": "texto A"}), _FakePoint({"text": "texto B"})]
    fake = _FakeQdrant(scroll_points=pontos, existing_collections=set())
    original_get_qdrant = ec.get_qdrant
    _patch_qdrant(ec, fake)
    try:
        result = asyncio.run(ec.reindexar_amostra_teste("peticoes_afj", limite=200))
    finally:
        ec.get_qdrant = original_get_qdrant

    assert result["ok"] is True
    assert result["pontos_lidos"] == 2
    assert result["pontos_reindexados"] == 2
    assert result["collection_origem"] == "peticoes_afj"
    assert result["collection_teste"] == "_test_bge_m3_peticoes_afj"

    # Invariante de segurança central: só leu (scroll) a collection real,
    # nunca escreveu (upsert/delete) nela.
    assert fake.scroll_calls == ["peticoes_afj"]
    assert fake.upsert_calls == [("_test_bge_m3_peticoes_afj", 2)]
    assert fake.delete_calls == []
    for chamada in fake.upsert_calls:
        assert chamada[0] != "peticoes_afj"


def test_reindexar_amostra_teste_respeita_limite():
    from app.services import embeddings_compare as ec

    pontos = [_FakePoint({"text": f"doc {i}"}) for i in range(500)]
    fake = _FakeQdrant(scroll_points=pontos, existing_collections=set())
    original_get_qdrant = ec.get_qdrant
    _patch_qdrant(ec, fake)
    try:
        result = asyncio.run(ec.reindexar_amostra_teste("jurisprudencia", limite=50))
    finally:
        ec.get_qdrant = original_get_qdrant

    assert result["pontos_lidos"] == 50
    assert result["pontos_reindexados"] == 50


def test_reindexar_amostra_teste_falha_soft_sem_texto():
    from app.services import embeddings_compare as ec

    pontos = [_FakePoint({}), _FakePoint({"outro_campo": "x"})]
    fake = _FakeQdrant(scroll_points=pontos, existing_collections=set())
    original_get_qdrant = ec.get_qdrant
    _patch_qdrant(ec, fake)
    try:
        result = asyncio.run(ec.reindexar_amostra_teste("legislacao", limite=10))
    finally:
        ec.get_qdrant = original_get_qdrant

    assert result["ok"] is False
    assert fake.upsert_calls == []


def test_reindexar_amostra_teste_nao_recria_collection_de_teste_existente():
    from app.services import embeddings_compare as ec

    pontos = [_FakePoint({"text": "x"})]
    fake = _FakeQdrant(scroll_points=pontos, existing_collections={"_test_bge_m3_doutrina"})
    original_get_qdrant = ec.get_qdrant
    _patch_qdrant(ec, fake)
    try:
        asyncio.run(ec.reindexar_amostra_teste("doutrina", limite=10))
    finally:
        ec.get_qdrant = original_get_qdrant

    assert fake.create_collection_calls == []


def test_buscar_teste_sem_query_retorna_erro():
    from app.services import embeddings_compare as ec
    result = asyncio.run(ec.buscar_teste("peticoes_afj", "   "))
    assert result["ok"] is False


def test_buscar_teste_collection_inexistente_retorna_erro_claro():
    from app.services import embeddings_compare as ec

    fake = _FakeQdrant(existing_collections=set())
    original_get_qdrant = ec.get_qdrant
    _patch_qdrant(ec, fake)
    try:
        result = asyncio.run(ec.buscar_teste("memorias_afj", "prazo recursal"))
    finally:
        ec.get_qdrant = original_get_qdrant

    assert result["ok"] is False
    assert "reindex" in result["detail"].lower()
    assert fake.search_calls == []


def test_buscar_teste_busca_na_collection_de_teste_correta():
    from app.services import embeddings_compare as ec

    fake = _FakeQdrant(existing_collections={"_test_bge_m3_documentos_clientes"})
    original_get_qdrant = ec.get_qdrant
    _patch_qdrant(ec, fake)
    try:
        result = asyncio.run(ec.buscar_teste("documentos_clientes", "citação de lei", limite=3))
    finally:
        ec.get_qdrant = original_get_qdrant

    assert result["ok"] is True
    assert result["collection_teste"] == "_test_bge_m3_documentos_clientes"
    assert len(result["resultados"]) == 3
    assert fake.search_calls == ["_test_bge_m3_documentos_clientes"]


def test_reindexar_amostra_teste_fail_soft_quando_embed_falha():
    """Achado real em produção: embed_batch_local carrega o BGE-M3 (~4,6GB) na
    1ª chamada — se isso falhar (memória/disco/rede), o endpoint HTTP devolvia
    um 500 genérico sem nenhuma pista. Confirma que agora vira um erro com
    `detail` acionável, nunca uma exceção não tratada."""
    from app.services import embeddings_compare as ec

    pontos = [_FakePoint({"text": "texto A"})]
    fake = _FakeQdrant(scroll_points=pontos, existing_collections=set())
    original_get_qdrant = ec.get_qdrant
    original_embed_batch = ec.embed_batch_local
    _patch_qdrant(ec, fake)

    async def fake_embed_batch_falha(texts):
        raise RuntimeError("não foi possível carregar o modelo BAAI/bge-m3 (sem memória/disco)")

    ec.embed_batch_local = fake_embed_batch_falha
    try:
        result = asyncio.run(ec.reindexar_amostra_teste("peticoes_afj", limite=10))
    finally:
        ec.get_qdrant = original_get_qdrant
        ec.embed_batch_local = original_embed_batch

    assert result["ok"] is False
    assert "bge-m3" in result["detail"].lower()
    # Nunca escreveu na collection de teste com vetores incompletos/quebrados.
    assert fake.upsert_calls == []


def test_buscar_teste_fail_soft_quando_embed_falha():
    from app.services import embeddings_compare as ec

    fake = _FakeQdrant(existing_collections={"_test_bge_m3_peticoes_afj"})
    original_get_qdrant = ec.get_qdrant
    original_embed_text = ec.embed_text_local
    _patch_qdrant(ec, fake)

    async def fake_embed_text_falha(text):
        raise RuntimeError("timeout ao carregar o modelo")

    ec.embed_text_local = fake_embed_text_falha
    try:
        result = asyncio.run(ec.buscar_teste("peticoes_afj", "prazo recursal"))
    finally:
        ec.get_qdrant = original_get_qdrant
        ec.embed_text_local = original_embed_text

    assert result["ok"] is False
    assert "timeout" in result["detail"].lower()
    assert fake.search_calls == []
