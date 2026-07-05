"""Criptografia simétrica (Fernet) para segredos em repouso — ex.: chaves de IA
por usuário (BYOK). A chave deriva de settings.ENCRYPTION_KEY."""
import base64
import hashlib
from cryptography.fernet import Fernet, InvalidToken
from app.config import settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        # Fernet exige 32 bytes url-safe base64. ENCRYPTION_KEY pode ter qualquer
        # tamanho → derivamos 32 bytes estáveis via SHA-256.
        raw = (settings.ENCRYPTION_KEY or settings.SECRET_KEY or "afj-fallback-key").encode()
        key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
        _fernet = Fernet(key)
    return _fernet


def encrypt(plaintext: str) -> str | None:
    """Cifra um texto. Retorna o token (str) ou None em caso de entrada vazia/erro."""
    if not plaintext:
        return None
    try:
        return _get_fernet().encrypt(plaintext.encode()).decode()
    except Exception:
        return None


def decrypt(token: str | None) -> str | None:
    """Decifra um token. Retorna o texto ou None se inválido/vazio."""
    if not token:
        return None
    try:
        return _get_fernet().decrypt(token.encode()).decode()
    except (InvalidToken, Exception):
        return None
