from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from pydantic import BaseModel, EmailStr
from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.core.security import hash_password
import uuid
import secrets
import string
from datetime import datetime, timezone

router = APIRouter(prefix="/users", tags=["users"])


def _require_admin(current_user: User) -> None:
    if current_user.role not in ("ADMIN", "SUPERADMIN"):
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")


class ProfileUpdate(BaseModel):
    full_name: str | None = None


class UserInvite(BaseModel):
    email: EmailStr
    full_name: str
    role: str = "ASSISTENTE"


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    oab_number: str | None = None
    oab_uf: str | None = None


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "full_name": current_user.full_name,
        "email": current_user.email,
        "role": current_user.role,
        "is_active": current_user.is_active,
        "tenant_id": str(current_user.tenant_id) if current_user.tenant_id else None,
        "oab_number": current_user.oab_number,
        "oab_uf": current_user.oab_uf,
    }


@router.put("/me")
async def update_me(
    body: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.full_name is not None:
        current_user.full_name = body.full_name
    await db.commit()
    return {"message": "Perfil atualizado"}


@router.get("")
async def list_users(
    search: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    query = select(User).where(User.tenant_id == current_user.tenant_id)
    if search:
        query = query.where(
            or_(User.full_name.ilike(f"%{search}%"), User.email.ilike(f"%{search}%"))
        )
    if role:
        query = query.where(User.role == role)
    if is_active is not None:
        query = query.where(User.is_active == is_active)
    query = query.order_by(User.full_name).limit(limit).offset(offset)
    result = await db.execute(query)
    users = result.scalars().all()
    return [
        {
            "id": str(u.id),
            "full_name": u.full_name,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "oab_number": u.oab_number,
            "oab_uf": u.oab_uf,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]


@router.post("/invite", status_code=201)
async def invite_user(
    body: UserInvite,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="E-mail já cadastrado")

    alphabet = string.ascii_letters + string.digits + "!@#$"
    temp_password = "".join(secrets.choice(alphabet) for _ in range(12))

    user = User(
        id=uuid.uuid4(),
        email=body.email,
        full_name=body.full_name,
        role=body.role,
        hashed_password=hash_password(temp_password),
        is_active=True,
        tenant_id=current_user.tenant_id,
    )
    db.add(user)
    await db.commit()
    return {"id": str(user.id), "temp_password": temp_password, "message": "Usuário convidado com sucesso"}


@router.put("/{user_id}")
async def update_user(
    user_id: str,
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)

    result = await db.execute(
        select(User).where(User.id == uuid.UUID(user_id), User.tenant_id == current_user.tenant_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(user, field, value)

    await db.commit()
    return {"message": "Usuário atualizado"}


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Gera nova senha temporária para o usuário (apenas ADMIN)."""
    _require_admin(current_user)

    result = await db.execute(
        select(User).where(User.id == uuid.UUID(user_id), User.tenant_id == current_user.tenant_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    alphabet = string.ascii_letters + string.digits + "!@#$"
    new_password = "".join(secrets.choice(alphabet) for _ in range(12))
    user.hashed_password = hash_password(new_password)
    await db.commit()
    return {"temp_password": new_password, "message": "Senha resetada com sucesso"}


@router.get("/{user_id}/activity")
async def get_user_activity(
    user_id: str,
    limit: int = Query(default=20, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retorna histórico de ações do usuário via AuditLog."""
    _require_admin(current_user)
    from app.models.audit_log import AuditLog
    result = await db.execute(
        select(AuditLog)
        .where(
            AuditLog.user_id == uuid.UUID(user_id),
            AuditLog.tenant_id == current_user.tenant_id,
        )
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
    )
    logs = result.scalars().all()
    return [
        {
            "timestamp": l.timestamp.isoformat(),
            "action": l.action,
            "resource_type": l.resource_type,
            "resource_id": str(l.resource_id) if l.resource_id else None,
            "success": l.success,
            "error_detail": l.error_detail,
            "ip_address": l.ip_address,
        }
        for l in logs
    ]
