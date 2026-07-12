"""Endpoints de configuração de tenant/escritório."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Any

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
    office_name: str | None = None
    slogan: str | None = None


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
    office_name: str | None = None  # armazenado em metadata.office_name
    slogan: str | None = None       # armazenado em metadata.slogan


class ModulesUpdate(BaseModel):
    processos: bool | None = None
    peticoes: bool | None = None
    clientes: bool | None = None
    financeiro: bool | None = None
    agentes: bool | None = None
    visual_law: bool | None = None
    google_workspace: bool | None = None   # integração opcional por escritório (opt-in do ADMIN)


class NavUpdate(BaseModel):
    nav_config: list[dict[str, Any]]


@router.get("/theme", response_model=ThemeResponse)
async def get_theme(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    config = await get_tenant_config(db, tenant_slug=await _resolve_tenant_slug(db, current_user))
    meta = config.get("metadata") or {}
    return ThemeResponse(
        primary_color=config["primary_color"],
        secondary_color=config["secondary_color"],
        accent_color=config["accent_color"],
        logo_url=config["logo_url"],
        logo_dark_url=config["logo_dark_url"],
        favicon_url=config["favicon_url"],
        app_name=config["app_name"],
        office_name=meta.get("office_name"),
        slogan=meta.get("slogan"),
    )


@router.get("/config", response_model=TenantConfigResponse)
async def get_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    config = await get_tenant_config(db, tenant_slug=await _resolve_tenant_slug(db, current_user))
    return TenantConfigResponse(**config)


@router.put("/branding", response_model=ThemeResponse)
async def update_branding(
    body: BrandingUpdate,
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    tenant, config = await _get_or_create_config(db, current_user)
    updates = body.model_dump(exclude_none=True)
    meta_updates = {}
    for field in ("office_name", "slogan"):
        if field in updates:
            meta_updates[field] = updates.pop(field)
    for field, value in updates.items():
        setattr(config, field, value)
    if meta_updates:
        current_meta = config.extra_data or {}
        config.extra_data = {**current_meta, **meta_updates}
    await db.flush()
    await invalidate_tenant_cache(tenant.slug)
    meta = config.extra_data or {}
    return ThemeResponse(
        primary_color=config.primary_color,
        secondary_color=config.secondary_color,
        accent_color=config.accent_color,
        logo_url=config.logo_url,
        logo_dark_url=config.logo_dark_url,
        favicon_url=config.favicon_url,
        app_name=config.app_name,
        office_name=meta.get("office_name"),
        slogan=meta.get("slogan"),
    )


@router.put("/modules")
async def update_modules(
    body: ModulesUpdate,
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    tenant, config = await _get_or_create_config(db, current_user)
    current = config.modules_enabled or {}
    updates = body.model_dump(exclude_none=True)
    config.modules_enabled = {**current, **updates}
    await db.flush()
    await invalidate_tenant_cache(tenant.slug)
    return {"modules_enabled": config.modules_enabled}


@router.post("/logo-upload")
async def upload_logo(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Recebe arquivo de imagem, converte para base64 data URL e salva como logo_url."""
    import base64
    ALLOWED = {"image/png", "image/jpeg", "image/svg+xml", "image/webp"}
    if file.content_type not in ALLOWED:
        raise HTTPException(status_code=400, detail="Tipo não suportado. Use PNG, JPG, SVG ou WebP.")
    contents = await file.read()
    if len(contents) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Arquivo muito grande. Máximo 2MB.")
    b64 = base64.b64encode(contents).decode()
    data_url = f"data:{file.content_type};base64,{b64}"
    tenant, config = await _get_or_create_config(db, current_user)
    config.logo_url = data_url
    await db.flush()
    await invalidate_tenant_cache(tenant.slug)
    return {"logo_url": data_url}


@router.post("/favicon-upload")
async def upload_favicon(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Recebe arquivo de favicon, converte para base64 data URL e salva como favicon_url."""
    import base64
    ALLOWED = {"image/png", "image/x-icon", "image/vnd.microsoft.icon", "image/svg+xml"}
    if file.content_type not in ALLOWED:
        raise HTTPException(status_code=400, detail="Tipo não suportado. Use PNG, ICO ou SVG.")
    contents = await file.read()
    if len(contents) > 512 * 1024:
        raise HTTPException(status_code=400, detail="Arquivo muito grande. Máximo 512KB.")
    b64 = base64.b64encode(contents).decode()
    ct = file.content_type if file.content_type != "image/x-icon" else "image/vnd.microsoft.icon"
    data_url = f"data:{ct};base64,{b64}"
    tenant, config = await _get_or_create_config(db, current_user)
    config.favicon_url = data_url
    await db.flush()
    await invalidate_tenant_cache(tenant.slug)
    return {"favicon_url": data_url}


@router.put("/nav")
async def update_nav(
    body: NavUpdate,
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    tenant, config = await _get_or_create_config(db, current_user)
    config.nav_config = body.nav_config
    await db.flush()
    await invalidate_tenant_cache(tenant.slug)
    return {"nav_config": config.nav_config}


async def _resolve_tenant_slug(db: AsyncSession, current_user: User) -> str:
    """Slug do tenant do usuário logado (somente leitura, sem efeitos colaterais)."""
    if current_user.tenant_id:
        slug = (await db.execute(
            select(Tenant.slug).where(Tenant.id == current_user.tenant_id)
        )).scalar_one_or_none()
        if slug:
            return slug
    return DEFAULT_TENANT_SLUG


async def _get_or_create_config(db: AsyncSession, current_user: User) -> tuple[Tenant, TenantConfig]:
    """Resolve (Tenant, TenantConfig) do escritório do usuário logado.

    Resolve pelo `current_user.tenant_id` — cada escritório escreve o SEU próprio
    branding/módulos/timbrado. Só recai no tenant AFJ raiz (bootstrap) quando o
    usuário não tem tenant e o tenant padrão ainda não existe (primeira execução).
    """
    tenant = None
    if current_user.tenant_id:
        tenant = (await db.execute(
            select(Tenant).where(Tenant.id == current_user.tenant_id)
        )).scalar_one_or_none()
    if not tenant:
        tenant = (await db.execute(
            select(Tenant).where(Tenant.slug == DEFAULT_TENANT_SLUG, Tenant.is_active == True)
        )).scalar_one_or_none()
    if not tenant:
        tenant = Tenant(name="Almeida, Freire & Jucá Advogados", slug=DEFAULT_TENANT_SLUG, plan="ENTERPRISE")
        db.add(tenant)
        await db.flush()

    config = (await db.execute(
        select(TenantConfig).where(TenantConfig.tenant_id == tenant.id)
    )).scalar_one_or_none()
    if not config:
        config = TenantConfig(tenant_id=tenant.id)
        db.add(config)
        await db.flush()

    return tenant, config


# ─── Timbrado dos documentos (padrão do escritório) ──────────────────────────
class LetterheadUpdate(BaseModel):
    office_name: str | None = None
    address: str | None = None
    contact: str | None = None
    oab: str | None = None
    footer: str | None = None
    use_logo: bool = True


@router.get("/letterhead")
async def get_letterhead(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Timbrado configurado do escritório (usado nos PDFs gerados)."""
    _, config = await _get_or_create_config(db, current_user)
    lh = (config.document_templates or {}).get("letterhead", {})
    return {
        "office_name": lh.get("office_name"),
        "address": lh.get("address"),
        "contact": lh.get("contact"),
        "oab": lh.get("oab"),
        "footer": lh.get("footer"),
        "use_logo": lh.get("use_logo", True),
        "has_logo": bool(config.logo_url),
    }


@router.put("/letterhead")
async def update_letterhead(
    body: LetterheadUpdate,
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Salva o timbrado do escritório em TenantConfig.document_templates (JSONB)."""
    tenant, config = await _get_or_create_config(db, current_user)
    templates = dict(config.document_templates or {})
    templates["letterhead"] = {
        "office_name": (body.office_name or "").strip() or None,
        "address": (body.address or "").strip() or None,
        "contact": (body.contact or "").strip() or None,
        "oab": (body.oab or "").strip() or None,
        "footer": (body.footer or "").strip() or None,
        "use_logo": body.use_logo,
    }
    config.document_templates = templates
    await db.flush()
    await invalidate_tenant_cache(tenant.slug)
    return {"message": "Timbrado salvo", **templates["letterhead"]}


# ─── Feriados forenses locais (complementam o cálculo de prazos) ─────────────
class FeriadoItem(BaseModel):
    data: str          # YYYY-MM-DD
    descricao: str | None = None


class FeriadosUpdate(BaseModel):
    feriados: list[FeriadoItem]


@router.get("/feriados")
async def get_feriados(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Feriados forenses locais do escritório (usados no cálculo de prazos)."""
    _, config = await _get_or_create_config(db, current_user)
    fer = (config.extra_data or {}).get("feriados_forenses", [])
    return {"feriados": fer if isinstance(fer, list) else []}


@router.put("/feriados")
async def update_feriados(
    body: FeriadosUpdate,
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Salva os feriados forenses locais em TenantConfig.extra_data (JSONB)."""
    from datetime import date as _date
    itens = []
    for f in body.feriados:
        try:
            _date.fromisoformat(f.data[:10])
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Data inválida: {f.data} (use AAAA-MM-DD).")
        itens.append({"data": f.data[:10], "descricao": (f.descricao or "").strip() or None})

    tenant, config = await _get_or_create_config(db, current_user)
    meta = dict(config.extra_data or {})
    meta["feriados_forenses"] = itens
    config.extra_data = meta
    await db.flush()
    await invalidate_tenant_cache(tenant.slug)
    return {"feriados": itens}


@router.get("/usage")
async def get_tenant_usage(
    current_user: User = Depends(require_role("ADMIN", "SOCIO")),
    db: AsyncSession = Depends(get_db),
):
    """Plano & Uso do escritório: limites do plano vs consumo real (Admin SaaS)."""
    from sqlalchemy import func
    from datetime import datetime, timezone
    from app.models.document import Document
    from app.models.agent_run import AgentRun

    # Tenant do usuário; fallback para o tenant padrão (mesma lógica do config)
    tenant = None
    if current_user.tenant_id:
        tenant = (await db.execute(
            select(Tenant).where(Tenant.id == current_user.tenant_id)
        )).scalar_one_or_none()
    if not tenant:
        tenant = (await db.execute(
            select(Tenant).where(Tenant.slug == DEFAULT_TENANT_SLUG)
        )).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant não encontrado")

    tid = tenant.id

    usuarios_ativos = (await db.execute(
        select(func.count(User.id)).where(User.tenant_id == tid, User.is_active == True)  # noqa: E712
    )).scalar_one() or 0

    # Estimativa de armazenamento: bytes dos arquivos (base64) + textos no banco
    storage_bytes = (await db.execute(
        select(
            func.coalesce(func.sum(func.length(Document.arquivo_url)), 0)
            + func.coalesce(func.sum(func.length(Document.conteudo_texto)), 0)
            + func.coalesce(func.sum(func.length(Document.conteudo_html)), 0)
        ).where(Document.tenant_id == tid)
    )).scalar_one() or 0

    inicio_mes = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    row = (await db.execute(
        select(
            func.coalesce(func.sum(AgentRun.cost_usd), 0).label("custo"),
            func.coalesce(func.sum(AgentRun.tokens_used), 0).label("tokens"),
            func.count(AgentRun.id).label("execucoes"),
        ).where(AgentRun.tenant_id == tid, AgentRun.started_at >= inicio_mes)
    )).one()

    return {
        "plan": tenant.plan,
        "tenant_name": tenant.name,
        "max_users": tenant.max_users,
        "usuarios_ativos": int(usuarios_ativos),
        "max_storage_gb": tenant.max_storage_gb,
        "storage_mb_estimado": round(storage_bytes / (1024 * 1024), 2),
        "custo_ia_mes_usd": float(row.custo),
        "tokens_mes": int(row.tokens),
        "execucoes_mes": int(row.execucoes),
        "billing": await _billing_summary(db, tenant),
    }


async def _billing_summary(db: AsyncSession, tenant: Tenant) -> dict:
    """Resumo de cobrança do escritório (alimenta banner e Plano & Uso)."""
    from datetime import date
    from app.models.billing import BillingAccount

    # Tenant raiz da plataforma é isento de cobrança.
    if tenant.slug == DEFAULT_TENANT_SLUG:
        return {"status": "ISENTO", "valor_mensal": None, "proximo_vencimento": None, "dias_para_vencimento": None}

    acc = (await db.execute(
        select(BillingAccount).where(BillingAccount.tenant_id == tenant.id)
    )).scalar_one_or_none()
    if not acc:
        return {"status": "NAO_CONFIGURADO", "valor_mensal": None, "proximo_vencimento": None, "dias_para_vencimento": None}

    dias = (acc.proximo_vencimento - date.today()).days if acc.proximo_vencimento else None
    status = acc.status
    # INADIMPLENTE é derivado: vencido e ainda não suspenso (só aviso, não bloqueia).
    if status == "ATIVO" and dias is not None and dias < 0:
        status = "INADIMPLENTE"
    return {
        "status": status,
        "valor_mensal": float(acc.valor_mensal),
        "proximo_vencimento": acc.proximo_vencimento.isoformat() if acc.proximo_vencimento else None,
        "dias_para_vencimento": dias,
    }


@router.get("/billing")
async def get_my_billing(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Situação de cobrança do escritório do usuário (para banner e assinatura).

    Acessível a qualquer usuário staff do tenant — o banner de bloqueio precisa
    aparecer para todos, não só ADMIN.
    """
    tenant = None
    if current_user.tenant_id:
        tenant = (await db.execute(
            select(Tenant).where(Tenant.id == current_user.tenant_id)
        )).scalar_one_or_none()
    if not tenant:
        return {"status": "NAO_CONFIGURADO", "valor_mensal": None, "proximo_vencimento": None, "dias_para_vencimento": None}
    return await _billing_summary(db, tenant)
