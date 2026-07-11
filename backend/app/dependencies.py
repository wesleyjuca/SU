from fastapi import Depends, Request
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
    request: Request,
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

    # Atribui o autor na request.state para o AuditMiddleware registrar a trilha
    # LGPD com user_id/tenant_id (o middleware roda após a rota, então já estará setado).
    request.state.user_id = user.id
    request.state.tenant_id = user.tenant_id
    return user


async def get_current_staff(current_user: User = Depends(get_current_user)) -> User:
    """Impede que usuários com role CLIENT acessem endpoints internos."""
    if current_user.role == "CLIENT":
        raise ForbiddenError("Acesso restrito a colaboradores do escritório")
    return current_user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    # SUPERADMIN (dono da plataforma) é superconjunto de ADMIN.
    if current_user.role not in ("ADMIN", "SOCIO", "SUPERADMIN"):
        raise ForbiddenError("Permissão de administrador necessária")
    return current_user


def require_role(*roles: str):
    async def _check(current_user: User = Depends(get_current_user)) -> User:
        # SUPERADMIN sempre passa — é superconjunto de qualquer papel do escritório.
        if current_user.role != "SUPERADMIN" and current_user.role not in roles:
            raise ForbiddenError(f"Perfil necessário: {', '.join(roles)}")
        return current_user
    return _check


_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


async def require_active_tenant(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Bloqueio suave: escritório SUSPENSO por pendência financeira não escreve.

    Leitura (GET/HEAD/OPTIONS) sempre passa; só métodos de escrita são barrados.
    SUPERADMIN (dono da plataforma) nunca é bloqueado. Ausência de conta de
    cobrança ou qualquer status != SUSPENSO também passa.
    """
    if current_user.role == "SUPERADMIN" or request.method not in _WRITE_METHODS:
        return current_user
    if not current_user.tenant_id:
        return current_user

    from app.models.billing import BillingAccount
    status = (await db.execute(
        select(BillingAccount.status).where(BillingAccount.tenant_id == current_user.tenant_id)
    )).scalar_one_or_none()
    if status == "SUSPENSO":
        raise ForbiddenError(
            "Escritório suspenso por pendência financeira. As alterações estão "
            "bloqueadas até a regularização — contate o administrador da plataforma."
        )
    return current_user
