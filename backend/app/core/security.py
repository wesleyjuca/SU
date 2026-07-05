from datetime import datetime, timedelta, timezone
from typing import Any
import hashlib
import secrets
import uuid

import bcrypt
from jose import jwt

from app.config import settings

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
    try:
        from app.db.redis import get_redis
        redis = await get_redis()
        if redis:
            return bool(await redis.exists(f"blacklist:{jti}"))
    except Exception:
        pass
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
