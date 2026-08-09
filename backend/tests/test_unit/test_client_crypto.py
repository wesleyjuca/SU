"""Fase 149 — CPF/CNPJ ciframento em repouso: cobre o helper de decrypt
fail-soft, que precisa continuar servindo linhas gravadas em texto puro
antes desta fase (sem backfill, mesmo padrão de outras migrações de dado
em repouso desta sessão)."""
from app.api.v1.clients import _decrypt_or_raw
from app.core.crypto import encrypt


def test_decrypt_or_raw_none_e_vazio_passam_direto():
    assert _decrypt_or_raw(None) is None
    assert _decrypt_or_raw("") == ""


def test_decrypt_or_raw_faz_round_trip_de_valor_cifrado():
    cifrado = encrypt("123.456.789-00")
    assert _decrypt_or_raw(cifrado) == "123.456.789-00"


def test_decrypt_or_raw_cai_pro_valor_bruto_em_dado_legado_texto_puro():
    """Linha gravada ANTES da Fase 149 tem CPF em texto puro — não é um
    token Fernet válido, decrypt() falha (InvalidToken) e o helper precisa
    devolver o valor como está, não None/erro."""
    legado = "123.456.789-00"
    assert _decrypt_or_raw(legado) == legado
