"""Fase 97 — process_agent._save_movements: defesa em profundidade por tenant_id.

Mesmo com process_id vindo de uma fonte não validada (ex.: task_input
controlado pelo chamador), o processo só deve ser encontrado/gravado se
pertencer ao tenant do contexto — nunca ao de outro escritório.
"""
import uuid
import pytest

from app.agents.process.process_agent import ProcessAgent


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    def __init__(self, resultado):
        self._resultado = resultado
        self.committed = False
        self.rolled_back = False

    async def execute(self, *_a, **_k):
        return self._resultado

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def close(self):
        pass


PROCESS_ID = uuid.uuid4()
TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()


@pytest.mark.asyncio
async def test_processo_de_outro_tenant_nao_e_encontrado_nem_gravado(monkeypatch):
    # Simula: o SELECT com filtro de tenant_id não encontra o processo
    # (porque ele pertence a outro tenant) — scalar_one_or_none() -> None.
    db = _FakeDB(_FakeScalarResult(None))
    agent = ProcessAgent(db=db)

    chamado = {"importar": False}

    async def _fake_importar(*a, **k):
        chamado["importar"] = True
        return {"novos": 999}

    import app.services.movements_import as mi
    monkeypatch.setattr(mi, "importar_movimentos", _fake_importar)

    novos = await agent._save_movements(PROCESS_ID, [], [], tenant_id=TENANT_B)

    assert novos == 0
    assert chamado["importar"] is False, "não deve gravar/notificar em processo de outro tenant"
    assert db.committed is False


@pytest.mark.asyncio
async def test_processo_do_proprio_tenant_e_gravado_normalmente(monkeypatch):
    class _FakeProc:
        id = PROCESS_ID

    db = _FakeDB(_FakeScalarResult(_FakeProc()))
    agent = ProcessAgent(db=db)

    async def _fake_importar(*a, **k):
        return {"novos": 3}

    import app.services.movements_import as mi
    monkeypatch.setattr(mi, "importar_movimentos", _fake_importar)

    novos = await agent._save_movements(PROCESS_ID, [], [], tenant_id=TENANT_A)

    assert novos == 3
    assert db.committed is True


@pytest.mark.asyncio
async def test_sem_tenant_id_mantem_comportamento_atual_sem_filtro(monkeypatch):
    """tenant_id=None (default) preserva o comportamento anterior — usado só
    em caminhos internos onde o processo já é conhecido/confiável."""
    class _FakeProc:
        id = PROCESS_ID

    db = _FakeDB(_FakeScalarResult(_FakeProc()))
    agent = ProcessAgent(db=db)

    async def _fake_importar(*a, **k):
        return {"novos": 1}

    import app.services.movements_import as mi
    monkeypatch.setattr(mi, "importar_movimentos", _fake_importar)

    novos = await agent._save_movements(PROCESS_ID, [], [])
    assert novos == 1
