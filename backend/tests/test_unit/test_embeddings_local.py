"""Fase 4.2 — embeddings_local.py (BGE-M3 local) e embeddings_compare.py.

`sentence-transformers` não está instalado neste sandbox e nunca seria
baixado de verdade em CI (~4,6GB de pesos do BAAI/bge-m3) — injeta um
módulo fake em `sys.modules` antes do import lazy dentro de `_get_model()`,
testando a lógica real de singleton sem depender do pacote real.
"""
import asyncio
import sys
import types


class _FakeVector(list):
    def tolist(self):
        return list(self)


class _FakeSentenceTransformer:
    instances = 0

    def __init__(self, name):
        _FakeSentenceTransformer.instances += 1
        self.name = name

    def encode(self, texts, normalize_embeddings=True):
        if isinstance(texts, str):
            return _FakeVector([1.0, 0.0, 0.0])
        return [_FakeVector([1.0, 0.0, 0.0]) for _ in texts]


def setup_module(module):
    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = _FakeSentenceTransformer
    sys.modules["sentence_transformers"] = fake_module


def test_embed_text_local_retorna_vetor_do_modelo():
    from app.rag import embeddings_local
    embeddings_local._model = None

    result = asyncio.run(embeddings_local.embed_text_local("processo trabalhista"))
    assert result == [1.0, 0.0, 0.0]


def test_embed_text_local_string_vazia_nao_instancia_modelo():
    from app.rag import embeddings_local
    embeddings_local._model = None
    _FakeSentenceTransformer.instances = 0

    result = asyncio.run(embeddings_local.embed_text_local("   "))
    assert result == [0.0] * embeddings_local.EMBEDDING_DIMENSIONS_LOCAL
    assert _FakeSentenceTransformer.instances == 0


def test_get_model_singleton_carrega_uma_vez_so():
    from app.rag import embeddings_local
    embeddings_local._model = None
    _FakeSentenceTransformer.instances = 0

    asyncio.run(embeddings_local.embed_text_local("a"))
    asyncio.run(embeddings_local.embed_text_local("b"))
    assert _FakeSentenceTransformer.instances == 1


def test_embed_batch_local_retorna_um_vetor_por_texto():
    from app.rag import embeddings_local
    embeddings_local._model = None

    result = asyncio.run(embeddings_local.embed_batch_local(["a", "b", "c"]))
    assert len(result) == 3
    assert all(r == [1.0, 0.0, 0.0] for r in result)


def test_rank_por_cosseno_ordena_por_similaridade_decrescente():
    from app.services.embeddings_compare import _rank_por_cosseno

    query = [1.0, 0.0]
    docs = [[0.0, 1.0], [1.0, 0.0], [0.7, 0.7]]
    textos = ["ortogonal", "identico", "meio_termo"]

    ranking = _rank_por_cosseno(query, docs, textos)
    assert ranking[0]["text"] == "identico"
    assert ranking[-1]["text"] == "ortogonal"


def test_comparar_embeddings_sem_queries_retorna_erro_sem_tocar_qdrant():
    from app.services import embeddings_compare

    result = asyncio.run(embeddings_compare.comparar_embeddings([], ["doc"]))
    assert result["ok"] is False


def test_comparar_embeddings_sem_documentos_retorna_erro_sem_tocar_qdrant():
    from app.services import embeddings_compare

    result = asyncio.run(embeddings_compare.comparar_embeddings(["query"], []))
    assert result["ok"] is False
