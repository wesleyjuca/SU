"""Fase 87 — migração das leituras de tribunal p/ a tabela (lógica pura)."""
import pytest

from app.services import tribunais_ref as tr
from app.integrations.tribunais.cnj import CNJDataJudClient, TRIBUNAL_INDICES


@pytest.fixture(autouse=True)
def _limpar_cache():
    tr._CACHE = None
    yield
    tr._CACHE = None


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _q):
        return _FakeResult(self._rows)


class _FakeDBFalha:
    async def execute(self, _q):
        raise RuntimeError("sem DB")


def test_sem_cache_indice_datajud_retorna_none():
    assert tr.indice_datajud("TJSP") is None


@pytest.mark.asyncio
async def test_carregar_cache_popula_e_normaliza():
    cache = await tr.carregar_cache(_FakeDB([("TJSP", "api_publica_tjsp"), ("tjce", "api_publica_tjce")]))
    assert cache["TJSP"] == "api_publica_tjsp"
    assert tr.indice_datajud("tjsp") == "api_publica_tjsp"  # normaliza maiúsculas


@pytest.mark.asyncio
async def test_carregar_cache_falha_nao_derruba_fica_vazio():
    cache = await tr.carregar_cache(_FakeDBFalha())
    assert cache == {}
    assert tr.indice_datajud("TJSP") is None


# ─── CNJDataJudClient._index: tabela tem prioridade, fallback preservado ──────
def test_index_sem_cache_usa_dict_hardcoded():
    client = CNJDataJudClient(tribunal="TJSP")
    assert client._index == TRIBUNAL_INDICES["TJSP"]


def test_index_com_cache_prioriza_a_tabela():
    tr._CACHE = {"TJSP": "indice_customizado_do_banco"}
    client = CNJDataJudClient(tribunal="TJSP")
    assert client._index == "indice_customizado_do_banco"


def test_index_tribunal_desconhecido_fallback_generico():
    tr._CACHE = {}
    client = CNJDataJudClient(tribunal="TJXX")
    assert client._index == "api_publica_tjxx"
