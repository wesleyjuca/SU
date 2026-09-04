"""Fase 255 — usuário reportou "Serviço RAG indisponível: OPENAI_API_KEY
não configurada" na tela de Pesquisa Jurídica. Ao contrário de toda outra
rota de IA do sistema (generate_petition/review_document/manage_contract/
brain_insights/brain_assistant/prazo_sugestao), embeddings nunca olhava o
BYOK do usuário — dependia 100% da chave central do servidor. Este teste
prova, com Qdrant real em memória (mesmo padrão da Fase 187,
test_rag_retrieval_real_qdrant.py) e Postgres real (AIProviderConfig de
verdade), que POST /rag/search agora usa a chave BYOK do usuário quando a
central está ausente — sem BYOK, o comportamento (chave central, ou o
RuntimeError de sempre) fica intacto."""
import json
import uuid

import pytest
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

import app.api.v1.rag as rag_mod
import app.rag.embeddings as emb_mod
from app.config import settings
from app.core.crypto import encrypt
from app.db.base import AsyncSessionLocal
from app.models.ai_config import AIProviderConfig
from app.models.tenant import Tenant
from app.models.user import User

pytestmark = pytest.mark.anyio


class _CurrentUser:
    def __init__(self, tenant_id, uid):
        self.tenant_id = tenant_id
        self.id = uid


class _FakeEmbeddingsAPI:
    last_construct_key = None

    def __init__(self, *a, **kw):
        pass

    class Data:
        def __init__(self, embedding, index):
            self.embedding = embedding
            self.index = index

    class Response:
        def __init__(self, data):
            self.data = data

    async def create(self, input, model, dimensions):
        texts = input if isinstance(input, list) else [input]
        return self.Response([self.Data([0.0105] * dimensions, i) for i in range(len(texts))])


class _FakeAsyncOpenAI:
    def __init__(self, api_key=None, base_url=None):
        _FakeEmbeddingsAPI.last_construct_key = api_key
        self.embeddings = _FakeEmbeddingsAPI()


@pytest.fixture
async def qdrant_memoria():
    client = AsyncQdrantClient(location=":memory:")
    await client.create_collection(
        collection_name="legislacao",
        vectors_config=VectorParams(size=settings.EMBEDDING_DIMENSIONS, distance=Distance.COSINE),
    )
    await client.upsert(
        collection_name="legislacao",
        points=[PointStruct(id=1, vector=[0.0105] * settings.EMBEDDING_DIMENSIONS,
                             payload={"text": "art. 5º da lei de teste"})],
    )
    return client


@pytest.fixture
async def usuario_com_byok_openai():
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant 255", slug=f"teste-255-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        user = User(
            email=f"user-255-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
            full_name="Usuario Teste 255", role="ADVOGADO", tenant_id=tenant.id,
        )
        db.add(user)
        await db.flush()
        cfg = AIProviderConfig(
            user_id=user.id, provider="openai", model="text-embedding-3-large",
            display_name="Minha IA — OpenAI",
            credentials_enc=encrypt(json.dumps({"api_key": "sk-byok-fase255"})),
            enabled=True, is_default=True,
        )
        db.add(cfg)
        await db.commit()
        ids = {"tenant": tenant.id, "user": user.id}
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(AIProviderConfig.__table__.delete().where(AIProviderConfig.user_id == ids["user"]))
        await db.execute(User.__table__.delete().where(User.id == ids["user"]))
        await db.execute(Tenant.__table__.delete().where(Tenant.id == ids["tenant"]))
        await db.commit()


async def test_rag_search_usa_byok_quando_chave_central_ausente(
    usuario_com_byok_openai, qdrant_memoria, monkeypatch,
):
    monkeypatch.setattr(emb_mod, "AsyncOpenAI", _FakeAsyncOpenAI)
    emb_mod._client = None
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")

    async def _fake_get_qdrant():
        return qdrant_memoria

    import app.db.qdrant as qdrant_mod
    monkeypatch.setattr(qdrant_mod, "get_qdrant", _fake_get_qdrant)

    cu = _CurrentUser(usuario_com_byok_openai["tenant"], usuario_com_byok_openai["user"])
    async with AsyncSessionLocal() as db:
        req = rag_mod.SearchRequest(query="art. 5º", collections=["legislacao"], k=5, score_threshold=0.0)
        resposta = await rag_mod.rag_search(req, db=db, current_user=cu)

    assert resposta["count"] == 1
    assert resposta["results"][0]["content"] == "art. 5º da lei de teste"
    assert _FakeEmbeddingsAPI.last_construct_key == "sk-byok-fase255"


async def test_rag_search_sem_byok_e_sem_chave_central_falha_com_mensagem_clara(
    qdrant_memoria, monkeypatch,
):
    """Regressão: sem BYOK nenhum e sem chave central, o comportamento de
    antes se mantém — 503 claro, não um crash silencioso."""
    from fastapi import HTTPException

    monkeypatch.setattr(emb_mod, "AsyncOpenAI", _FakeAsyncOpenAI)
    emb_mod._client = None
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")

    async def _fake_get_qdrant():
        return qdrant_memoria

    import app.db.qdrant as qdrant_mod
    monkeypatch.setattr(qdrant_mod, "get_qdrant", _fake_get_qdrant)

    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant 255 sem BYOK", slug=f"teste-255-sembyok-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        user = User(
            email=f"user-255-sembyok-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
            full_name="Usuario Sem BYOK", role="ADVOGADO", tenant_id=tenant.id,
        )
        db.add(user)
        await db.commit()
        cu = _CurrentUser(tenant.id, user.id)
        tenant_id = tenant.id

    async with AsyncSessionLocal() as db:
        req = rag_mod.SearchRequest(query="art. 5º", collections=["legislacao"], k=5, score_threshold=0.0)
        with pytest.raises(HTTPException) as exc:
            await rag_mod.rag_search(req, db=db, current_user=cu)
    assert exc.value.status_code == 503
    # Fase pós-260 — detail passou a ser um dict estruturado
    # ({"message", "needs_embedding_provider"}) pro frontend parar de
    # fazer sniffing de texto pra decidir se mostra o link "Ir para Minha IA".
    assert "OPENAI_API_KEY" in exc.value.detail["message"]
    assert exc.value.detail["needs_embedding_provider"] is True

    async with AsyncSessionLocal() as db:
        await db.execute(User.__table__.delete().where(User.tenant_id == tenant_id))
        await db.execute(Tenant.__table__.delete().where(Tenant.id == tenant_id))
        await db.commit()


# Fase pós-260 — Pesquisa Jurídica não fica mais presa a um único provedor:
# tenant com Gemini BYOK ingere/busca em collection PRIVADA sem precisar de
# nenhuma chave OpenAI, e nunca mistura resultado com conteúdo tageado de
# outro provedor (mesmo com vetores idênticos aqui — o mock não diferencia
# semanticamente os provedores, então só o FILTRO de embedding_provider
# pode estar impedindo o vazamento).


@pytest.fixture
async def qdrant_memoria_privada():
    from app.rag.collections import ensure_collections

    client = AsyncQdrantClient(location=":memory:")
    await ensure_collections(client)
    return client


@pytest.fixture
async def usuario_com_byok_gemini():
    async with AsyncSessionLocal() as db:
        tenant = Tenant(name="Tenant Gemini 260", slug=f"teste-260-gemini-{uuid.uuid4().hex[:8]}")
        db.add(tenant)
        await db.flush()
        user = User(
            email=f"user-260-gemini-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x",
            full_name="Usuario Gemini 260", role="ADVOGADO", tenant_id=tenant.id,
        )
        db.add(user)
        await db.flush()
        cfg = AIProviderConfig(
            user_id=user.id, provider="gemini", model="gemini-embedding-001",
            display_name="Minha IA — Gemini",
            credentials_enc=encrypt(json.dumps({"api_key": "gm-byok-fase260"})),
            enabled=True, is_default=True,
        )
        db.add(cfg)
        await db.commit()
        ids = {"tenant": tenant.id, "user": user.id}
    yield ids
    async with AsyncSessionLocal() as db:
        await db.execute(AIProviderConfig.__table__.delete().where(AIProviderConfig.user_id == ids["user"]))
        await db.execute(User.__table__.delete().where(User.id == ids["user"]))
        await db.execute(Tenant.__table__.delete().where(Tenant.id == ids["tenant"]))
        await db.commit()


async def test_rag_gemini_byok_ingere_e_busca_sem_chave_openai_nenhuma(
    usuario_com_byok_gemini, qdrant_memoria_privada, monkeypatch,
):
    """Critério de aceite central desta fase: cliente configurado com
    Gemini consegue usar a Pesquisa Jurídica (ingestão + busca numa
    collection privada) sem cadastrar nenhuma chave OpenAI, central ou
    BYOK."""
    monkeypatch.setattr(emb_mod, "AsyncOpenAI", _FakeAsyncOpenAI)
    emb_mod._client = None
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")

    async def _fake_get_qdrant():
        return qdrant_memoria_privada

    import app.db.qdrant as qdrant_mod
    monkeypatch.setattr(qdrant_mod, "get_qdrant", _fake_get_qdrant)
    import app.rag.ingestion as ingestion_mod
    monkeypatch.setattr(ingestion_mod, "get_qdrant", _fake_get_qdrant)

    cu = _CurrentUser(usuario_com_byok_gemini["tenant"], usuario_com_byok_gemini["user"])

    # Seed: conteúdo legado tageado "openai" (simula ponto já indexado por
    # outro tenant/época) no MESMO vetor — só o filtro de embedding_provider
    # deveria impedir esse ponto de aparecer na busca do tenant Gemini.
    await qdrant_memoria_privada.upsert(
        collection_name="peticoes_afj",
        points=[PointStruct(
            id=str(uuid.uuid4()), vector=[0.0105] * settings.EMBEDDING_DIMENSIONS,
            payload={
                "text": "peticao de outro tenant, tageada openai",
                "tenant_id": str(usuario_com_byok_gemini["tenant"]),
                "embedding_provider": "openai",
            },
        )],
    )

    async with AsyncSessionLocal() as db:
        ingest_req = rag_mod.IngestRequest(
            content="Peticao inicial sobre rescisao contratual, ingerida via BYOK Gemini.",
            collection="peticoes_afj",
            metadata={"tipo": "inicial"},
        )
        resultado_ingest = await rag_mod.rag_ingest(ingest_req, db=db, current_user=cu)
    assert resultado_ingest["chunks_created"] == 1
    assert _FakeEmbeddingsAPI.last_construct_key == "gm-byok-fase260"

    async with AsyncSessionLocal() as db:
        search_req = rag_mod.SearchRequest(
            query="rescisao contratual", collections=["peticoes_afj"], k=5, score_threshold=0.0,
        )
        resposta = await rag_mod.rag_search(search_req, db=db, current_user=cu)

    # Só o ponto gemini deve aparecer — o legado "openai" fica de fora,
    # mesmo tendo o vetor idêntico (prova de que é o FILTRO de provider,
    # não a distância do vetor, que decide).
    assert resposta["count"] == 1
    assert resposta["results"][0]["metadata"]["embedding_provider"] == "gemini"
    assert "BYOK Gemini" in resposta["results"][0]["content"]
