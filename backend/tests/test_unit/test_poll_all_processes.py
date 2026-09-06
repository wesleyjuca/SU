"""`poll_all_processes` — a tarefa de maior volume de escrita automática.

Roda de 30 em 30 minutos e escreve em 4 tabelas (`ProcessMovement`,
`LegalProcess`, `Notification`, `SyncRun`). Estava com cobertura zero.

Além de fixar o caminho feliz, estes testes provam as três correções desta
fase — em todas, uma FALHA aparecia como SUCESSO:

  (a) exceção na montagem do lote sumia sem `SyncRun` e sem acionar o retry
      da task, porque `BaseAgent.run` converte exceção em `AgentResult(FAILED)`
      e a task só lia `result.output`;
  (b) DataJud fora do ar devolvia `[]` — indistinguível de "sem novidades" —
      e o ciclo saía `status="OK", errors=0`;
  (c) falha ao persistir movimentação era engolida e o processo ainda contava
      como polled com sucesso.

Cada teste correspondente falha se a correção for revertida.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select

import app.agents.process.process_agent as mod
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext
from app.agents.process.process_agent import ProcessAgent
from app.models.sync_run import SyncRun
from app.models.tenant import Tenant
from tests.db_isolada import sessao_isolada


class _Contagem:
    def __init__(self, valor):
        self._valor = valor

    def scalar(self):
        return self._valor


class _Linhas:
    def __init__(self, linhas):
        self._linhas = linhas

    def scalars(self):
        return self

    def all(self):
        return self._linhas


class _Explode:
    """Sentinela: em vez de devolver resultado, levanta (mesmo padrão de
    `test_google_drive_sync.py`)."""

    def __init__(self, exc):
        self.exc = exc


class _FakeDB:
    """Consome uma fila de resultados, um por `execute()`."""

    def __init__(self, fila):
        self._fila = list(fila)
        self.commits = 0

    async def execute(self, *_args, **_kwargs):
        item = self._fila.pop(0)
        if isinstance(item, _Explode):
            raise item.exc
        return item

    def add(self, _obj):
        pass

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass

    async def close(self):
        pass


class _ProcessoFalso:
    def __init__(self, tenant_id):
        self.id = uuid.uuid4()
        self.tenant_id = tenant_id
        self.numero_cnj = f"{uuid.uuid4().int % 10**7:07d}-11.2026.8.26.0100"
        self.tribunal = "TJSP"


class _FonteFalsa:
    """Substitui a `DataJudFonte`. `movimentos=None` simula fonte indisponível
    (é o que `sinalizar_falha=True` devolve quando a consulta não acontece)."""

    def __init__(self, movimentos):
        self._movimentos = movimentos
        self.chamadas = 0

    async def fetch_movements_datajud(self, numero_cnj, tribunal=None, since=None, *, sinalizar_falha=False):
        self.chamadas += 1
        return self._movimentos


def _montar_lote(monkeypatch, processos, fonte, fila_extra=None):
    """Prepara o `ProcessAgent` para um ciclo: a fila do banco responde à
    contagem de tenants e à busca dos processos, nessa ordem."""
    tenants = {p.tenant_id for p in processos}
    fila = [_Contagem(len(tenants) or 1), _Linhas(processos)] + list(fila_extra or [])
    monkeypatch.setattr(mod, "obter_fonte", lambda _nome: fonte, raising=False)
    import app.integrations.fontes.registry as registry
    monkeypatch.setattr(registry, "obter_fonte", lambda _nome: fonte)
    return ProcessAgent(db=_FakeDB(fila))


async def _sync_runs_desde(inicio):
    async with sessao_isolada() as db:
        linhas = (await db.execute(
            select(SyncRun).where(
                SyncRun.tipo == "POLLING",
                SyncRun.fonte == "datajud",
                SyncRun.started_at >= inicio,
            )
        )).scalars().all()
        return [
            {"tenant_id": s.tenant_id, "status": s.status, "stats": dict(s.stats or {})}
            for s in linhas
        ]


async def _limpar_sync_runs(inicio):
    async with sessao_isolada() as db:
        await db.execute(delete(SyncRun).where(
            SyncRun.tipo == "POLLING", SyncRun.fonte == "datajud", SyncRun.started_at >= inicio,
        ))
        await db.commit()


@pytest.fixture
async def marco_temporal():
    """Instante-âncora para achar (e depois apagar) só os `SyncRun` do teste."""
    inicio = datetime.now(timezone.utc) - timedelta(seconds=1)
    yield inicio
    await _limpar_sync_runs(inicio)


@pytest.fixture
async def tenants_reais():
    """Dois tenants que EXISTEM no banco.

    `sync_runs.tenant_id` tem FK para `tenants.id`: inventar UUID aqui faria o
    bloco de fechamento estourar `ForeignKeyViolationError` — e, como ele é
    fail-soft (só loga warning), o teste passaria a não ver `SyncRun` nenhum e
    a acusar a ausência como se fosse bug do código. É a mesma armadilha de FK
    fabricada já corrigida em outros testes deste projeto."""
    async with sessao_isolada() as db:
        a = Tenant(name="Polling A", slug=f"poll-a-{uuid.uuid4().hex[:8]}")
        b = Tenant(name="Polling B", slug=f"poll-b-{uuid.uuid4().hex[:8]}")
        db.add_all([a, b])
        await db.commit()
        ids = (a.id, b.id)
    yield ids
    async with sessao_isolada() as db:
        await db.execute(delete(Tenant).where(Tenant.id.in_(list(ids))))
        await db.commit()


async def test_ciclo_feliz_grava_syncrun_agregado_mais_um_por_tenant(monkeypatch, marco_temporal, tenants_reais):
    """O agregado (`tenant_id=None`) alimenta o painel Cérebro; os por tenant
    alimentam `GET /system/health/tenant-infra`, que filtra por tenant exato.
    Perder qualquer um dos dois deixa uma das telas cega."""
    tenant_a, tenant_b = tenants_reais
    processos = [_ProcessoFalso(tenant_a), _ProcessoFalso(tenant_a), _ProcessoFalso(tenant_b)]
    agente = _montar_lote(monkeypatch, processos, _FonteFalsa(movimentos=[]))

    res = await agente._poll_all_active(AgentContext(task_type="poll_all"))

    assert res.status == AgentStatus.SUCCESS
    assert res.output["total_processos"] == 3
    assert res.output["polled_ok"] == 3
    assert res.output["errors"] == 0
    assert res.output["fonte_indisponivel"] == 0

    runs = await _sync_runs_desde(marco_temporal)
    agregados = [r for r in runs if r["tenant_id"] is None]
    por_tenant = {r["tenant_id"]: r for r in runs if r["tenant_id"] is not None}
    assert len(agregados) == 1 and agregados[0]["status"] == "OK"
    assert set(por_tenant) == {tenant_a, tenant_b}
    assert por_tenant[tenant_a]["stats"]["total_processos"] == 2
    assert por_tenant[tenant_b]["stats"]["total_processos"] == 1
    assert all(r["status"] == "OK" for r in por_tenant.values())


async def test_fonte_indisponivel_nao_e_confundida_com_ausencia_de_novidade(monkeypatch, marco_temporal, tenants_reais):
    """PROVA DA CORREÇÃO (b).

    Com o DataJud fora do ar, o breaker devolvia `[]` e o ciclo inteiro saía
    `status="OK", errors=0` — um ciclo em que NENHUMA consulta aconteceu era
    indistinguível de um ciclo tranquilo. Agora conta como erro e ainda
    registra separadamente quantos foram por indisponibilidade da fonte."""
    tenant = tenants_reais[0]
    processos = [_ProcessoFalso(tenant), _ProcessoFalso(tenant)]
    agente = _montar_lote(monkeypatch, processos, _FonteFalsa(movimentos=None))

    res = await agente._poll_all_active(AgentContext(task_type="poll_all"))

    assert res.output["polled_ok"] == 0
    assert res.output["errors"] == 2
    assert res.output["fonte_indisponivel"] == 2

    runs = await _sync_runs_desde(marco_temporal)
    assert all(r["status"] == "ERRO" for r in runs), runs
    agregado = next(r for r in runs if r["tenant_id"] is None)
    assert agregado["stats"]["fonte_indisponivel"] == 2


async def test_falha_ao_persistir_conta_como_erro_e_nao_como_sucesso(monkeypatch, marco_temporal, tenants_reais):
    """PROVA DA CORREÇÃO (c).

    `_save_movements` capturava toda exceção, devolvia `novos = 0` e o
    processo ainda entrava em `polled_ok` — andamento perdido sem nenhum
    sinal. Agora propaga e o loop do lote contabiliza como erro, seguindo
    para o próximo processo (o isolamento por processo é preservado)."""
    tenant = tenants_reais[0]
    processos = [_ProcessoFalso(tenant), _ProcessoFalso(tenant)]

    class _MovimentoFalso:
        data = datetime.now(timezone.utc)
        descricao = "Juntada de petição"
        tipo = "ANDAMENTO"
        documento_url = None
        raw_data = None

    # O `_save_movements` REAL precisa rodar: substituí-lo por um fake que
    # levanta não provaria nada — a correção está DENTRO dele (antes o
    # `except` engolia e devolvia `novos = 0`). Então a falha é injetada no
    # `importar_movimentos`, que ele chama.
    class _Achou:
        def __init__(self, proc):
            self._proc = proc

        def scalar_one_or_none(self):
            return self._proc

    fila_extra = [_Achou(processos[0]), _Achou(processos[1])]
    agente = _montar_lote(
        monkeypatch, processos, _FonteFalsa(movimentos=[_MovimentoFalso()]),
        fila_extra=fila_extra,
    )

    import app.services.movements_import as mi

    async def _importar_explode(*_args, **_kwargs):
        raise RuntimeError("banco fora do ar no meio da gravação")

    monkeypatch.setattr(mi, "importar_movimentos", _importar_explode)

    res = await agente._poll_all_active(AgentContext(task_type="poll_all"))

    assert res.output["polled_ok"] == 0
    assert res.output["errors"] == 2
    # Não é indisponibilidade de fonte: a consulta funcionou, a gravação é que
    # falhou. Os dois casos precisam continuar distinguíveis.
    assert res.output["fonte_indisponivel"] == 0
    runs = await _sync_runs_desde(marco_temporal)
    assert all(r["status"] == "ERRO" for r in runs)


async def test_falha_na_montagem_do_lote_deixa_rastro_e_propaga(monkeypatch, marco_temporal):
    """PROVA DA CORREÇÃO (a), parte 1.

    A query que monta o lote fica FORA do try/except do loop. Uma exceção ali
    subia direto, o bloco que grava os `SyncRun` ficava para trás e o ciclo
    sumia sem deixar nem "OK" nem "ERRO" — invisível para qualquer painel."""
    agente = ProcessAgent(db=_FakeDB([_Explode(RuntimeError("timeout na query do lote"))]))

    with pytest.raises(RuntimeError, match="timeout na query do lote"):
        await agente._poll_all_active(AgentContext(task_type="poll_all"))

    runs = await _sync_runs_desde(marco_temporal)
    assert len(runs) == 1
    assert runs[0]["status"] == "ERRO"
    assert runs[0]["tenant_id"] is None
    assert "timeout na query do lote" in runs[0]["stats"]["erro"]


async def test_um_processo_quebrado_nao_derruba_os_demais(monkeypatch, marco_temporal, tenants_reais):
    """O isolamento é POR PROCESSO (o try/except está dentro do loop), e os
    processos de tenants diferentes vêm intercalados na mesma lista — então
    uma falha no tenant A não impede o polling do tenant B. Diferente do bug
    histórico de `google_drive_sync.py`, que tinha loop aninhado por tenant."""
    tenant_a, tenant_b = tenants_reais
    proc_ruim, proc_bom = _ProcessoFalso(tenant_a), _ProcessoFalso(tenant_b)
    agente = _montar_lote(monkeypatch, [proc_ruim, proc_bom], _FonteFalsa(movimentos=[]))

    original = ProcessAgent._poll_single_process

    async def _um_falha(self, ctx, task):
        if task["process_id"] == str(proc_ruim.id):
            raise RuntimeError("explodiu neste processo")
        return await original(self, ctx, task)

    monkeypatch.setattr(ProcessAgent, "_poll_single_process", _um_falha)

    res = await agente._poll_all_active(AgentContext(task_type="poll_all"))

    assert res.output["errors"] == 1
    assert res.output["polled_ok"] == 1  # o do tenant B seguiu normalmente
    runs = await _sync_runs_desde(marco_temporal)
    por_tenant = {r["tenant_id"]: r for r in runs if r["tenant_id"] is not None}
    assert por_tenant[tenant_a]["status"] == "ERRO"
    assert por_tenant[tenant_b]["status"] == "OK"


async def test_lote_vazio_nao_grava_syncrun_por_tenant(monkeypatch, marco_temporal):
    """Sem processo monitorado, só o agregado é registrado — não se inventa
    linha por tenant que não participou do ciclo."""
    agente = _montar_lote(monkeypatch, [], _FonteFalsa(movimentos=[]))

    res = await agente._poll_all_active(AgentContext(task_type="poll_all"))

    assert res.output["total_processos"] == 0
    runs = await _sync_runs_desde(marco_temporal)
    assert len(runs) == 1 and runs[0]["tenant_id"] is None and runs[0]["status"] == "OK"


# --- a task Celery em si -----------------------------------------------------

def _preparar_task(monkeypatch, resultado_agente):
    """Isola a task: lock livre, sessão fake, agente fake e engine fake.

    O engine precisa ser fake porque `run_worker_coro` chama `engine.dispose()`
    no `finally` (`workers/async_utils.py`) — sem isso o teste derrubaria o
    pool real e contaminaria os testes seguintes (mesmo cuidado de
    `test_worker_reliability.py`)."""
    import app.db.base as dbbase
    import app.workers.task_lock as lock_mod

    class _LockLivre:
        def __init__(self, *_a, **_kw):
            pass

        async def acquire(self):
            return True

        async def release(self):
            pass

    class _SessaoFake:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

    class _AgenteFake:
        def __init__(self, db=None):
            pass

        async def run(self, _ctx):
            return resultado_agente

    class _EngineFake:
        async def dispose(self):
            pass

    monkeypatch.setattr(lock_mod, "TaskLock", _LockLivre)
    monkeypatch.setattr(dbbase, "AsyncSessionLocal", lambda: _SessaoFake())
    monkeypatch.setattr(mod, "ProcessAgent", _AgenteFake)
    monkeypatch.setattr(dbbase, "engine", _EngineFake())


def test_task_devolve_o_output_quando_o_ciclo_da_certo(monkeypatch):
    from app.workers.tasks.process_polling import poll_all_processes

    _preparar_task(monkeypatch, AgentResult(
        status=AgentStatus.SUCCESS, agent_name="process_agent",
        output={"total_processos": 7, "polled_ok": 7, "errors": 0},
    ))

    assert poll_all_processes.run()["polled_ok"] == 7


def test_task_nao_engole_falha_do_agente(monkeypatch):
    """PROVA DA CORREÇÃO (a), parte 2.

    `BaseAgent.run` nunca propaga — devolve `AgentResult(FAILED)`. A task só
    lia `result.output`, então um lote totalmente falho retornava `None` com
    sucesso aparente: o `except` não disparava, o `self.retry` nunca rodava e
    o Beat seguia como se o ciclo tivesse acontecido. Agora a falha vira
    exceção (a task converte em `retry`)."""
    from celery.exceptions import Retry

    from app.workers.tasks.process_polling import poll_all_processes

    _preparar_task(monkeypatch, AgentResult(
        status=AgentStatus.FAILED, agent_name="process_agent",
        output={}, error="timeout na query do lote",
    ))

    with pytest.raises((Retry, RuntimeError)):
        poll_all_processes.run()


def test_lock_ocupado_pula_o_ciclo_sem_rodar_o_agente(monkeypatch):
    """Duas execuções concorrentes não podem pollar em dobro — o Beat pode
    disparar de novo antes de a anterior terminar."""
    import app.db.base as dbbase
    import app.workers.task_lock as lock_mod

    from app.workers.tasks.process_polling import poll_all_processes

    rodou = {"agente": False}

    class _LockOcupado:
        def __init__(self, *_a, **_kw):
            pass

        async def acquire(self):
            return False

        async def release(self):
            rodou["release"] = True

    class _AgenteQueNaoDeveRodar:
        def __init__(self, db=None):
            rodou["agente"] = True

    class _EngineFake:
        async def dispose(self):
            pass

    monkeypatch.setattr(lock_mod, "TaskLock", _LockOcupado)
    monkeypatch.setattr(mod, "ProcessAgent", _AgenteQueNaoDeveRodar)
    monkeypatch.setattr(dbbase, "engine", _EngineFake())

    assert poll_all_processes.run() == {"skipped": True, "reason": "lock_held"}
    assert rodou["agente"] is False
