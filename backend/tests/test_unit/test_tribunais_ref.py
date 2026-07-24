"""Fase 74 — helpers de referência de tribunais (puros, sem I/O)."""
from app.services.tribunais_ref import (
    derivar_tipo,
    derivar_uf,
    linhas_seed,
    normalizar_codigo,
)


def test_normaliza_df_para_tjdft():
    assert normalizar_codigo("TJDF") == "TJDFT"
    assert normalizar_codigo("tjdf") == "TJDFT"
    assert normalizar_codigo("TJDFT") == "TJDFT"
    assert normalizar_codigo(" tjsp ") == "TJSP"
    assert normalizar_codigo(None) == ""


def test_deriva_tipo():
    assert derivar_tipo("TJSP") == "ESTADUAL"
    assert derivar_tipo("TRF3") == "FEDERAL"
    assert derivar_tipo("TRT2") == "TRABALHO"
    assert derivar_tipo("STJ") == "SUPERIOR"
    assert derivar_tipo("TJDFT") == "ESTADUAL"


def test_deriva_uf():
    assert derivar_uf("TJSP") == "SP"
    assert derivar_uf("TJDFT") == "DF"     # caso especial
    assert derivar_uf("TRF3") is None
    assert derivar_uf("STF") is None


def test_linhas_seed_dedup_e_df():
    linhas = linhas_seed()
    codigos = {ln["codigo"] for ln in linhas}
    # DF entra só como TJDFT (normalizado), nunca TJDF cru
    assert "TJDFT" in codigos and "TJDF" not in codigos
    # traz estaduais, superiores, TRFs e TRTs
    assert {"TJSP", "STJ", "TRF3", "TRT2"} <= codigos
    # a linha do DF tem o índice DataJud correto e UF derivada
    df = next(ln for ln in linhas if ln["codigo"] == "TJDFT")
    assert df["datajud_index"] == "api_publica_tjdft" and df["uf"] == "DF"
    # todas têm índice não-vazio
    assert all(ln["datajud_index"] for ln in linhas)
