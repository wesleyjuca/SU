from datetime import datetime, timedelta, timezone
from typing import Any
import hashlib
import secrets
import uuid

import bcrypt
import structlog
from jose import jwt

from app.config import settings

log = structlog.get_logger()

ROLES = {
    "ADMIN": {"level": 100, "permissions": ["*"]},
    "SOCIO": {"level": 80, "permissions": ["clients.*", "processes.*", "documents.*", "agents.*", "approvals.*", "financial.*"]},
    "ADVOGADO": {"level": 60, "permissions": ["clients.read", "clients.write", "processes.*", "documents.*", "agents.trigger", "approvals.read"]},
    "PARALEGAL": {"level": 40, "permissions": ["clients.read", "processes.read", "documents.read"]},
    "ASSISTENTE": {"level": 20, "permissions": ["clients.read", "processes.read"]},
}


def hash_password(password: str) -> str:
    # bcrypt opera em no máximo 72 bytes — trunca para evitar ValueError no bcrypt 5.x
    pwd = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pwd, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    # Retorna False (em vez de lançar) em hash malformado → 401 legítimo, nunca 500
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str | Any, role: str, extra: dict | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(subject),
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),
        "type": "access",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str | Any) -> tuple[str, str]:
    """Returns (token_str, token_hash_for_db)."""
    token = secrets.token_urlsafe(64)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    return token, token_hash


def decode_access_token(token: str) -> dict:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    return payload


async def is_token_blacklisted(jti: str) -> bool:
    """Fail-open de propósito (indisponibilidade do Redis nunca pode travar
    login/toda a API — mesmo princípio de `task_lock.py`/`incrementar_com_janela`).

    Achado da rodada pós-166a43c: até aqui, "Redis não configurado" (estado
    degradado documentado, `get_redis()` devolve `None`) e "Redis configurado
    mas a chamada falhou de verdade" (erro de conexão/timeout num Redis que
    deveria estar de pé) caíam no MESMO `except Exception: pass` — o 2º caso
    é logado agora, o 1º continua silencioso (não é uma falha, é config).
    Sem isso, um erro transitório de Redis fazia um token JÁ deslogado (na
    blacklist) continuar sendo aceito, em silêncio, por toda a API
    autenticada (`get_current_user`/`ws.py`), não só WebSocket."""
    from app.db.redis import get_redis
    try:
        redis = await get_redis()
    except Exception as exc:
        log.warning("blacklist_check_redis_unavailable", jti=jti[:8], error=str(exc))
        return False
    if not redis:
        return False
    try:
        return bool(await redis.exists(f"blacklist:{jti}"))
    except Exception as exc:
        log.warning("blacklist_check_failed", jti=jti[:8], error=str(exc))
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def has_permission(role: str, resource: str, action: str) -> bool:
    role_data = ROLES.get(role, {})
    perms = role_data.get("permissions", [])
    if "*" in perms:
        return True
    target = f"{resource}.{action}"
    wildcard = f"{resource}.*"
    return target in perms or wildcard in perms
