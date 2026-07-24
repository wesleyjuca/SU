"""Fase 75 — parsing PDPJ → partes e escritor de ProcessParty (lógica pura)."""
import pytest

from app.integrations.fontes.pdpj_fonte import PdpjFonte, parse_pdpj_partes
from app.services.partes_import import ParteEntrada, _chave


# ─── parse_pdpj_partes ────────────────────────────────────────────────────────
def test_parse_partes_polos_e_advogados():
    dados = {
        "poloAtivo": [
            {"nome": "João Autor", "documento": "12345678900",
             "advogados": [{"nome": "Dra. Ana", "numeroOab": "123", "ufOab": "CE"}]},
        ],
        "poloPassivo": [
            {"nome": "Empresa Ré LTDA", "cpfCnpj": "11222333000144"},
        ],
    }
    partes = parse_pdpj_partes(dados)
    tipos = [(p.tipo, p.nome, p.polo, p.oab) for p in partes]
    assert ("AUTOR", "João Autor", "ATIVO", None) in tipos
    assert ("ADVOGADO", "Dra. Ana", "ATIVO", "123/CE") in tipos
    assert ("REU", "Empresa Ré LTDA", "PASSIVO", None) in tipos
    # documento do autor preservado
    autor = next(p for p in partes if p.nome == "João Autor")
    assert autor.cpf_cnpj == "12345678900"


def test_parse_partes_lista_topo_e_polo_variantes():
    dados = {"partes": [
        {"nome": "Fulano", "polo": "ATIVO"},
        {"nome": "Sicrano", "tipoPolo": "PA"},   # variação de polo passivo
        {"nome": "Beltrano", "poloProcessual": "DESCONHECIDO"},
    ]}
    partes = parse_pdpj_partes(dados)
    m = {p.nome: (p.tipo, p.polo) for p in partes}
    assert m["Fulano"] == ("AUTOR", "ATIVO")
    assert m["Sicrano"] == ("REU", "PASSIVO")
    assert m["Beltrano"][0] == "PARTE"   # polo não reconhecido → PARTE


def test_parse_partes_vazio_e_lixo():
    assert parse_pdpj_partes({}) == []
    assert parse_pdpj_partes({"partes": [None, 42, {"semNome": 1}]}) == []


# ─── PdpjFonte capabilities / gating ──────────────────────────────────────────
def test_pdpj_fonte_capabilities():
    fonte = PdpjFonte(token="t")
    from app.integrations.fontes.base import Capability
    assert fonte.suporta(Capability.PARTES)
    assert fonte.suporta(Capability.DETALHAR)
    assert fonte.suporta(Capability.MOVIMENTOS)


@pytest.mark.asyncio
async def test_pdpj_fonte_sem_token_retorna_vazio():
    fonte = PdpjFonte(token="")
    assert await fonte.partes("0001234-56.2026.8.06.0001") == []
    assert await fonte.detalhar("0001234-56.2026.8.06.0001") is None


@pytest.mark.asyncio
async def test_pdpj_fonte_numero_invalido():
    fonte = PdpjFonte(token="tok")
    assert await fonte.partes("sem-digitos") == []


# ─── _chave (dedup do escritor) ───────────────────────────────────────────────
def test_chave_dedup_normaliza():
    # mesmo advogado com espaçamento/caixa diferentes → mesma chave
    a = _chave("ADVOGADO", "Dra.  ANA", "123/CE")
    b = _chave("advogado", "dra. ana", "123/ce")
    assert a == b
    # tipo diferente → chave diferente
    assert _chave("AUTOR", "João", None) != _chave("REU", "João", None)


def test_parte_entrada_defaults():
    p = ParteEntrada(tipo="AUTOR", nome="X")
    assert p.cpf_cnpj is None and p.oab is None and p.polo is None
