"""Fase 77 — observabilidade das fontes no Cérebro (lógica, sem rede/DB)."""
import pytest

from app.services import brain_infra, system_map


@pytest.mark.asyncio
async def test_fontes_probe_lista_breakers():
    r = await brain_infra._fontes()
    assert r["ok"] is True
    nomes = {f["nome"] for f in r["fontes"]}
    assert {"comunica", "datajud"} <= nomes
    # cada fonte reporta o estado do circuit breaker (fechado no boot)
    assert all(f["breaker"] == "closed" for f in r["fontes"])
    dj = next(f for f in r["fontes"] if f["nome"] == "datajud")
    assert "detalhar" in dj["capabilities"] and "movimentos" in dj["capabilities"]


def test_system_map_reflete_fontes_e_tribunais():
    mapa = system_map.construir_mapa()
    ids = {n["id"] for n in mapa["nos"]}
    # nós de fonte aparecem no grafo (inclui PDPJ credenciado)
    assert {"fonte_comunica", "fonte_datajud", "fonte_pdpj"} <= ids
    captura = next(n for n in mapa["nos"] if n["id"] == "captura")
    assert captura["meta"]["fontes"] == system_map._fontes_captura()
    assert captura["meta"]["tribunais"] == 62
    # resumo carrega as contagens novas
    assert mapa["resumo"]["fontes"] == len(system_map._fontes_captura())
    assert mapa["resumo"]["tribunais"] == 62
    # arestas captura→fonte
    fonte_edges = [a for a in mapa["arestas"] if a["tipo"] == "fonte"]
    assert any(a["para"] == "fonte_pdpj" for a in fonte_edges)


def test_system_map_nos_fonte_tem_meta_capabilities():
    """Fase 78: nós de fonte carregam meta.capabilities p/ o drill-down do mapa."""
    mapa = system_map.construir_mapa()
    dj = next(n for n in mapa["nos"] if n["id"] == "fonte_datajud")
    assert dj["meta"]["capabilities"] == ["detalhar", "movimentos"]
    pdpj = next(n for n in mapa["nos"] if n["id"] == "fonte_pdpj")
    assert "partes" in pdpj["meta"]["capabilities"] and pdpj["meta"]["credenciado"] is True
