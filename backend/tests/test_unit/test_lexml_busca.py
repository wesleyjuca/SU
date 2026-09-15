"""Busca LexML — CQL montada, cliente SRU e a orquestração cache→acervo→fonte.

O ponto central destes testes é o que o plano da fase deixou explícito: a CQL
enviada ao portal usa SÓ as formas provadas em produção. `ano` e `autoridade`
nunca entram nela — são pós-filtro no acervo local, porque os índices
correspondentes do SRU nunca foram vistos respondendo e um índice inexistente
pode derrubar a busca inteira.
"""
import uuid

import pytest
from sqlalchemy import select

from app.integrations.lexml import client as lexml_client
from app.integrations.lexml.client import montar_query_cql
from app.models.lexml import LexmlNorma, LexmlNormaTenant
from app.services import lexml_acervo
from tests.db_isolada import sessao_isolada

_XML_UM_REGISTRO = """<?xml version="1.0"?>
<srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/">
  <srw:numberOfRecords>1</srw:numberOfRecords>
  <srw:records><srw:record><srw:recordData>
    <urn>urn:lex:br:federal:lei:2021-04-01;14133</urn>
    <title>Lei de Licitações e Contratos Administrativos</title>
    <location>https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm</location>
  </srw:recordData></srw:record></srw:records>
</srw:searchRetrieveResponse>"""


class _RespostaFake:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class _ClienteFake:
    """Captura os params da chamada — é o que prova qual CQL foi enviada."""

    def __init__(self, capturados: list, resposta: _RespostaFake):
        self._capturados = capturados
        self._resposta = resposta

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def get(self, url, params=None, **_kwargs):
        self._capturados.append({"url": url, "params": params or {}})
        return self._resposta


@pytest.fixture(autouse=True)
def _breaker_limpo():
    """O `CircuitBreaker` do LexML é singleton de MÓDULO — abre depois de 3
    falhas e assim fica para todo teste seguinte no mesmo processo.

    Achado real desta fase, não precaução: o teste de degradação abaixo
    (3× HTTP 403) abriu o breaker e derrubou 3 testes de OUTROS arquivos
    (`test_lexml_client.py`, `test_lexml_seguranca.py`) que passavam
    isolados — só apareceu ao rodar a suíte inteira. Fechar antes E depois
    de cada teste mantém o efeito dentro do arquivo que o causou.
    """
    lexml_client._breaker.record_success()
    yield
    lexml_client._breaker.record_success()


def _fingir_http(monkeypatch, capturados, resposta):
    monkeypatch.setattr(
        lexml_client.httpx, "AsyncClient",
        lambda **_kwargs: _ClienteFake(capturados, resposta),
    )


# ─── CQL ─────────────────────────────────────────────────────────────────────

def test_cql_texto_livre_vai_sozinho():
    assert montar_query_cql("Lei 14.133") == "Lei 14.133"


def test_cql_com_tipo_usa_a_forma_provada_da_sincronizacao():
    assert montar_query_cql("licitação", "Lei") == "licitação and localidade=federal and tipoDocumento=Lei"


def test_cql_so_tipo_sem_texto_nao_gera_and_orfao():
    assert montar_query_cql("", "Decreto") == "localidade=federal and tipoDocumento=Decreto"


def test_cql_nunca_contem_indice_nao_provado():
    """Guarda de regressão: se alguém adicionar `ano=`/`autoridade=` à CQL sem
    uma sonda real confirmando o índice, este teste reprova."""
    query = montar_query_cql("Lei 14.133 de 2021 do Congresso Nacional", "Lei")
    assert "ano=" not in query
    assert "autoridade=" not in query


# ─── Cliente SRU ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_buscar_normas_envia_cql_e_parseia(monkeypatch):
    capturados = []
    _fingir_http(monkeypatch, capturados, _RespostaFake(200, _XML_UM_REGISTRO))

    resultado = await lexml_client.buscar_normas("licitação", "Lei", limite=5)

    assert capturados[0]["params"]["query"] == "licitação and localidade=federal and tipoDocumento=Lei"
    assert capturados[0]["params"]["maximumRecords"] == "5"
    assert len(resultado) == 1
    assert resultado[0]["urn"] == "urn:lex:br:federal:lei:2021-04-01;14133"
    assert resultado[0]["url"].startswith("https://www.planalto.gov.br/")


@pytest.mark.asyncio
async def test_buscar_normas_degrada_sem_lancar(monkeypatch):
    """HTTP 403 (ou qualquer falha) devolve `[]` — nunca exceção: quem chama
    está num caminho síncrono de usuário."""
    capturados = []
    _fingir_http(monkeypatch, capturados, _RespostaFake(403, "bloqueado"))
    assert await lexml_client.buscar_normas("qualquer coisa") == []


@pytest.mark.asyncio
async def test_buscar_normas_sem_criterio_nao_chama_a_rede(monkeypatch):
    capturados = []
    _fingir_http(monkeypatch, capturados, _RespostaFake(200, _XML_UM_REGISTRO))
    assert await lexml_client.buscar_normas("   ") == []
    assert capturados == [], "busca vazia não pode gastar uma chamada ao portal"


# ─── Orquestração (Postgres real) ────────────────────────────────────────────

async def _limpar(db, urns):
    for urn in urns:
        norma = (await db.execute(select(LexmlNorma).where(LexmlNorma.urn == urn))).scalar_one_or_none()
        if norma:
            await db.execute(
                LexmlNormaTenant.__table__.delete().where(LexmlNormaTenant.norma_id == norma.id)
            )
            await db.delete(norma)
    await db.commit()


@pytest.mark.asyncio
async def test_busca_persiste_o_que_veio_da_fonte(monkeypatch):
    urn = f"urn:lex:br:federal:lei:2021-04-01;busca{uuid.uuid4().hex[:8]}"

    async def _fonte_fake(texto, tipo_norma=None, limite=20):
        return [{"urn": urn, "titulo": "Lei de teste", "url": "https://www.planalto.gov.br/x.htm"}]

    monkeypatch.setattr(lexml_client, "buscar_normas", _fonte_fake)

    async with sessao_isolada() as db:
        await _limpar(db, [urn])
        try:
            resposta = await lexml_acervo.buscar(db, texto="Lei de teste", limite=10)
            assert resposta["fonte_consultada"] is True
            assert resposta["fonte_respondeu"] is True
            assert any(r["urn"] == urn and r["origem"] == "lexml" for r in resposta["resultados"])

            # A norma ficou no acervo — a MESMA busca agora sai local.
            persistida = (await db.execute(
                select(LexmlNorma).where(LexmlNorma.urn == urn)
            )).scalar_one_or_none()
            assert persistida is not None
            assert persistida.ano == 2021, "campos derivados da URN têm de ser gravados"
        finally:
            await _limpar(db, [urn])


@pytest.mark.asyncio
async def test_ano_filtra_o_que_veio_da_fonte_tambem(monkeypatch):
    """O filtro por ano é pós-filtro local — mas vale para as duas origens,
    senão a mesma busca devolveria conjuntos diferentes conforme de onde cada
    linha veio."""
    urn_2021 = f"urn:lex:br:federal:lei:2021-04-01;a{uuid.uuid4().hex[:8]}"
    urn_1990 = f"urn:lex:br:federal:lei:1990-09-11;b{uuid.uuid4().hex[:8]}"

    async def _fonte_fake(texto, tipo_norma=None, limite=20):
        return [
            {"urn": urn_2021, "titulo": "Norma de 2021", "url": None},
            {"urn": urn_1990, "titulo": "Norma de 1990", "url": None},
        ]

    monkeypatch.setattr(lexml_client, "buscar_normas", _fonte_fake)

    async with sessao_isolada() as db:
        await _limpar(db, [urn_2021, urn_1990])
        try:
            resposta = await lexml_acervo.buscar(db, texto="Norma", ano=2021, limite=10)
            urns = {r["urn"] for r in resposta["resultados"]}
            assert urn_2021 in urns
            assert urn_1990 not in urns
        finally:
            await _limpar(db, [urn_2021, urn_1990])


@pytest.mark.asyncio
async def test_consultar_fonte_false_nao_toca_a_rede(monkeypatch):
    chamou = []

    async def _fonte_fake(*_a, **_k):
        chamou.append(True)
        return []

    monkeypatch.setattr(lexml_client, "buscar_normas", _fonte_fake)

    async with sessao_isolada() as db:
        resposta = await lexml_acervo.buscar(db, texto="qualquer", consultar_fonte=False)
        assert resposta["fonte_consultada"] is False
        assert chamou == []


@pytest.mark.asyncio
async def test_fonte_muda_nao_apaga_metadado_ja_conhecido(monkeypatch):
    """Regressão do upsert conservador: uma busca que devolveu menos metadado
    que a ingestão anterior não pode zerar o que já se sabia."""
    urn = f"urn:lex:br:federal:lei:2021-04-01;c{uuid.uuid4().hex[:8]}"

    async def _fonte_pobre(*_a, **_k):
        return [{"urn": urn, "titulo": None, "url": None}]

    monkeypatch.setattr(lexml_client, "buscar_normas", _fonte_pobre)

    async with sessao_isolada() as db:
        await _limpar(db, [urn])
        try:
            await lexml_acervo.upsert_norma(
                db, urn=urn, titulo="Título bom", ementa="Ementa boa",
                url_fonte="https://www.planalto.gov.br/bom.htm",
            )
            await db.commit()

            await lexml_acervo.buscar(db, texto="Título bom", limite=10)

            norma = (await db.execute(
                select(LexmlNorma).where(LexmlNorma.urn == urn)
            )).scalar_one()
            assert norma.titulo == "Título bom"
            assert norma.ementa == "Ementa boa"
            assert norma.url_fonte == "https://www.planalto.gov.br/bom.htm"
        finally:
            await _limpar(db, [urn])
