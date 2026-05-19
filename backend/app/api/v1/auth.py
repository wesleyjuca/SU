from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, timedelta
import hashlib

from app.db.base import get_db
from app.models.user import User, Session
from app.core.security import verify_password, create_access_token, create_refresh_token, hash_token, decode_access_token
from app.core.exceptions import UnauthorizedError
from app.config import settings
from app.dependencies import bearer_scheme
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


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email, User.is_active == True))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise UnauthorizedError("E-mail ou senha incorretos")

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

    user_result = await db.execute(select(User).where(User.id == session.user_id, User.is_active == True))
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
