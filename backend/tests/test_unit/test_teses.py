"""Fase 138.4 — CRUD de teses: isolamento por tenant (nunca pular esse
teste — invariante multi-tenant), validação de nome vazio, duplicata."""
import pytest
from fastapi import HTTPException

from app.api.v1.teses import (
    list_teses, create_tese, update_tese, deactivate_tese,
    TeseCreate, TeseUpdate,
)


class _FakeUser:
    def __init__(self, tenant_id="tenant-a"):
        self.tenant_id = tenant_id


class _FakeTese:
    def __init__(self, id, tenant_id, nome, area_direito=None, ativo=True):
        import datetime
        self.id = id
        self.tenant_id = tenant_id
        self.nome = nome
        self.area_direito = area_direito
        self.ativo = ativo
        self.created_at = datetime.datetime(2026, 1, 1)


class _FakeScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _FakeResult:
    def __init__(self, items=None, scalar=None):
        self._items = items or []
        self._scalar = scalar

    def scalars(self):
        return _FakeScalars(self._items)

    def scalar_one_or_none(self):
        return self._scalar


class _FakeDB:
    def __init__(self, execute_results=None):
        self._results = list(execute_results or [])
        self.added = []
        self.flushed = False

    async def execute(self, query):
        if self._results:
            return self._results.pop(0)
        return _FakeResult()

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        # simula o que o Postgres faria com server_default=func.now() —
        # num teste sem engine real, created_at nunca é preenchido sozinho.
        import datetime
        for obj in self.added:
            if getattr(obj, "created_at", "unset") is None:
                obj.created_at = datetime.datetime(2026, 1, 1)
            if getattr(obj, "ativo", "unset") is None:
                obj.ativo = True
        self.flushed = True


@pytest.mark.asyncio
async def test_list_teses_so_do_proprio_tenant():
    tese_a = _FakeTese("1", "tenant-a", "Prescrição intercorrente")
    db = _FakeDB(execute_results=[_FakeResult(items=[tese_a])])
    resultado = await list_teses(incluir_inativas=False, current_user=_FakeUser("tenant-a"), db=db)
    assert len(resultado) == 1
    assert resultado[0].nome == "Prescrição intercorrente"


@pytest.mark.asyncio
async def test_create_tese_nome_vazio_rejeitado():
    with pytest.raises(ValueError):
        TeseCreate(nome="   ")


@pytest.mark.asyncio
async def test_create_tese_duplicada_rejeitada():
    db = _FakeDB(execute_results=[_FakeResult(scalar="existing-id")])
    with pytest.raises(HTTPException) as exc:
        await create_tese(TeseCreate(nome="Dano moral"), current_user=_FakeUser("tenant-a"), db=db)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_create_tese_sucesso():
    db = _FakeDB(execute_results=[_FakeResult(scalar=None)])
    resultado = await create_tese(TeseCreate(nome="Dano moral", area_direito="CIVIL"), current_user=_FakeUser("tenant-a"), db=db)
    assert resultado.nome == "Dano moral"
    assert resultado.area_direito == "CIVIL"
    assert len(db.added) == 1
    assert db.added[0].tenant_id == "tenant-a"


@pytest.mark.asyncio
async def test_update_tese_de_outro_tenant_404():
    """Tenant B tenta editar uma tese que só existe pro tenant A — a query
    já filtra por tenant_id, então o resultado é None (não achado), nunca
    um vazamento de dado de outro escritório."""
    db = _FakeDB(execute_results=[_FakeResult(scalar=None)])
    with pytest.raises(HTTPException) as exc:
        await update_tese("11111111-1111-1111-1111-111111111111", TeseUpdate(nome="Hackeado"), current_user=_FakeUser("tenant-b"), db=db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_deactivate_tese_marca_ativo_false():
    tese = _FakeTese("11111111-1111-1111-1111-111111111111", "tenant-a", "Dano moral")
    db = _FakeDB(execute_results=[_FakeResult(scalar=tese)])
    await deactivate_tese("11111111-1111-1111-1111-111111111111", current_user=_FakeUser("tenant-a"), db=db)
    assert tese.ativo is False
    assert db.flushed is True
