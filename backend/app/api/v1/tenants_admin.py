"""Provisionamento SaaS — gestão de escritórios e unidades (somente SUPERADMIN).

Cada escritório é um `Tenant` isolado. Unidades da mesma banca são tenants
filhos (`parent_tenant_id`) — os dados continuam isolados por `tenant_id`; o
vínculo serve para agrupamento e relatórios consolidados futuros (P3).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, EmailStr
import uuid
import re
import secrets
import string

from app.db.base import get_db
from app.dependencies import require_role
from app.models.user import User
from app.models.tenant import Tenant, TenantConfig
from app.core.security import hash_password
from app.core.tenant import DEFAULT_TENANT_SLUG, invalidate_tenant_cache

router = APIRouter(prefix="/tenants", tags=["tenants-admin"])

_ALPHABET = string.ascii_letters + string.digits + "!@#$"

# Tiers de plano — limites derivados automaticamente (0 = ilimitado).
# Custom override permitido: informe max_users explicitamente no create/patch.
PLAN_TIERS: dict[str, dict[str, int]] = {
    "STANDARD": {"max_users": 10, "max_storage_gb": 50},
    "PRO": {"max_users": 25, "max_storage_gb": 200},
    "ENTERPRISE": {"max_users": 0, "max_storage_gb": 0},  # ilimitado + filiais self-serve
    # Fase 170 — exclusivo do tenant raiz da plataforma (slug="afj"); nunca
    # oferecido/aceito na criação ou edição de um escritório-cliente comum
    # (ver _provision() e update_tenant() abaixo).
    "MAXIMO": {"max_users": 0, "max_storage_gb": 0},
}


def _tier_limits(plan: str | None) -> dict[str, int] | None:
    return PLAN_TIERS.get((plan or "").strip().upper())


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return base or "escritorio"


async def _unique_slug(db: AsyncSession, name: str) -> str:
    """Slug único a partir do nome (sufixo numérico em caso de colisão)."""
    base = _slugify(name)
    slug = base
    i = 2
    while (await db.execute(select(Tenant.id).where(Tenant.slug == slug))).scalar_one_or_none():
        slug = f"{base}-{i}"
        i += 1
    return slug


class TenantCreate(BaseModel):
    name: str
    plan: str = "STANDARD"
    max_users: int | None = None   # None → derivado do tier do plano
    admin_email: EmailStr
    admin_name: str


class UnitCreate(BaseModel):
    name: str
    unit_label: str
    plan: str = "STANDARD"
    max_users: int | None = None   # None → derivado do tier do plano
    admin_email: EmailStr
    admin_name: str


class TenantPatch(BaseModel):
    is_active: bool | None = None
    plan: str | None = None
    max_users: int | None = None


async def _provision(
    db: AsyncSession, body, *, parent_tenant_id: uuid.UUID | None, unit_label: str | None,
) -> dict:
    """Cria Tenant + TenantConfig + usuário ADMIN inicial. Retorna as credenciais."""
    email = str(body.admin_email).lower().strip()
    if (await db.execute(select(User.id).where(User.email == email))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Já existe um usuário com este e-mail.")

    # Fase 170 — "MAXIMO" é exclusivo do tenant raiz da plataforma, nunca de
    # um escritório-cliente provisionado por aqui.
    if (body.plan or "").strip().upper() == "MAXIMO":
        raise HTTPException(status_code=422, detail="O plano Máximo é exclusivo do escritório raiz da plataforma.")

    slug = await _unique_slug(db, body.name)
    tier = _tier_limits(body.plan) or PLAN_TIERS["STANDARD"]
    tenant = Tenant(
        id=uuid.uuid4(), name=body.name.strip(), slug=slug,
        plan=body.plan,
        max_users=body.max_users if body.max_users is not None else tier["max_users"],
        max_storage_gb=tier["max_storage_gb"],
        is_active=True,
        parent_tenant_id=parent_tenant_id, unit_label=unit_label,
    )
    db.add(tenant)
    db.add(TenantConfig(id=uuid.uuid4(), tenant_id=tenant.id))

    temp_password = "".join(secrets.choice(_ALPHABET) for _ in range(12))
    db.add(User(
        id=uuid.uuid4(), email=email, full_name=body.admin_name.strip(),
        role="ADMIN", hashed_password=hash_password(temp_password),
        is_active=True, tenant_id=tenant.id,
    ))
    await db.commit()
    return {
        "tenant_id": str(tenant.id),
        "name": tenant.name,
        "slug": tenant.slug,
        "admin_email": email,
        "temp_password": temp_password,
        "message": "Escritório provisionado. Entregue a senha temporária ao administrador.",
    }


@router.get("")
async def list_tenants(
    current_user: User = Depends(require_role("SUPERADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Lista todos os escritórios/unidades com plano, status e nº de usuários."""
    tenants = (await db.execute(select(Tenant).order_by(Tenant.created_at))).scalars().all()

    counts = dict((await db.execute(
        select(User.tenant_id, func.count(User.id)).group_by(User.tenant_id)
    )).all())
    names = {t.id: t.name for t in tenants}

    return [
        {
            "id": str(t.id),
            "name": t.name,
            "slug": t.slug,
            "plan": t.plan,
            "isento": t.isento,
            "is_active": t.is_active,
            "max_users": t.max_users,
            "users": int(counts.get(t.id, 0)),
            "is_unit": t.parent_tenant_id is not None,
            "unit_label": t.unit_label,
            "parent_name": names.get(t.parent_tenant_id) if t.parent_tenant_id else None,
            "is_root": t.slug == DEFAULT_TENANT_SLUG,
        }
        for t in tenants
    ]


@router.post("", status_code=201)
async def create_tenant(
    body: TenantCreate,
    current_user: User = Depends(require_role("SUPERADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Cria um novo escritório (cliente SaaS) com seu administrador inicial."""
    return await _provision(db, body, parent_tenant_id=None, unit_label=None)


@router.post("/{tenant_id}/units", status_code=201)
async def create_unit(
    tenant_id: str,
    body: UnitCreate,
    current_user: User = Depends(require_role("SUPERADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Cria uma unidade (filial) de uma banca existente."""
    parent = (await db.execute(
        select(Tenant).where(Tenant.id == uuid.UUID(tenant_id))
    )).scalar_one_or_none()
    if not parent:
        raise HTTPException(status_code=404, detail="Escritório (banca-mãe) não encontrado.")
    if parent.parent_tenant_id is not None:
        raise HTTPException(status_code=422, detail="Uma unidade não pode ter sub-unidades (apenas 1 nível).")
    return await _provision(db, body, parent_tenant_id=parent.id, unit_label=body.unit_label.strip())


@router.patch("/{tenant_id}")
async def update_tenant(
    tenant_id: str,
    body: TenantPatch,
    current_user: User = Depends(require_role("SUPERADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Ativa/desativa o escritório e ajusta plano/limite de usuários."""
    tenant = (await db.execute(
        select(Tenant).where(Tenant.id == uuid.UUID(tenant_id))
    )).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Escritório não encontrado.")

    updates = body.model_dump(exclude_none=True)
    if updates.get("is_active") is False and tenant.slug == DEFAULT_TENANT_SLUG:
        raise HTTPException(status_code=422, detail="O escritório raiz da plataforma não pode ser desativado.")

    # Fase 170 — "MAXIMO" é fixo pro tenant raiz (garantido pelo backfill em
    # app/core/events.py) e proibido pra qualquer outro escritório.
    if "plan" in updates:
        novo_plano = (updates["plan"] or "").strip().upper()
        if tenant.slug == DEFAULT_TENANT_SLUG and novo_plano != "MAXIMO":
            raise HTTPException(status_code=422, detail="O escritório raiz da plataforma sempre usa o plano Máximo.")
        if tenant.slug != DEFAULT_TENANT_SLUG and novo_plano == "MAXIMO":
            raise HTTPException(status_code=422, detail="O plano Máximo é exclusivo do escritório raiz da plataforma.")

    # Mudou o plano sem informar max_users? Re-deriva os limites do tier.
    if "plan" in updates and "max_users" not in updates:
        tier = _tier_limits(updates["plan"])
        if tier:
            updates["max_users"] = tier["max_users"]
            updates["max_storage_gb"] = tier["max_storage_gb"]

    for field, value in updates.items():
        setattr(tenant, field, value)
    await db.commit()
    await invalidate_tenant_cache(tenant.slug)
    return {"message": "Escritório atualizado.", "is_active": tenant.is_active, "plan": tenant.plan}
