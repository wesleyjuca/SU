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
        secret = settings.ENCRYPTION_KEY or settings.SECRET_KEY
        if not secret:
            # Fail-closed em produção: sem chave, os segredos BYOK ficariam
            # cifrados com uma chave adivinhável — recusar em vez de degradar.
            if getattr(settings, "ENVIRONMENT", "development") == "production":
                raise RuntimeError(
                    "ENCRYPTION_KEY (ou SECRET_KEY) ausente em produção — "
                    "configure para cifrar os segredos BYOK em repouso."
                )
            secret = "afj-dev-fallback-key"  # apenas ambiente de desenvolvimento
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
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


def decrypt_or_raw(value: str | None) -> str | None:
    """Decifra um valor cifrado por encrypt(); se falhar (InvalidToken —
    dado gravado em texto puro ANTES de um campo passar a ser cifrado, sem
    backfill), devolve o valor bruto como está em vez de None. Uso: campos
    que migraram de texto puro pra cifrado sem reprocessar linhas antigas
    (ex.: Client.cpf/cnpj, Fase 149)."""
    if not value:
        return value
    decrypted = decrypt(value)
    return decrypted if decrypted is not None else value
