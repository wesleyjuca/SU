"""Fase 116 — coleções privadas do RAG devem indexar tenant_id no payload.

`retrieval.py::PRIVATE_COLLECTIONS` filtra por tenant_id em toda busca
vetorial dessas 3 coleções, mas o payload_fields de `collections.py` nunca
declarava esse campo como indexado — todo filtro de isolamento multi-tenant
dependia de scan não-indexado. Este teste trava a correção: garante que as
3 coleções privadas sempre têm tenant_id nos payload_fields.
"""
from app.rag.collections import COLLECTIONS
from app.rag.retrieval import PRIVATE_COLLECTIONS


def test_todas_as_colecoes_privadas_tem_tenant_id_indexado():
    for nome in PRIVATE_COLLECTIONS:
        assert "tenant_id" in COLLECTIONS[nome]["payload_fields"], (
            f"coleção privada '{nome}' não indexa tenant_id — "
            "filtro de isolamento multi-tenant ficaria sem índice"
        )


def test_colecoes_publicas_nao_precisam_de_tenant_id():
    # jurisprudencia/legislacao/doutrina são compartilhadas entre tenants —
    # não devem ganhar o campo à toa (documenta a distinção público/privado).
    publicas = set(COLLECTIONS) - PRIVATE_COLLECTIONS - {"documentacao_sistema"}
    assert publicas == {"jurisprudencia", "doutrina", "legislacao"}
