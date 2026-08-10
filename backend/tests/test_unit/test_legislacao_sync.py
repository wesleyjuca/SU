"""Fase 167 — mesmo padrão de proteção do `SyncRun` aplicado a
`jurisprudencia_sync.py`: uma exceção fora do try/except por-norma (ex.: no
próprio dedup check via `db.execute`) precisa finalizar o run como ERRO com
stats parciais, não deixá-lo preso em RUNNING."""
import pytest


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _RaiseNoExecute:
    def __init__(self, exc):
        self.exc = exc


class _FakeDB:
    def __init__(self, queue):
        self._queue = list(queue)
        self.commits = 0

    async def execute(self, query):
        item = self._queue.pop(0)
        if isinstance(item, _RaiseNoExecute):
            raise item.exc
        return item

    def add(self, obj):
        pass

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_excecao_no_dedup_check_finaliza_run_como_erro_e_relanca(monkeypatch):
    import app.workers.tasks.legislacao_sync as mod

    chamadas_finalizar = []

    async def _fake_iniciar_sync(db, tenant_id, fonte, tipo):
        return object()

    async def _fake_finalizar_sync(db, run, status, stats):
        chamadas_finalizar.append((status, stats))

    monkeypatch.setattr("app.services.movements_import.iniciar_sync", _fake_iniciar_sync)
    monkeypatch.setattr("app.services.movements_import.finalizar_sync", _fake_finalizar_sync)

    async def _fake_buscar_lote():
        return [
            {"urn": "urn:lex:1", "titulo": "Lei 1", "tipo_norma": "Lei", "url": "http://x/1"},
            {"urn": "urn:lex:2", "titulo": "Lei 2", "tipo_norma": "Lei", "url": "http://x/2"},
            {"urn": "urn:lex:3", "titulo": "Lei 3", "tipo_norma": "Lei", "url": "http://x/3"},
        ]

    monkeypatch.setattr("app.integrations.lexml.client.buscar_lote_legislacao_federal", _fake_buscar_lote)

    async def _fake_buscar_norma_completa(registro):
        return {"texto": "texto da norma", "titulo": registro["titulo"], "tipo_norma": registro["tipo_norma"]}

    monkeypatch.setattr("app.integrations.lexml.client.buscar_norma_completa", _fake_buscar_norma_completa)

    async def _fake_ingest(**kwargs):
        return None

    monkeypatch.setattr("app.rag.ingestion.ingest_document", _fake_ingest)

    # 1º dedup (urn:lex:1) -> não existe, processa; 2º dedup (urn:lex:2) -> a
    # query em si falha (DB caiu no meio do loop) -- esse é o caso que o
    # try/except NOVO em volta do loop cobre (não o try/except por-norma,
    # que só protege a chamada de busca+ingest de CADA item já dentro do
    # loop, não a query de dedup em si).
    db = _FakeDB([
        _FakeScalarResult(None),
        _RaiseNoExecute(RuntimeError("DB caiu no meio do loop")),
    ])

    with pytest.raises(RuntimeError, match="DB caiu no meio do loop"):
        await mod.executar_sync_legislacao(db)

    assert len(chamadas_finalizar) == 1
    status, stats = chamadas_finalizar[0]
    assert status == "ERRO"
    assert stats["processados"] == 1  # urn:lex:1 já tinha processado antes da falha
    assert "erro" in stats


@pytest.mark.asyncio
async def test_caminho_feliz_finaliza_ok(monkeypatch):
    import app.workers.tasks.legislacao_sync as mod

    chamadas_finalizar = []

    async def _fake_iniciar_sync(db, tenant_id, fonte, tipo):
        return object()

    async def _fake_finalizar_sync(db, run, status, stats):
        chamadas_finalizar.append((status, stats))

    monkeypatch.setattr("app.services.movements_import.iniciar_sync", _fake_iniciar_sync)
    monkeypatch.setattr("app.services.movements_import.finalizar_sync", _fake_finalizar_sync)

    async def _fake_buscar_lote():
        return [{"urn": "urn:lex:1", "titulo": "Lei 1", "tipo_norma": "Lei", "url": "http://x/1"}]

    monkeypatch.setattr("app.integrations.lexml.client.buscar_lote_legislacao_federal", _fake_buscar_lote)

    async def _fake_buscar_norma_completa(registro):
        return {"texto": "texto", "titulo": registro["titulo"], "tipo_norma": registro["tipo_norma"]}

    monkeypatch.setattr("app.integrations.lexml.client.buscar_norma_completa", _fake_buscar_norma_completa)

    async def _fake_ingest(**kwargs):
        return None

    monkeypatch.setattr("app.rag.ingestion.ingest_document", _fake_ingest)

    db = _FakeDB([_FakeScalarResult(None)])
    resultado = await mod.executar_sync_legislacao(db)

    assert resultado["processados"] == 1
    assert chamadas_finalizar[0][0] == "OK"
