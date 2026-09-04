"""Fase 188.2 — achado pendente da Fase 186: a tela de Integrações não
mostrava nenhum resultado da sincronização de doutrina do Google Drive
(processados/pulados/falhas/erro), mesmo já registrado em `SyncRun`.
`GET /integrations/hub/google_drive_doutrina/last-sync` devolve o último
`SyncRun` cuja `fonte` é `google_drive:{tenant_id}` (mesmo formato gravado
por `google_drive_sync.py::executar_sync_drive_doutrina`).

Achado real (validação da pasta Doutrina): um `SyncRun` pode ficar preso em
RUNNING pra sempre (crash de processo no meio da sincronização) — os testes
`test_running_recente_nao_e_sinalizado_como_travada`/
`test_running_antigo_e_sinalizado_como_provavelmente_travada` cobrem o
campo `provavelmente_travada` que sinaliza esse caso pra UI, sem tentar
corrigir/reabrir sozinho."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.api.v1.integrations_hub import hub_drive_doutrina_last_sync


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    def __init__(self, value):
        self._value = value
        self.last_query = None

    async def execute(self, query):
        self.last_query = query
        return _FakeScalarResult(self._value)


class _FakeUser:
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id


class _FakeSyncRun:
    def __init__(self, status, stats, started_at, finished_at):
        self.status = status
        self.stats = stats
        self.started_at = started_at
        self.finished_at = finished_at


@pytest.mark.asyncio
async def test_sem_sincronizacao_ainda_devolve_none():
    db = _FakeDB(None)
    result = await hub_drive_doutrina_last_sync(current_user=_FakeUser(uuid.uuid4()), db=db)
    assert result == {"ultima_sincronizacao": None}


@pytest.mark.asyncio
async def test_sincronizacao_ok_expoe_stats():
    now = datetime.now(timezone.utc)
    run = _FakeSyncRun("OK", {"processados": 3, "pulados": 1, "falhas": 0}, now, now)
    db = _FakeDB(run)
    result = await hub_drive_doutrina_last_sync(current_user=_FakeUser(uuid.uuid4()), db=db)

    assert result["ultima_sincronizacao"]["status"] == "OK"
    assert result["ultima_sincronizacao"]["stats"] == {"processados": 3, "pulados": 1, "falhas": 0}
    assert result["ultima_sincronizacao"]["started_at"] is not None


@pytest.mark.asyncio
async def test_sincronizacao_com_erro_expoe_motivo():
    now = datetime.now(timezone.utc)
    run = _FakeSyncRun("ERRO", {"processados": 0, "pulados": 0, "falhas": 0, "erro": "falha ao listar a pasta"}, now, now)
    db = _FakeDB(run)
    result = await hub_drive_doutrina_last_sync(current_user=_FakeUser(uuid.uuid4()), db=db)

    assert result["ultima_sincronizacao"]["status"] == "ERRO"
    assert result["ultima_sincronizacao"]["stats"]["erro"] == "falha ao listar a pasta"


@pytest.mark.asyncio
async def test_running_recente_nao_e_sinalizado_como_travada():
    started_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    run = _FakeSyncRun("RUNNING", {}, started_at, None)
    db = _FakeDB(run)
    result = await hub_drive_doutrina_last_sync(current_user=_FakeUser(uuid.uuid4()), db=db)

    assert result["ultima_sincronizacao"]["status"] == "RUNNING"
    assert result["ultima_sincronizacao"]["provavelmente_travada"] is False


@pytest.mark.asyncio
async def test_running_antigo_e_sinalizado_como_provavelmente_travada():
    """Achado real: um SyncRun preso em RUNNING há muito tempo (crash de
    processo no meio da sync) nunca era sinalizado — a tela mostrava "em
    andamento" indefinidamente. 30min é folga generosa acima do tempo real
    de uma sincronização síncrona via HTTP."""
    started_at = datetime.now(timezone.utc) - timedelta(minutes=45)
    run = _FakeSyncRun("RUNNING", {}, started_at, None)
    db = _FakeDB(run)
    result = await hub_drive_doutrina_last_sync(current_user=_FakeUser(uuid.uuid4()), db=db)

    assert result["ultima_sincronizacao"]["status"] == "RUNNING"
    assert result["ultima_sincronizacao"]["provavelmente_travada"] is True


@pytest.mark.asyncio
async def test_ok_ou_erro_nunca_e_sinalizado_como_travada_mesmo_antigo():
    started_at = datetime.now(timezone.utc) - timedelta(hours=5)
    run = _FakeSyncRun("OK", {"processados": 3, "pulados": 0, "falhas": 0}, started_at, started_at)
    db = _FakeDB(run)
    result = await hub_drive_doutrina_last_sync(current_user=_FakeUser(uuid.uuid4()), db=db)

    assert result["ultima_sincronizacao"]["provavelmente_travada"] is False


@pytest.mark.asyncio
async def test_started_at_naive_nao_quebra_o_calculo():
    """`started_at` sem timezone (possível dependendo de como o driver
    devolve o timestamp) não deve lançar TypeError ao comparar com
    datetime.now(timezone.utc)."""
    started_at_naive = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=45)
    run = _FakeSyncRun("RUNNING", {}, started_at_naive, None)
    db = _FakeDB(run)
    result = await hub_drive_doutrina_last_sync(current_user=_FakeUser(uuid.uuid4()), db=db)

    assert result["ultima_sincronizacao"]["provavelmente_travada"] is True
