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


class _FakeScalarsResult:
    """Resultado no formato que o backfill consome (`.scalars().all()`)."""

    def __init__(self, linhas):
        self._linhas = list(linhas)

    def scalars(self):
        return self

    def all(self):
        return self._linhas


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
        _FakeScalarsResult([]),  # query do backfill (roda antes do loop)
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

    db = _FakeDB([_FakeScalarsResult([]), _FakeScalarResult(None)])
    resultado = await mod.executar_sync_legislacao(db)

    assert resultado["processados"] == 1
    assert chamadas_finalizar[0][0] == "OK"


# ─── Fase pós-266.2 — o acervo LexML precisa ser alimentado aqui ─────────────
#
# Sem esta chamada o acervo estruturado nasce vazio e assim fica: o
# `upsert_norma` do loop só é alcançado no ramo de URN NOVA, e toda norma já
# ingerida cai no `continue` antes dele. Como a pipeline roda diariamente há
# muito tempo, "já ingerida" é praticamente o acervo inteiro — a busca de
# legislação devolvia zero mesmo com o portal funcionando.

async def _preparar_sync_sem_normas(monkeypatch):
    """Sincronização que não tem nenhuma norma para processar: isola o
    backfill como única coisa sob teste."""
    chamadas_finalizar = []

    async def _fake_iniciar_sync(db, tenant_id, fonte, tipo):
        return object()

    async def _fake_finalizar_sync(db, run, status, stats):
        chamadas_finalizar.append((status, stats))

    async def _fake_buscar_lote():
        return []

    monkeypatch.setattr("app.services.movements_import.iniciar_sync", _fake_iniciar_sync)
    monkeypatch.setattr("app.services.movements_import.finalizar_sync", _fake_finalizar_sync)
    monkeypatch.setattr("app.integrations.lexml.client.buscar_lote_legislacao_federal", _fake_buscar_lote)
    return chamadas_finalizar


@pytest.mark.asyncio
async def test_backfill_do_acervo_lexml_roda_na_sincronizacao(monkeypatch):
    import app.workers.tasks.legislacao_sync as mod

    chamadas_finalizar = await _preparar_sync_sem_normas(monkeypatch)

    db = _FakeDB([_FakeScalarsResult([])])  # a query do backfill, e só ela
    resultado = await mod.executar_sync_legislacao(db)

    assert db._queue == [], "o backfill não chegou a consultar o banco"
    assert chamadas_finalizar[0][0] == "OK"
    assert resultado["processados"] == 0


@pytest.mark.asyncio
async def test_backfill_que_falha_nao_derruba_a_sincronizacao(monkeypatch):
    """A falha é injetada na dependência de DENTRO do backfill (a própria
    query), não trocando a função inteira por um fake que levanta — senão o
    teste passaria com a correção revertida, porque o código real nunca
    rodaria. Armadilha já catalogada no CLAUDE.md."""
    import app.workers.tasks.legislacao_sync as mod

    chamadas_finalizar = await _preparar_sync_sem_normas(monkeypatch)

    db = _FakeDB([_RaiseNoExecute(RuntimeError("banco fora no backfill"))])
    resultado = await mod.executar_sync_legislacao(db)

    assert chamadas_finalizar[0][0] == "OK", "backfill falho não pode derrubar a sincronização"
    assert resultado["processados"] == 0
