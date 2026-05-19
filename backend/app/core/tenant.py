"""Tenant resolution and context management."""
import json
from typing import Callable
from fastapi import Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

log = structlog.get_logger()

DEFAULT_TENANT_SLUG = "afj"
TENANT_CACHE_TTL = 300  # 5 minutes


async def get_tenant_id_from_request(request: Request) -> str | None:
    """Resolve tenant_id from X-Tenant-ID header, subdomain, or default."""
    header = request.headers.get("X-Tenant-ID")
    if header:
        return header
    host = request.headers.get("host", "")
    subdomain = host.split(".")[0] if "." in host else None
    if subdomain and subdomain not in ("www", "api", "localhost"):
        return subdomain
    return None


async def get_tenant_config(db: AsyncSession, tenant_slug: str | None = None) -> dict:
    """Return TenantConfig dict, with Redis cache."""
    from app.models.tenant import Tenant, TenantConfig

    slug = tenant_slug or DEFAULT_TENANT_SLUG
    cache_key = f"tenant_config:{slug}"

    try:
        from app.db.redis import get_redis
        redis = await get_redis()
        if redis:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
    except Exception:
        pass

    result = await db.execute(
        select(Tenant, TenantConfig)
        .join(TenantConfig, TenantConfig.tenant_id == Tenant.id)
        .where(Tenant.slug == slug, Tenant.is_active == True)
    )
    row = result.first()

    if not row:
        return _default_config()

    tenant, config = row
    data = {
        "tenant_id": str(tenant.id),
        "slug": tenant.slug,
        "name": tenant.name,
        "plan": tenant.plan,
        "primary_color": config.primary_color,
        "secondary_color": config.secondary_color,
        "accent_color": config.accent_color,
        "logo_url": config.logo_url,
        "logo_dark_url": config.logo_dark_url,
        "favicon_url": config.favicon_url,
        "app_name": config.app_name,
        "nav_config": config.nav_config or [],
        "dashboard_widgets": config.dashboard_widgets or [],
        "modules_enabled": config.modules_enabled or {},
        "document_templates": config.document_templates or {},
        "custom_css": config.custom_css,
    }

    try:
        from app.db.redis import get_redis
        redis = await get_redis()
        if redis:
            await redis.setex(cache_key, TENANT_CACHE_TTL, json.dumps(data))
    except Exception:
        pass

    return data


async def invalidate_tenant_cache(slug: str) -> None:
    try:
        from app.db.redis import get_redis
        redis = await get_redis()
        if redis:
            await redis.delete(f"tenant_config:{slug}")
    except Exception:
        pass


def _default_config() -> dict:
    return {
        "tenant_id": None,
        "slug": DEFAULT_TENANT_SLUG,
        "name": "Almeida, Freire & Jucá Advogados",
        "plan": "ENTERPRISE",
        "primary_color": "#C9A84C",
        "secondary_color": "#1A1A1A",
        "accent_color": "#F5F0E8",
        "logo_url": None,
        "logo_dark_url": None,
        "favicon_url": None,
        "app_name": "AFJ CORE",
        "nav_config": [],
        "dashboard_widgets": [],
        "modules_enabled": {
            "processos": True,
            "peticoes": True,
            "clientes": True,
            "financeiro": True,
            "agentes": True,
            "visual_law": True,
        },
        "document_templates": {},
        "custom_css": None,
    }


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Injects tenant_slug into request.state for downstream handlers."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        tenant_id_or_slug = await get_tenant_id_from_request(request)
        request.state.tenant_slug = tenant_id_or_slug or DEFAULT_TENANT_SLUG
        response = await call_next(request)
        return response
