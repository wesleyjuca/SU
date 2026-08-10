"""Fase 167 — `SyncRun` não pode ficar preso em RUNNING pra sempre se uma
exceção não prevista acontecer no MEIO do loop de sincronização (fora do
try/except por-documento já existente). Testa que `executar_sync_stj`
finaliza o run como ERRO (com stats parciais) e re-lança, em vez de deixar
a exceção escapar sem tocar o SyncRun."""
import pytest


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    def __init__(self):
        self.commits = 0

    async def execute(self, query):
        return _FakeScalarResult(None)  # nunca existe -- sempre processa

    def add(self, obj):
        pass

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_excecao_fora_do_try_interno_finaliza_run_como_erro_e_relanca(monkeypatch):
    import app.workers.tasks.jurisprudencia_sync as mod

    chamadas_finalizar = []

    async def _fake_iniciar_sync(db, tenant_id, fonte, tipo):
        return object()

    async def _fake_finalizar_sync(db, run, status, stats):
        chamadas_finalizar.append((status, stats))

    monkeypatch.setattr("app.services.movements_import.iniciar_sync", _fake_iniciar_sync)
    monkeypatch.setattr("app.services.movements_import.finalizar_sync", _fake_finalizar_sync)

    async def _fake_buscar_lote_recente():
        return [
            {"fonte_documento_id": "doc1", "texto": "texto 1"},
            {"fonte_documento_id": "doc2", "texto": "texto 2"},
            {"fonte_documento_id": "doc3", "texto": "texto 3"},
        ]

    monkeypatch.setattr("app.integrations.jurisprudencia.stj_client.buscar_lote_recente", _fake_buscar_lote_recente)

    chamada = {"n": 0}

    async def _fake_classificar(texto):
        # classificar_acordao roda FORA do try interno de ingest -- uma
        # falha aqui não é protegida pelo except por-documento existente,
        # é exatamente o caso que o try/except NOVO em volta do loop cobre.
        chamada["n"] += 1
        if chamada["n"] == 2:
            raise RuntimeError("falha simulada fora do try interno")
        return None

    monkeypatch.setattr(mod, "classificar_acordao", _fake_classificar)

    async def _fake_ingest(**kwargs):
        return None

    monkeypatch.setattr("app.rag.ingestion.ingest_document", _fake_ingest)

    db = _FakeDB()
    with pytest.raises(RuntimeError, match="falha simulada"):
        await mod.executar_sync_stj(db)

    assert len(chamadas_finalizar) == 1
    status, stats = chamadas_finalizar[0]
    assert status == "ERRO"
    assert stats["processados"] == 1  # doc1 já tinha sido processado antes da falha
    assert "erro" in stats


@pytest.mark.asyncio
async def test_caminho_feliz_finaliza_ok_sem_excecao(monkeypatch):
    import app.workers.tasks.jurisprudencia_sync as mod

    chamadas_finalizar = []

    async def _fake_iniciar_sync(db, tenant_id, fonte, tipo):
        return object()

    async def _fake_finalizar_sync(db, run, status, stats):
        chamadas_finalizar.append((status, stats))

    monkeypatch.setattr("app.services.movements_import.iniciar_sync", _fake_iniciar_sync)
    monkeypatch.setattr("app.services.movements_import.finalizar_sync", _fake_finalizar_sync)

    async def _fake_buscar_lote_recente():
        return [{"fonte_documento_id": "doc1", "texto": "texto 1"}]

    monkeypatch.setattr("app.integrations.jurisprudencia.stj_client.buscar_lote_recente", _fake_buscar_lote_recente)

    async def _fake_classificar(texto):
        return None

    monkeypatch.setattr(mod, "classificar_acordao", _fake_classificar)

    async def _fake_ingest(**kwargs):
        return None

    monkeypatch.setattr("app.rag.ingestion.ingest_document", _fake_ingest)

    db = _FakeDB()
    resultado = await mod.executar_sync_stj(db)

    assert resultado["processados"] == 1
    assert len(chamadas_finalizar) == 1
    assert chamadas_finalizar[0][0] == "OK"
