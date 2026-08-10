"""Fase 167 — `scan_publicacoes` não pode deixar o `SyncRun` preso em
RUNNING se uma exceção não prevista acontecer no meio do loop de OABs (o
circuit breaker da Fase 142 só evita chamadas REPETIDAS após falhas
consecutivas — não intercepta exceções). Separado de
test_dje_monitor_circuit_breaker.py (concern distinto: aqui é sobre
proteção do SyncRun, não sobre o breaker em si)."""
import uuid

import pytest

import app.services.dje_monitor as dje_monitor


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


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


class _FakeComunicacao:
    numero_cnj = "0001"
    numero_cnj_fmt = "0001"
    texto = "texto da intimacao"
    data_disponibilizacao = None
    tribunal = "TJSP"
    tipo_comunicacao = "Intimação"
    orgao = "1a Vara"
    link = None

    def hash_dedupe(self):
        return "hash1"


async def _fake_sleep(*args, **kwargs):
    pass


@pytest.mark.asyncio
async def test_excecao_no_meio_do_loop_finaliza_run_como_erro_e_relanca(monkeypatch):
    tenant_id = uuid.uuid4()

    chamadas_finalizar = []

    async def _fake_iniciar_sync(db, t_id, fonte, tipo):
        return object()

    async def _fake_finalizar_sync(db, run, status, stats):
        chamadas_finalizar.append((status, stats))

    monkeypatch.setattr("app.services.movements_import.iniciar_sync", _fake_iniciar_sync)
    monkeypatch.setattr("app.services.movements_import.finalizar_sync", _fake_finalizar_sync)

    async def _fake_buscar_comunicacoes(oab_numero, oab_uf, data_inicio, data_fim, stats=None, **kwargs):
        if stats is not None:
            stats["requests"] = 1
            stats["ok"] = True
        return [_FakeComunicacao()]

    monkeypatch.setattr("app.integrations.dje.comunica.buscar_comunicacoes", _fake_buscar_comunicacoes)
    monkeypatch.setattr(dje_monitor.asyncio, "sleep", _fake_sleep)

    # Ordem de execute(): [OABs monitoradas] [TenantConfig.extra_data]
    # [proc_map (LegalProcess)] [dedup Intimacao -> RAISES]
    db = _FakeDB([
        _FakeScalarsResult([("1000", "SP", tenant_id)]),
        _FakeScalarsResult([]),
        _FakeScalarsResult([]),
        _RaiseNoExecute(RuntimeError("DB caiu no meio do loop de OABs")),
    ])

    with pytest.raises(RuntimeError, match="DB caiu no meio do loop de OABs"):
        await dje_monitor.scan_publicacoes(db, tenant_id=None, dias_retro=1)

    assert len(chamadas_finalizar) == 1
    status, stats = chamadas_finalizar[0]
    assert status == "ERRO"
    assert stats["oabs_monitoradas"] == 1
    assert "erro" in stats
