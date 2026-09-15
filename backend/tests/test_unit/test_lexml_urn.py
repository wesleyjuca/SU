"""URN LexML — normalização, validação e derivação de campos.

A URN é a chave natural de `lexml_normas`. O princípio testado aqui é o de
desenho: uma URN que não casa a forma esperada é PRESERVADA como veio e
apenas não rende campos derivados — nunca é "consertada" por heurística.
"""
import pytest

from app.services.lexml_urn import derivar_campos_da_urn, normalizar_urn, validar_urn

# URN real, a mesma já usada nos testes do cliente LexML.
_CDC = "urn:lex:br:federal:lei:1990-09-11;8078"


@pytest.mark.parametrize("entrada, esperado", [
    ("  URN:LEX:BR:federal:Lei:1990-09-11;8078  ", _CDC),
    (_CDC, _CDC),
    ("urn:lex:br:federal:lei:1990-09-11;8078\n", _CDC),
    ("", None),
    (None, None),
    ("   ", None),
])
def test_normalizacao_e_conservadora(entrada, esperado):
    assert normalizar_urn(entrada) == esperado


@pytest.mark.parametrize("urn", [
    _CDC,
    "urn:lex:br:federal:decreto:2021-01-15;10000",
    "urn:lex:br;sp:estadual:lei:2020;17000",
])
def test_urns_validas(urn):
    assert validar_urn(urn) is True


@pytest.mark.parametrize("urn, motivo", [
    ("", "vazia"),
    (None, "nula"),
    ("lei 8078/1990", "sem prefixo"),
    ("urn:lex:br:federal", "segmentos de menos"),
    ("urn:lex:br::lei:1990;8078", "segmento vazio"),
    ("https://planalto.gov.br/l8078", "é URL, não URN"),
])
def test_urns_invalidas(urn, motivo):
    assert validar_urn(urn) is False, f"deveria rejeitar: {motivo}"


def test_derivacao_completa():
    campos = derivar_campos_da_urn(_CDC)
    assert campos["localidade"] == "br"
    assert campos["autoridade"] == "federal"
    assert campos["tipo_norma"] == "Lei"   # forma de exibição, não a da URN
    assert campos["numero"] == "8078"
    assert campos["ano"] == 1990
    assert campos["data_publicacao"] == "1990-09-11"


def test_derivacao_com_so_o_ano():
    campos = derivar_campos_da_urn("urn:lex:br;sp:estadual:lei:2020;17000")
    assert campos["ano"] == 2020
    assert campos["numero"] == "17000"
    assert campos["data_publicacao"] is None  # não inventa dia/mês


def test_urn_invalida_nao_inventa_campo():
    """O ponto central do desenho: sem estrutura reconhecível, tudo nulo."""
    campos = derivar_campos_da_urn("lei 8078 de 1990")
    assert set(campos.values()) == {None}


def test_derivacao_nunca_lanca():
    for entrada in (None, "", "urn:lex:::", "urn:lex:a:b:c:", "urn:lex:a:b:c:;;;"):
        assert isinstance(derivar_campos_da_urn(entrada), dict)
