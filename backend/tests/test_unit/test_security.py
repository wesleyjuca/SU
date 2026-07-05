"""Unit tests para hashing de senha (bcrypt direto, sem passlib)."""
from app.core.security import hash_password, verify_password


def test_hash_verify_roundtrip():
    h = hash_password("Admin@123")
    assert h.startswith("$2b$")          # formato bcrypt, compatível com hashes legados
    assert verify_password("Admin@123", h) is True


def test_verify_rejects_wrong_password():
    h = hash_password("Admin@123")
    assert verify_password("errada", h) is False


def test_verify_malformed_hash_returns_false_not_raises():
    # hash inválido no banco deve virar 401 legítimo, nunca 500
    assert verify_password("qualquer", "nao-e-um-hash-bcrypt") is False


def test_long_password_is_truncated_not_error():
    # bcrypt 5.x levanta em >72 bytes; hash_password deve truncar com segurança
    h = hash_password("x" * 200)
    assert verify_password("x" * 200, h) is True
