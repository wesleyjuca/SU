"""Fase 95 — CRM: client_id de oportunidade não pode vazar dado cross-tenant."""
import uuid
import pytest
from fastapi import HTTPException

from app.api.v1.crm import _validar_client_id, _nomes_clientes
from app.models.client import Client
from app.models.crm import Opportunity


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeScalarsResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class _FakeDB:
    """Simula AsyncSession.execute — devolve o resultado configurado, sem
    interpretar a query (o teste controla o retorno esperado por cenário)."""
    def __init__(self, resultado):
        self._resultado = resultado

    async def execute(self, *_a, **_k):
        return self._resultado


TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()
CLIENT_ID = uuid.uuid4()


@pytest.mark.asyncio
async def test_validar_client_id_pertence_ao_tenant():
    db = _FakeDB(_FakeScalarResult(CLIENT_ID))
    resultado = await _validar_client_id(db, str(CLIENT_ID), TENANT_A)
    assert resultado == CLIENT_ID


@pytest.mark.asyncio
async def test_validar_client_id_de_outro_tenant_e_rejeitado():
    # Simula: o SELECT filtrado por tenant_id não encontra o cliente
    # (porque ele pertence a outro tenant) — scalar_one_or_none() -> None.
    db = _FakeDB(_FakeScalarResult(None))
    with pytest.raises(HTTPException) as exc_info:
        await _validar_client_id(db, str(CLIENT_ID), TENANT_B)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_validar_client_id_vazio_retorna_none_sem_consultar_db():
    db = _FakeDB(_FakeScalarResult("nao deveria ser usado"))
    assert await _validar_client_id(db, None, TENANT_A) is None
    assert await _validar_client_id(db, "", TENANT_A) is None


@pytest.mark.asyncio
async def test_nomes_clientes_filtra_por_tenant():
    cliente_a = Client(id=CLIENT_ID, tenant_id=TENANT_A, nome_completo="Cliente do Tenant A")
    opp = Opportunity(client_id=CLIENT_ID)

    # Simula: a query já filtrou por tenant_id — só devolve o cliente do tenant certo.
    db = _FakeDB(_FakeScalarsResult([cliente_a]))
    nomes = await _nomes_clientes(db, [opp], TENANT_A)
    assert nomes == {CLIENT_ID: "Cliente do Tenant A"}


@pytest.mark.asyncio
async def test_nomes_clientes_sem_oportunidades_nao_consulta_db():
    db = _FakeDB(_FakeScalarsResult(["nao deveria ser usado"]))
    assert await _nomes_clientes(db, [], TENANT_A) == {}
