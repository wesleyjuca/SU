"""Fase 98 — documents.py: process_id/client_id não podem vincular
documento/contrato/petição a dado de outro tenant (mesmo padrão das
Fases 95-97)."""
import uuid
import pytest
from fastapi import HTTPException

from app.api.v1.documents import _validar_client_id, _validar_process_id


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
CLIENT_ID = uuid.uuid4()
PROCESS_ID = uuid.uuid4()


@pytest.mark.asyncio
async def test_client_id_do_proprio_tenant_e_aceito():
    db = _FakeDB(_FakeScalarResult(CLIENT_ID))
    assert await _validar_client_id(db, str(CLIENT_ID), TENANT_A) == CLIENT_ID


@pytest.mark.asyncio
async def test_client_id_de_outro_tenant_e_rejeitado():
    db = _FakeDB(_FakeScalarResult(None))
    with pytest.raises(HTTPException) as exc_info:
        await _validar_client_id(db, str(CLIENT_ID), TENANT_B)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_process_id_do_proprio_tenant_e_aceito():
    db = _FakeDB(_FakeScalarResult(PROCESS_ID))
    assert await _validar_process_id(db, str(PROCESS_ID), TENANT_A) == PROCESS_ID


@pytest.mark.asyncio
async def test_process_id_de_outro_tenant_e_rejeitado():
    db = _FakeDB(_FakeScalarResult(None))
    with pytest.raises(HTTPException) as exc_info:
        await _validar_process_id(db, str(PROCESS_ID), TENANT_B)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_ids_vazios_nao_consultam_db():
    db = _FakeDB(_FakeScalarResult("nao deveria ser usado"))
    assert await _validar_client_id(db, None, TENANT_A) is None
    assert await _validar_process_id(db, None, TENANT_A) is None
