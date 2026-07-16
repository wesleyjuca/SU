from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, timedelta

from app.db.base import get_db
from app.models.user import User, Session
from app.core.security import verify_password, hash_password, create_access_token, create_refresh_token, hash_token, decode_access_token
from app.core.exceptions import UnauthorizedError
from app.config import settings
from app.dependencies import bearer_scheme, get_current_user
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class RefreshRequest(BaseModel):
    refresh_token: str


_LOGIN_MAX_FAILS = 8       # tentativas erradas antes de bloquear
_LOGIN_WINDOW_SEC = 900    # janela de 15 min


async def _login_rl_key(request: Request, email: str) -> str:
    ip = request.client.host if request.client else "?"
    return f"login_fail:{ip}:{email.lower()}"


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    # Rate-limit por IP+email (anti brute-force). Sem Redis, vira no-op.
    from app.db.redis import get_redis
    from fastapi import HTTPException
    redis = await get_redis()
    rl_key = await _login_rl_key(request, body.email)
    if redis:
        try:
            fails = int(await redis.get(rl_key) or 0)
        except Exception:
            fails = 0
        if fails >= _LOGIN_MAX_FAILS:
            raise HTTPException(status_code=429, detail="Muitas tentativas. Aguarde alguns minutos e tente novamente.")

    result = await db.execute(select(User).where(User.email == body.email, User.is_active.is_(True)))
    user = result.scalar_one_or_none()

    ok = False
    if user:
        try:
            ok = verify_password(body.password, user.hashed_password)
        except Exception:
            ok = False
    if not user or not ok:
        if redis:
            try:
                n = await redis.incr(rl_key)
                if n == 1:
                    await redis.expire(rl_key, _LOGIN_WINDOW_SEC)
            except Exception:
                pass
        # Motivo detalhado só no log (mensagem ao usuário permanece genérica).
        import structlog
        structlog.get_logger().warning(
            "login_failed",
            email=body.email,
            reason="user_not_found_or_inactive" if not user else "wrong_password",
        )
        raise UnauthorizedError("E-mail ou senha incorretos")

    if redis:
        try:
            await redis.delete(rl_key)  # login OK — zera o contador de falhas
        except Exception:
            pass

    user.last_login_at = datetime.now(timezone.utc)
    access_token = create_access_token(str(user.id), user.role)
    refresh_token_str, token_hash = create_refresh_token(str(user.id))

    session = Session(
        user_id=user.id,
        token_hash=token_hash,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(session)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token_str,
        user={
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "oab_number": user.oab_number,
        },
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    token_hash = hash_token(body.refresh_token)

    result = await db.execute(
        select(Session).where(
            Session.token_hash == token_hash,
            Session.expires_at > datetime.now(timezone.utc),
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise UnauthorizedError("Refresh token inválido ou expirado")

    user_result = await db.execute(select(User).where(User.id == session.user_id, User.is_active.is_(True)))
    user = user_result.scalar_one_or_none()
    if not user:
        raise UnauthorizedError()

    new_access = create_access_token(str(user.id), user.role)
    new_refresh_str, new_hash = create_refresh_token(str(user.id))

    # Rotacionar refresh token
    await db.delete(session)
    new_session = Session(
        user_id=user.id,
        token_hash=new_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(new_session)

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh_str,
        user={"id": str(user.id), "email": user.email, "full_name": user.full_name, "role": user.role},
    )


@router.post("/logout")
async def logout(
    body: RefreshRequest,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    token_hash = hash_token(body.refresh_token)
    result = await db.execute(select(Session).where(Session.token_hash == token_hash))
    session = result.scalar_one_or_none()
    if session:
        await db.delete(session)

    # Blacklist the access token via Redis
    if credentials:
        try:
            payload = decode_access_token(credentials.credentials)
            jti = payload.get("jti")
            exp = payload.get("exp")
            if jti and exp:
                remaining = max(0, int(exp - datetime.now(timezone.utc).timestamp()))
                from app.db.redis import get_redis
                redis = await get_redis()
                if redis and remaining > 0:
                    await redis.setex(f"blacklist:{jti}", remaining, "1")
        except Exception:
            pass

    return {"message": "Logout realizado com sucesso"}


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


@router.patch("/password")
async def change_password(
    body: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(body.current_password, current_user.hashed_password):
        raise UnauthorizedError("Senha atual incorreta")
    import re as _re
    _PWD_RE = _re.compile(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&_\-#])[A-Za-z\d@$!%*?&_\-#]{8,}$')
    if not _PWD_RE.match(body.new_password):
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Senha deve ter 8+ caracteres com maiúscula, minúscula, número e símbolo (@$!%*?&_-#)")
    current_user.hashed_password = hash_password(body.new_password)
    await db.flush()
    return {"message": "Senha alterada com sucesso"}
