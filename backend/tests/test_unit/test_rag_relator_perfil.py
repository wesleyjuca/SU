"""Fase 206.1 — perfil de relator/juiz: drill-down por trás da agregação de
favorabilidade já existente desde a Fase 138.5. Qdrant real em memória (não
um Fake escrito à mão), mesmo padrão da Fase 187 — `detalhar_relator()` usa
`scroll()`, igual `agregar_favorabilidade_por_relator()`."""
import pytest
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.config import settings
from app.rag.aggregation import agregar_favorabilidade_por_relator, detalhar_relator

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def qdrant_memoria():
    client = AsyncQdrantClient(location=":memory:")
    await client.create_collection(
        collection_name="jurisprudencia",
        vectors_config=VectorParams(size=settings.EMBEDDING_DIMENSIONS, distance=Distance.COSINE),
    )
    v = [0.01] * settings.EMBEDDING_DIMENSIONS
    pontos = [
        # Relator A: 2 chunks do MESMO acórdão (document_id doc-1) — dedup
        # não pode contar 2x.
        PointStruct(id=1, vector=v, payload={
            "relator": "Min. Fulano", "favoravel": True, "document_id": "doc-1",
            "numero_processo": "0001", "data": "2026-01-10", "orgao_julgador": "1ª Turma", "area_direito": "CIVIL",
        }),
        PointStruct(id=2, vector=v, payload={
            "relator": "Min. Fulano", "favoravel": True, "document_id": "doc-1",
            "numero_processo": "0001", "data": "2026-01-10", "orgao_julgador": "1ª Turma", "area_direito": "CIVIL",
        }),
        PointStruct(id=3, vector=v, payload={
            "relator": "Min. Fulano", "favoravel": False, "document_id": "doc-2",
            "numero_processo": "0002", "data": "2026-02-15", "orgao_julgador": "2ª Turma", "area_direito": "TRIBUTARIO",
        }),
        # Relator B — não deve aparecer no drill-down de "Min. Fulano".
        PointStruct(id=4, vector=v, payload={
            "relator": "Min. Beltrano", "favoravel": True, "document_id": "doc-3",
            "numero_processo": "0003", "data": "2026-03-01", "orgao_julgador": "3ª Turma", "area_direito": "PENAL",
        }),
        # Sem classificação (favoravel ausente) — ignorado por ambas as funções.
        PointStruct(id=5, vector=v, payload={
            "relator": "Min. Fulano", "document_id": "doc-4", "numero_processo": "0004",
        }),
    ]
    await client.upsert(collection_name="jurisprudencia", points=pontos)
    return client


async def test_agregacao_ainda_bate_2_documentos_pro_relator(qdrant_memoria):
    dados = await agregar_favorabilidade_por_relator(qdrant_memoria, "jurisprudencia")
    fulano = next(r for r in dados if r["relator"] == "Min. Fulano")
    assert fulano["total"] == 2  # doc-1 (dedup) + doc-2
    assert fulano["favoraveis"] == 1


async def test_detalhar_relator_lista_os_acordaos_do_relator_certo(qdrant_memoria):
    acordaos = await detalhar_relator(qdrant_memoria, "Min. Fulano", "jurisprudencia")

    assert len(acordaos) == 2
    ids = {a["document_id"] for a in acordaos}
    assert ids == {"doc-1", "doc-2"}
    doc1 = next(a for a in acordaos if a["document_id"] == "doc-1")
    assert doc1["numero_processo"] == "0001"
    assert doc1["favoravel"] is True
    assert doc1["orgao_julgador"] == "1ª Turma"
    doc2 = next(a for a in acordaos if a["document_id"] == "doc-2")
    assert doc2["favoravel"] is False


async def test_detalhar_relator_nao_traz_acordao_de_outro_relator(qdrant_memoria):
    acordaos = await detalhar_relator(qdrant_memoria, "Min. Beltrano", "jurisprudencia")
    assert len(acordaos) == 1
    assert acordaos[0]["document_id"] == "doc-3"


async def test_detalhar_relator_inexistente_devolve_lista_vazia(qdrant_memoria):
    acordaos = await detalhar_relator(qdrant_memoria, "Min. Ninguem", "jurisprudencia")
    assert acordaos == []
