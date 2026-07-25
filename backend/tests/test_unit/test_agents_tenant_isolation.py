"""Fase 97 — POST /agents/trigger: process_id/client_id não podem apontar
pra dado de outro tenant (evita escrita/notificação cross-tenant via
process_agent.poll_process e demais agentes)."""
import uuid
import pytest
from fastapi import HTTPException

from app.api.v1.agents import _validar_pertence_ao_tenant


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    def __init__(self, resultado):
        self._resultado = resultado

    async def execute(self, *_a, **_k):
        return self._resultado


TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()
PROCESS_ID = uuid.uuid4()
CLIENT_ID = uuid.uuid4()


@pytest.mark.asyncio
async def test_process_id_do_proprio_tenant_e_aceito():
    db = _FakeDB(_FakeScalarResult(PROCESS_ID))
    await _validar_pertence_ao_tenant(db, TENANT_A, PROCESS_ID, None)  # não levanta


@pytest.mark.asyncio
async def test_process_id_de_outro_tenant_e_rejeitado():
    db = _FakeDB(_FakeScalarResult(None))
    with pytest.raises(HTTPException) as exc_info:
        await _validar_pertence_ao_tenant(db, TENANT_B, PROCESS_ID, None)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_client_id_de_outro_tenant_e_rejeitado():
    db = _FakeDB(_FakeScalarResult(None))
    with pytest.raises(HTTPException) as exc_info:
        await _validar_pertence_ao_tenant(db, TENANT_B, None, CLIENT_ID)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_sem_process_id_nem_client_id_nao_consulta_db():
    db = _FakeDB(_FakeScalarResult("nao deveria ser usado"))
    await _validar_pertence_ao_tenant(db, TENANT_A, None, None)  # não levanta, no-op
