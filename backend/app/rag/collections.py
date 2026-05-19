"""Definição das 6 collections Qdrant do AFJ CORE SYSTEM."""
from qdrant_client.models import Distance, VectorParams, PayloadSchemaType
from app.config import settings

COLLECTIONS: dict[str, dict] = {
    "jurisprudencia": {
        "description": "Acórdãos STJ/STF/TRF/TJ indexados — fonte verificável obrigatória",
        "vector_size": settings.EMBEDDING_DIMENSIONS,
        "distance": Distance.COSINE,
        "payload_fields": {
            "tribunal": PayloadSchemaType.KEYWORD,
            "numero_processo": PayloadSchemaType.KEYWORD,
            "area_direito": PayloadSchemaType.KEYWORD,
            "favoravel": PayloadSchemaType.BOOL,
        },
    },
    "peticoes_afj": {
        "description": "Petições do próprio escritório — referência de estilo e estratégia",
        "vector_size": settings.EMBEDDING_DIMENSIONS,
        "distance": Distance.COSINE,
        "payload_fields": {
            "tipo": PayloadSchemaType.KEYWORD,
            "area": PayloadSchemaType.KEYWORD,
            "tribunal": PayloadSchemaType.KEYWORD,
            "outcome": PayloadSchemaType.KEYWORD,
        },
    },
    "doutrina": {
        "description": "Doutrina jurídica — livros, artigos, comentários",
        "vector_size": settings.EMBEDDING_DIMENSIONS,
        "distance": Distance.COSINE,
        "payload_fields": {
            "autor": PayloadSchemaType.KEYWORD,
            "area": PayloadSchemaType.KEYWORD,
        },
    },
    "legislacao": {
        "description": "Leis, códigos e regulamentos brasileiros (CPC, CC, CLT, etc.)",
        "vector_size": settings.EMBEDDING_DIMENSIONS,
        "distance": Distance.COSINE,
        "payload_fields": {
            "diploma": PayloadSchemaType.KEYWORD,
            "artigo": PayloadSchemaType.KEYWORD,
        },
    },
    "memorias_afj": {
        "description": "Memória institucional do escritório — estratégias e conhecimento acumulado",
        "vector_size": settings.EMBEDDING_DIMENSIONS,
        "distance": Distance.COSINE,
        "payload_fields": {
            "tipo": PayloadSchemaType.KEYWORD,
            "agent_source": PayloadSchemaType.KEYWORD,
        },
    },
    "documentos_clientes": {
        "description": "Documentos dos clientes indexados — acesso controlado por permissão",
        "vector_size": settings.EMBEDDING_DIMENSIONS,
        "distance": Distance.COSINE,
        "payload_fields": {
            "client_id": PayloadSchemaType.KEYWORD,
            "document_id": PayloadSchemaType.KEYWORD,
            "tipo": PayloadSchemaType.KEYWORD,
        },
    },
}


async def ensure_collections(qdrant_client):
    """Cria collections no Qdrant se não existirem. Chamado na startup."""
    existing = {c.name for c in await qdrant_client.get_collections()}

    for name, config in COLLECTIONS.items():
        if name not in existing:
            await qdrant_client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(
                    size=config["vector_size"],
                    distance=config["distance"],
                ),
            )
            # Criar índices de payload
            for field_name, field_type in config.get("payload_fields", {}).items():
                await qdrant_client.create_payload_index(
                    collection_name=name,
                    field_name=field_name,
                    field_schema=field_type,
                )
