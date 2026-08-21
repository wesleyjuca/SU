"""Agregações sobre coleções Qdrant — leitura em lote via scroll(), não busca
semântica (ver app/rag/retrieval.py pra isso). Fase 138.5."""
from collections import defaultdict

SCROLL_BATCH_SIZE = 500


async def agregar_favorabilidade_por_relator(qdrant_client, collection: str = "jurisprudencia") -> list[dict]:
    """Varre toda a collection (scroll paginado, só payload relator/favoravel/
    document_id, sem vetores) e agrega contagem de favorável/desfavorável por
    relator. Deduplica por `document_id` (cada acórdão vira N chunks com a
    mesma metadata — sem dedup, o total contaria chunks, não documentos).
    Pontos sem `relator`, sem `document_id` ou sem `favoravel` classificado
    (campo ausente do payload — acórdão ainda não classificado ou ingerido
    antes da Fase 138.5) são ignorados.

    Retorna lista ordenada por `total` desc:
    [{"relator": str, "total": int, "favoraveis": int, "taxa_favoravel": float}, ...]
    """
    contagem: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "favoraveis": 0})
    vistos: set[str] = set()

    offset = None
    while True:
        pontos, offset = await qdrant_client.scroll(
            collection_name=collection,
            limit=SCROLL_BATCH_SIZE,
            offset=offset,
            with_payload=["relator", "favoravel", "document_id"],
            with_vectors=False,
        )
        for ponto in pontos:
            payload = ponto.payload or {}
            doc_id = payload.get("document_id")
            relator = payload.get("relator")
            favoravel = payload.get("favoravel")
            if not doc_id or doc_id in vistos or not relator or not isinstance(favoravel, bool):
                continue
            vistos.add(doc_id)
            contagem[relator]["total"] += 1
            if favoravel:
                contagem[relator]["favoraveis"] += 1
        if not pontos or offset is None:
            break

    resultado = [
        {
            "relator": relator,
            "total": c["total"],
            "favoraveis": c["favoraveis"],
            "taxa_favoravel": round(c["favoraveis"] / c["total"], 4) if c["total"] else 0.0,
        }
        for relator, c in contagem.items()
    ]
    resultado.sort(key=lambda x: x["total"], reverse=True)
    return resultado


async def detalhar_relator(qdrant_client, relator: str, collection: str = "jurisprudencia", limite: int = 200) -> list[dict]:
    """Fase 206.1 — lista os acórdãos de um relator específico, por trás da
    contagem agregada de `agregar_favorabilidade_por_relator`. Mesmo scroll
    paginado e mesma dedup por `document_id`, mas retendo os campos por
    documento em vez de só somar. Teto de `limite` documentos (relatores
    muito prolíficos não devolvem lista ilimitada)."""
    vistos: set[str] = set()
    resultado: list[dict] = []

    offset = None
    while len(resultado) < limite:
        pontos, offset = await qdrant_client.scroll(
            collection_name=collection,
            limit=SCROLL_BATCH_SIZE,
            offset=offset,
            with_payload=["relator", "favoravel", "document_id", "area_direito", "numero_processo", "data", "orgao_julgador"],
            with_vectors=False,
        )
        for ponto in pontos:
            payload = ponto.payload or {}
            doc_id = payload.get("document_id")
            favoravel = payload.get("favoravel")
            if (
                payload.get("relator") != relator or not doc_id or doc_id in vistos
                or not isinstance(favoravel, bool)
            ):
                continue
            vistos.add(doc_id)
            resultado.append({
                "document_id": doc_id,
                "numero_processo": payload.get("numero_processo"),
                "data": payload.get("data"),
                "orgao_julgador": payload.get("orgao_julgador"),
                "area_direito": payload.get("area_direito"),
                "favoravel": payload.get("favoravel"),
            })
            if len(resultado) >= limite:
                break
        if not pontos or offset is None:
            break

    resultado.sort(key=lambda d: d.get("data") or "", reverse=True)
    return resultado
