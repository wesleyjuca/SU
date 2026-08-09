"""Fase 149/150 — CPF/CNPJ ciframento em repouso: cobre decrypt_or_raw()
(app/core/crypto.py), o helper fail-soft compartilhado por clients.py
(_to_response) e lgpd.py (export de portabilidade) que precisa continuar
servindo linhas gravadas em texto puro antes da Fase 149 (sem backfill,
mesmo padrão de outras migrações de dado em repouso desta sessão)."""
from app.core.crypto import encrypt, decrypt_or_raw


def test_decrypt_or_raw_none_e_vazio_passam_direto():
    assert decrypt_or_raw(None) is None
    assert decrypt_or_raw("") == ""


def test_decrypt_or_raw_faz_round_trip_de_valor_cifrado():
    cifrado = encrypt("123.456.789-00")
    assert decrypt_or_raw(cifrado) == "123.456.789-00"


def test_decrypt_or_raw_cai_pro_valor_bruto_em_dado_legado_texto_puro():
    """Linha gravada ANTES da Fase 149 tem CPF em texto puro — não é um
    token Fernet válido, decrypt() falha (InvalidToken) e o helper precisa
    devolver o valor como está, não None/erro."""
    legado = "123.456.789-00"
    assert decrypt_or_raw(legado) == legado
