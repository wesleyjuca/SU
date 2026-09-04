"""Fase 188.1 — achado pendente da Fase 186: `executar_sync_drive_doutrina`
reprocessa arquivos `FALHOU` (fix da Fase 185), mas nunca chamava
`delete_document_chunks()` antes de re-ingerir, e `ingest_document()` usa
`uuid4()` como point ID (não determinístico) — reingerir duplicava chunks
órfãos no Qdrant, sem rota de limpeza. Usa `AsyncQdrantClient(location=":memory:")`
(motor real, não um Fake escrito à mão) — mesmo padrão do
`test_rag_retrieval_real_qdrant.py` da Fase 187 — pra provar que o fix
(`delete_document_chunks` antes de `ingest_document` no branch de
reprocessamento) realmente evita a duplicação, e não só que a função foi
chamada."""
import uuid

import pytest
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams

from app.config import settings

pytestmark = pytest.mark.asyncio


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, queue):
        self._queue = list(queue)

    async def execute(self, query):
        return self._queue.pop(0)

    def add(self, obj):
        pass

    async def flush(self):
        pass

    async def rollback(self):
        pass

    async def commit(self):
        pass


class _FakeInteg:
    def __init__(self, tenant_id, folder_id):
        self.tenant_id = tenant_id
        self.extra_data = {"folder_id": folder_id}


class _FakeCfg:
    def __init__(self):
        self.modules_enabled = {"google_drive_doutrina": True}


class _FakeEntradaFalhou:
    """Simula uma JurisprudenciaIngerida FALHOU que já tinha subido chunks
    no Qdrant antes de falhar (ex.: upsert ok, commit seguinte não) — o
    cenário real do achado 4b da Fase 186."""
    def __init__(self):
        self.status = "FALHOU"
        self.erro = "timeout transiente"
        self.metadata_extraida = {"nome_arquivo": "doutrina.pdf", "google_file_id": "f1"}
        self.processed_at = None


@pytest.fixture
async def qdrant_memoria():
    client = AsyncQdrantClient(location=":memory:")
    await client.create_collection(
        collection_name="doutrina_privada",
        vectors_config=VectorParams(size=settings.EMBEDDING_DIMENSIONS, distance=Distance.COSINE),
    )
    return client


async def test_reprocessar_arquivo_falhou_nao_duplica_chunks_no_qdrant(qdrant_memoria, monkeypatch):
    """Sem o fix (delete_document_chunks antes de ingest_document), este
    teste falharia: 2 execuções de `ingest_document` pro mesmo
    `document_id` (1ª que "falhou" depois do upsert, 2ª no reprocessamento)
    resultariam em pontos duplicados no Qdrant (uuid4() nunca colide)."""
    import app.workers.tasks.google_drive_sync as mod
    import app.rag.ingestion as ingestion_mod

    async def _fake_get_qdrant():
        return qdrant_memoria

    async def _fake_embed_batch(texts):
        return [[0.01] * settings.EMBEDDING_DIMENSIONS for _ in texts]

    monkeypatch.setattr(ingestion_mod, "get_qdrant", _fake_get_qdrant)
    monkeypatch.setattr(ingestion_mod, "embed_batch", _fake_embed_batch)

    # Simula o estado "já ingerido uma vez antes de FALHOU" — chunks já
    # existem no Qdrant pro mesmo document_id antes da reconciliação.
    await ingestion_mod.ingest_document(
        content="Art. 1º Esta é a doutrina sobre o tema X, com texto suficiente para gerar ao menos um chunk.",
        collection="doutrina_privada",
        metadata={"nome_arquivo": "doutrina.pdf"},
        document_id="f1",
    )
    pontos_antes = (await qdrant_memoria.scroll(collection_name="doutrina_privada", limit=100))[0]
    assert len(pontos_antes) >= 1

    tenant = uuid.uuid4()
    integ = _FakeInteg(tenant, "folder_x")

    async def _fake_iniciar_sync(db, tenant_id, fonte, tipo):
        return type("Run", (), {"tenant_id": tenant_id})()

    async def _fake_finalizar_sync(db, run, status, stats):
        pass

    monkeypatch.setattr("app.services.movements_import.iniciar_sync", _fake_iniciar_sync)
    monkeypatch.setattr("app.services.movements_import.finalizar_sync", _fake_finalizar_sync)

    async def _fake_get_credentials(db, tenant_id, provider):
        return {"access_token": "tok"}

    monkeypatch.setattr("app.services.integration_hub.get_credentials", _fake_get_credentials)

    async def _fake_listar_arquivos(access_token, folder_id):
        return [{"id": "f1", "name": "doutrina.pdf", "mimeType": "application/pdf"}]

    async def _fake_baixar_conteudo(access_token, file_id, mime_type):
        return b"bytes"

    async def _fake_extrair_texto(mimetype, conteudo):
        return "Art. 1º Esta é a doutrina sobre o tema X, com texto suficiente para gerar ao menos um chunk."

    monkeypatch.setattr("app.integrations.google_drive.client.listar_arquivos", _fake_listar_arquivos)
    monkeypatch.setattr("app.integrations.google_drive.client.baixar_conteudo", _fake_baixar_conteudo)
    monkeypatch.setattr("app.integrations.google_drive.client.extrair_texto", _fake_extrair_texto)

    entrada_falhou = _FakeEntradaFalhou()
    db = _FakeDB([
        _FakeScalarsResult([integ]),
        _FakeScalarResult(_FakeCfg()),
        _FakeScalarResult(entrada_falhou),  # dedup: já existe, status FALHOU -> reprocessa
    ])

    resultado = await mod.executar_sync_drive_doutrina(db)

    assert resultado["processados"] == 1
    assert entrada_falhou.status == "EMBEDDED"

    pontos_depois = (await qdrant_memoria.scroll(collection_name="doutrina_privada", limit=100))[0]
    assert len(pontos_depois) == len(pontos_antes), (
        "reprocessar um arquivo FALHOU duplicou chunks no Qdrant — "
        "delete_document_chunks() não foi chamado (ou não funcionou) antes do re-ingest"
    )
