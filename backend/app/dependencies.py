from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError

from app.db.base import get_db
from app.core.security import decode_access_token, is_token_blacklisted
from app.core.exceptions import UnauthorizedError, ForbiddenError
from app.models.user import User
from sqlalchemy import select

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise UnauthorizedError("Token de autenticação não fornecido")
    try:
        payload = decode_access_token(credentials.credentials)
        user_id: str = payload.get("sub")
        jti: str = payload.get("jti", "")
        if not user_id:
            raise UnauthorizedError()
        if jti and await is_token_blacklisted(jti):
            raise UnauthorizedError("Token revogado")
    except JWTError:
        raise UnauthorizedError("Token inválido ou expirado")

    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise UnauthorizedError("Usuário não encontrado ou inativo")
    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in ("ADMIN", "SOCIO"):
        raise ForbiddenError("Permissão de administrador necessária")
    return current_user


def require_role(*roles: str):
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise ForbiddenError(f"Perfil necessário: {', '.join(roles)}")
        return current_user
    return _check
