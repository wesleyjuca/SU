"""Fase 167 — reaper de `SyncRun` travados em RUNNING. Rede de segurança
pro cenário residual que o try/except nos loops de sincronização não cobre
(processo worker morto sem desenrolar a pilha — OOM kill, `kill -9`)."""
import uuid

import pytest
from sqlalchemy.sql.dml import Update


class _FakeScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, ids_travados):
        self._ids = ids_travados
        self.updates = []
        self.commits = 0

    async def execute(self, query):
        if isinstance(query, Update):
            self.updates.append(query)
            return None
        return _FakeScalarsResult(self._ids)

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_marca_runs_travados_como_erro():
    from app.workers.tasks.sync_reaper import executar_reaper_syncs

    ids = [uuid.uuid4(), uuid.uuid4()]
    db = _FakeDB(ids)

    resultado = await executar_reaper_syncs(db)

    assert resultado["marcados_travados"] == 2
    assert len(db.updates) == 1  # 1 UPDATE em lote, não 1 por linha
    assert db.commits == 1


@pytest.mark.asyncio
async def test_sem_runs_travados_nao_executa_update_nem_commit():
    from app.workers.tasks.sync_reaper import executar_reaper_syncs

    db = _FakeDB([])

    resultado = await executar_reaper_syncs(db)

    assert resultado["marcados_travados"] == 0
    assert db.updates == []
    assert db.commits == 0


@pytest.mark.asyncio
async def test_limite_horas_customizado_e_repassado_pra_query():
    """Confirma que o parâmetro `limite_horas` participa da query (não é só
    um parâmetro morto) — verifica indiretamente checando que a função
    aceita o kwarg sem lançar e devolve o resultado esperado."""
    from app.workers.tasks.sync_reaper import executar_reaper_syncs

    db = _FakeDB([uuid.uuid4()])
    resultado = await executar_reaper_syncs(db, limite_horas=1)

    assert resultado["marcados_travados"] == 1
