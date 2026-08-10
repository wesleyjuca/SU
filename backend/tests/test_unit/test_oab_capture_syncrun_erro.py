"""Fase 167 — `capturar_por_oab` não pode deixar o `SyncRun` preso em
RUNNING se o enriquecimento (DataJud/partes credenciadas), que roda SEM
try/except próprio, lançar. Antes desta fase, essa exceção propagava direto
pra fora da função, pulando `finalizar_sync("OK", ...)`."""
import uuid

import pytest


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def all(self):
        return self._value if self._value is not None else []


class _FakeDB:
    def __init__(self, queue):
        self._queue = list(queue)
        self.commits = 0

    async def execute(self, query):
        return self._queue.pop(0)

    def add(self, obj):
        pass

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1


class _FakeRaw:
    numero_cnj_fmt = "0001234-56.2026.8.26.0100"


class _FakeProcessoDescoberto:
    numero_cnj = "00012345620268260100"
    tribunal = "TJSP"
    raw = _FakeRaw()


@pytest.mark.asyncio
async def test_falha_no_enriquecimento_finaliza_run_como_erro_e_relanca(monkeypatch):
    import app.services.oab_capture as mod

    tenant_id = uuid.uuid4()
    chamadas_finalizar = []

    async def _fake_iniciar_sync(db, t_id, fonte, tipo):
        return object()

    async def _fake_finalizar_sync(db, run, status, stats):
        chamadas_finalizar.append((status, stats))

    monkeypatch.setattr("app.services.movements_import.iniciar_sync", _fake_iniciar_sync)
    monkeypatch.setattr("app.services.movements_import.finalizar_sync", _fake_finalizar_sync)

    class _FakeFonteComunica:
        async def descobrir_por_oab(self, numero, uf, inicio, hoje, max_paginas=20, stats=None):
            if stats is not None:
                stats["itens"] = 1
                stats["ok"] = True
            return [_FakeProcessoDescoberto()]

    monkeypatch.setattr("app.integrations.fontes.registry.obter_fonte", lambda nome: _FakeFonteComunica())

    async def _fake_enriquecer_via_datajud(db, novos):
        return None

    async def _fake_enriquecer_partes_falha(db, tenant_id, novos):
        raise RuntimeError("PDPJ indisponível no meio do enriquecimento")

    monkeypatch.setattr(mod, "_enriquecer_via_datajud", _fake_enriquecer_via_datajud)
    monkeypatch.setattr(mod, "_enriquecer_partes", _fake_enriquecer_partes_falha)

    # Ordem de execute(): [candidatos de owner p/ apenas_oab] [existentes]
    db = _FakeDB([
        _FakeScalarResult([]),   # nenhum advogado dono dessa OAB no tenant
        _FakeScalarResult([]),  # nenhum processo existente -- CNJ é novo
    ])

    with pytest.raises(RuntimeError, match="PDPJ indisponível"):
        await mod.capturar_por_oab(db, tenant_id, apenas_oab=("12345", "SP"))

    assert len(chamadas_finalizar) == 1
    status, stats = chamadas_finalizar[0]
    assert status == "ERRO"
    assert stats["processos_criados"] == 1  # o processo já tinha sido criado antes da falha
    assert "erro" in stats


@pytest.mark.asyncio
async def test_caminho_feliz_finaliza_ok(monkeypatch):
    import app.services.oab_capture as mod

    tenant_id = uuid.uuid4()
    chamadas_finalizar = []

    async def _fake_iniciar_sync(db, t_id, fonte, tipo):
        return object()

    async def _fake_finalizar_sync(db, run, status, stats):
        chamadas_finalizar.append((status, stats))

    monkeypatch.setattr("app.services.movements_import.iniciar_sync", _fake_iniciar_sync)
    monkeypatch.setattr("app.services.movements_import.finalizar_sync", _fake_finalizar_sync)

    class _FakeFonteComunica:
        async def descobrir_por_oab(self, numero, uf, inicio, hoje, max_paginas=20, stats=None):
            if stats is not None:
                stats["itens"] = 1
                stats["ok"] = True
            return [_FakeProcessoDescoberto()]

    monkeypatch.setattr("app.integrations.fontes.registry.obter_fonte", lambda nome: _FakeFonteComunica())
    monkeypatch.setattr(mod, "_enriquecer_via_datajud", lambda db, novos: _ok())
    monkeypatch.setattr(mod, "_enriquecer_partes", lambda db, tenant_id, novos: _ok())

    db = _FakeDB([_FakeScalarResult([]), _FakeScalarResult([])])
    resultado = await mod.capturar_por_oab(db, tenant_id, apenas_oab=("12345", "SP"))

    assert resultado["processos_criados"] == 1
    assert chamadas_finalizar[0][0] == "OK"


async def _ok():
    return None
