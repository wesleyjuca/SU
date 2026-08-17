"""Definição das 8 collections Qdrant do AFJ CORE SYSTEM."""
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
            # Já capturado no painel manual de indexação desde sempre, nunca
            # tinha sido indexado pra filtro/agregação (Fase 138.1).
            "relator": PayloadSchemaType.KEYWORD,
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
            # Coleção privada (retrieval.py::PRIVATE_COLLECTIONS) — todo filtro
            # de isolamento multi-tenant usa este campo, precisa de índice.
            "tenant_id": PayloadSchemaType.KEYWORD,
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
    "doutrina_privada": {
        "description": "Doutrina própria do escritório (pasta do Google Drive, Fase 138.2) — "
                        "isolada por tenant, distinta da doutrina compartilhada acima. "
                        "Conteúdo trazido pelo próprio escritório (direito de uso já do "
                        "escritório), nunca deve aparecer pra outro tenant.",
        "vector_size": settings.EMBEDDING_DIMENSIONS,
        "distance": Distance.COSINE,
        "payload_fields": {
            "nome_arquivo": PayloadSchemaType.KEYWORD,
            "google_file_id": PayloadSchemaType.KEYWORD,
            # Coleção privada — ver nota em peticoes_afj acima.
            "tenant_id": PayloadSchemaType.KEYWORD,
        },
    },
    "legislacao": {
        "description": "Leis, códigos e regulamentos brasileiros (CPC, CC, CLT, etc.)",
        "vector_size": settings.EMBEDDING_DIMENSIONS,
        "distance": Distance.COSINE,
        "payload_fields": {
            "diploma": PayloadSchemaType.KEYWORD,
            "artigo": PayloadSchemaType.KEYWORD,
            # Fase 138.3 — ingestão automática via LexML/Planalto.
            "tipo_norma": PayloadSchemaType.KEYWORD,  # "Lei" | "Decreto"
            "urn": PayloadSchemaType.KEYWORD,         # URN LexML, chave estável do documento
        },
    },
    "memorias_afj": {
        "description": "Memória institucional do escritório — estratégias e conhecimento acumulado",
        "vector_size": settings.EMBEDDING_DIMENSIONS,
        "distance": Distance.COSINE,
        "payload_fields": {
            "tipo": PayloadSchemaType.KEYWORD,
            "agent_source": PayloadSchemaType.KEYWORD,
            # Coleção privada — ver nota em peticoes_afj acima.
            "tenant_id": PayloadSchemaType.KEYWORD,
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
            # Coleção privada — ver nota em peticoes_afj acima.
            "tenant_id": PayloadSchemaType.KEYWORD,
        },
    },
    "documentacao_sistema": {
        "description": "Documentação/arquitetura do próprio sistema — base do assistente do Cérebro (SUPERADMIN)",
        "vector_size": settings.EMBEDDING_DIMENSIONS,
        "distance": Distance.COSINE,
        "payload_fields": {
            "fonte": PayloadSchemaType.KEYWORD,
        },
    },
}


async def ensure_collections(qdrant_client):
    """Cria collections no Qdrant se não existirem. Chamado na startup.

    Fase 198 — achado da Fase 197: `get_collections()` devolve um
    `CollectionsResponse` (pydantic), não uma lista — iterar o objeto
    direto itera seus campos (`[("collections", [...])]`), não as
    collections em si. `c.name` explodia com AttributeError em qualquer
    ambiente com QDRANT_URL real configurado (silenciado pelo except do
    warmup, nunca visto neste sandbox)."""
    existing = {c.name for c in (await qdrant_client.get_collections()).collections}

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
        else:
            # Fase 116 — coleção já existia antes do payload_fields ganhar
            # campos novos (ex.: tenant_id nas privadas). create_payload_index
            # é idempotente no Qdrant (recria o índice se já existir com o
            # mesmo schema); best-effort para não travar o boot por um campo.
            for field_name, field_type in config.get("payload_fields", {}).items():
                try:
                    await qdrant_client.create_payload_index(
                        collection_name=name,
                        field_name=field_name,
                        field_schema=field_type,
                    )
                except Exception:
                    pass
