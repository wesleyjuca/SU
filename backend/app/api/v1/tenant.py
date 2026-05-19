"""Endpoints de configuração de tenant/escritório."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Any
import uuid

from app.db.base import get_db
from app.dependencies import get_current_user, require_role
from app.models.user import User
from app.models.tenant import Tenant, TenantConfig
from app.core.tenant import get_tenant_config, invalidate_tenant_cache, DEFAULT_TENANT_SLUG

router = APIRouter(prefix="/tenant", tags=["tenant"])


class ThemeResponse(BaseModel):
    primary_color: str
    secondary_color: str
    accent_color: str
    logo_url: str | None
    logo_dark_url: str | None
    favicon_url: str | None
    app_name: str


class TenantConfigResponse(ThemeResponse):
    tenant_id: str | None
    slug: str
    name: str
    plan: str
    nav_config: list
    dashboard_widgets: list
    modules_enabled: dict
    document_templates: dict
    custom_css: str | None


class BrandingUpdate(BaseModel):
    primary_color: str | None = None
    secondary_color: str | None = None
    accent_color: str | None = None
    logo_url: str | None = None
    logo_dark_url: str | None = None
    favicon_url: str | None = None
    app_name: str | None = None


class ModulesUpdate(BaseModel):
    processos: bool | None = None
    peticoes: bool | None = None
    clientes: bool | None = None
    financeiro: bool | None = None
    agentes: bool | None = None
    visual_law: bool | None = None


class NavUpdate(BaseModel):
    nav_config: list[dict[str, Any]]


@router.get("/theme", response_model=ThemeResponse)
async def get_theme(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    config = await get_tenant_config(db)
    return ThemeResponse(
        primary_color=config["primary_color"],
        secondary_color=config["secondary_color"],
        accent_color=config["accent_color"],
        logo_url=config["logo_url"],
        logo_dark_url=config["logo_dark_url"],
        favicon_url=config["favicon_url"],
        app_name=config["app_name"],
    )


@router.get("/config", response_model=TenantConfigResponse)
async def get_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    config = await get_tenant_config(db)
    return TenantConfigResponse(**config)


@router.put("/branding", response_model=ThemeResponse)
async def update_branding(
    body: BrandingUpdate,
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    config = await _get_or_create_config(db)
    updates = body.model_dump(exclude_none=True)
    for field, value in updates.items():
        setattr(config, field, value)
    await db.flush()
    await invalidate_tenant_cache(DEFAULT_TENANT_SLUG)
    return ThemeResponse(
        primary_color=config.primary_color,
        secondary_color=config.secondary_color,
        accent_color=config.accent_color,
        logo_url=config.logo_url,
        logo_dark_url=config.logo_dark_url,
        favicon_url=config.favicon_url,
        app_name=config.app_name,
    )


@router.put("/modules")
async def update_modules(
    body: ModulesUpdate,
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    config = await _get_or_create_config(db)
    current = config.modules_enabled or {}
    updates = body.model_dump(exclude_none=True)
    config.modules_enabled = {**current, **updates}
    await db.flush()
    await invalidate_tenant_cache(DEFAULT_TENANT_SLUG)
    return {"modules_enabled": config.modules_enabled}


@router.put("/nav")
async def update_nav(
    body: NavUpdate,
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    config = await _get_or_create_config(db)
    config.nav_config = body.nav_config
    await db.flush()
    await invalidate_tenant_cache(DEFAULT_TENANT_SLUG)
    return {"nav_config": config.nav_config}


async def _get_or_create_config(db: AsyncSession) -> TenantConfig:
    result = await db.execute(
        select(Tenant).where(Tenant.slug == DEFAULT_TENANT_SLUG, Tenant.is_active == True)
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        tenant = Tenant(name="Almeida, Freire & Jucá Advogados", slug=DEFAULT_TENANT_SLUG, plan="ENTERPRISE")
        db.add(tenant)
        await db.flush()

    result2 = await db.execute(select(TenantConfig).where(TenantConfig.tenant_id == tenant.id))
    config = result2.scalar_one_or_none()

    if not config:
        config = TenantConfig(tenant_id=tenant.id)
        db.add(config)
        await db.flush()

    return config
