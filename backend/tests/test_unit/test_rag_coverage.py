"""Fase 90 — GET /rag/coverage: contagem de chunks por coleção (Qdrant mockado).

Fase 204 (achado BAIXO da Fase 203) — nas coleções privadas do escritório, a
contagem passou a ser escopada por tenant_id (antes vazava o total agregado
da plataforma inteira, todos os tenants somados, pra qualquer usuário staff)."""
import pytest

from app.api.v1.rag import rag_coverage, VALID_COLLECTIONS
from app.rag.retrieval import PRIVATE_COLLECTIONS


class _FakeUser:
    tenant_id = "t1"


class _Collection:
    def __init__(self, name):
        self.name = name


class _CollectionsResp:
    def __init__(self, names):
        self.collections = [_Collection(n) for n in names]


class _CountResp:
    def __init__(self, count):
        self.count = count


class _FakeQdrant:
    """Registra os `count_filter` recebidos por coleção, pra confirmar que só
    as coleções privadas recebem filtro de tenant_id."""
    def __init__(self, existentes, pontos):
        self._existentes = existentes
        self._pontos = pontos
        self.filtros_recebidos = {}

    async def get_collections(self):
        return _CollectionsResp(self._existentes)

    async def count(self, collection_name, count_filter=None, exact=False):
        self.filtros_recebidos[collection_name] = count_filter
        if collection_name not in self._pontos:
            raise RuntimeError("sem coleção")
        return _CountResp(self._pontos[collection_name])


@pytest.mark.asyncio
async def test_rag_coverage_conta_so_colecoes_validas(monkeypatch):
    fake = _FakeQdrant(
        existentes=["jurisprudencia", "peticoes_afj", "outra_colecao_nao_valida"],
        pontos={"jurisprudencia": 42, "peticoes_afj": 7},
    )

    async def _fake_get_qdrant():
        return fake

    import app.db.qdrant as qdrant_mod
    monkeypatch.setattr(qdrant_mod, "get_qdrant", _fake_get_qdrant)

    resp = await rag_coverage(current_user=_FakeUser())
    por_colecao = {c["collection"]: c["pontos"] for c in resp["colecoes"]}

    assert set(por_colecao) == VALID_COLLECTIONS
    assert por_colecao["jurisprudencia"] == 42
    assert por_colecao["peticoes_afj"] == 7
    # coleção válida mas ainda não criada no Qdrant → 0, não erro
    assert por_colecao["legislacao"] == 0


@pytest.mark.asyncio
async def test_rag_coverage_escopa_colecoes_privadas_por_tenant(monkeypatch):
    fake = _FakeQdrant(
        existentes=list(VALID_COLLECTIONS),
        pontos={n: 1 for n in VALID_COLLECTIONS},
    )

    async def _fake_get_qdrant():
        return fake

    import app.db.qdrant as qdrant_mod
    monkeypatch.setattr(qdrant_mod, "get_qdrant", _fake_get_qdrant)

    await rag_coverage(current_user=_FakeUser())

    for nome in VALID_COLLECTIONS:
        filtro = fake.filtros_recebidos[nome]
        if nome in PRIVATE_COLLECTIONS:
            assert filtro is not None, f"{nome} é privada mas não recebeu filtro de tenant"
            cond = filtro.must[0]
            assert cond.key == "tenant_id"
            assert cond.match.value == "t1"
        else:
            assert filtro is None, f"{nome} é pública mas recebeu filtro de tenant"


@pytest.mark.asyncio
async def test_rag_coverage_qdrant_indisponivel_retorna_503(monkeypatch):
    from fastapi import HTTPException

    async def _fake_get_qdrant():
        raise RuntimeError("qdrant off")

    import app.db.qdrant as qdrant_mod
    monkeypatch.setattr(qdrant_mod, "get_qdrant", _fake_get_qdrant)

    with pytest.raises(HTTPException) as exc_info:
        await rag_coverage(current_user=_FakeUser())
    assert exc_info.value.status_code == 503
