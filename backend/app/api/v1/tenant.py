"""Endpoints de configuração de tenant/escritório."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr, field_validator
from typing import Any

from app.db.base import get_db
from app.dependencies import get_current_user, require_role
from app.models.user import User
from app.models.tenant import Tenant, TenantConfig
from app.core.tenant import get_tenant_config, invalidate_tenant_cache, DEFAULT_TENANT_SLUG

# Fase 143 — cap defensivo pra evitar que PUT /tenant/branding (campo de
# texto livre, sem upload) aceite um data URL base64 de tamanho arbitrário
# — os endpoints de upload dedicados já capeiam em 2MB/512KB antes de
# base64-codificar; esse valor dá folga generosa acima disso.
_MAX_BRANDING_STRING_LEN = 4_000_000

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
    is_demo: bool = False


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

    @field_validator("logo_url", "logo_dark_url", "favicon_url")
    @classmethod
    def _validar_tamanho(cls, v):
        if v and len(v) > _MAX_BRANDING_STRING_LEN:
            raise ValueError(f"Valor excede o tamanho máximo permitido ({_MAX_BRANDING_STRING_LEN} caracteres).")
        return v


class ModulesUpdate(BaseModel):
    processos: bool | None = None
    peticoes: bool | None = None
    clientes: bool | None = None
    financeiro: bool | None = None
    agentes: bool | None = None
    visual_law: bool | None = None
    google_workspace: bool | None = None   # integração opcional por escritório (opt-in do ADMIN)
    google_drive_doutrina: bool | None = None  # Fase 138.2 — idem, pasta de doutrina do Drive


class NavUpdate(BaseModel):
    nav_config: list[dict[str, Any]]


async def _resolve_cached_logo_url(config: dict) -> str | None:
    """Fase 143 — `get_tenant_config()` cacheia `logo_storage_key` (valor
    estável, seguro por até TENANT_CACHE_TTL), nunca uma URL calculada. A
    presigned URL de verdade é gerada aqui, fresca a cada request (cálculo
    local, sem round-trip de rede) — evita servir uma URL expirada a partir
    do cache."""
    storage_key = config.get("logo_storage_key")
    if not storage_key:
        return config.get("logo_url")
    from app.integrations import object_storage
    try:
        return await object_storage.generate_presigned_url(storage_key, expires_in=3600)
    except object_storage.ObjectStorageError:
        return None


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
        logo_url=await _resolve_cached_logo_url(config),
        logo_dark_url=config["logo_dark_url"],
        favicon_url=config["favicon_url"],
        app_name=config["app_name"],
        office_name=meta.get("office_name"),
        slogan=meta.get("slogan"),
        is_demo=bool(config.get("is_demo", False)),
    )


@router.get("/config", response_model=TenantConfigResponse)
async def get_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    config = await get_tenant_config(db, tenant_slug=await _resolve_tenant_slug(db, current_user))
    config = {**config, "logo_url": await _resolve_cached_logo_url(config)}
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
    if "logo_url" in updates:
        # Fase 143 — logo_url colado à mão (URL externa literal) tem
        # precedência sobre um logo migrado pro S3; zera a storage key pra
        # não ficar uma ambiguidade entre os 2 caminhos.
        config.logo_storage_key = None
        config.logo_mimetype = None
    if meta_updates:
        current_meta = config.extra_data or {}
        config.extra_data = {**current_meta, **meta_updates}
        # Fase 232 — sincroniza o nome do timbrado (document_templates.
        # letterhead.office_name) com "Nome do Escritório", a menos que já
        # tenha sido personalizado explicitamente no próprio timbrado.
        # Não confundir com "Nome do Sistema" (app_name, branding do
        # produto) — conceito diferente, não entra nesta sincronização.
        if "office_name" in meta_updates:
            _sync_letterhead_derivado(config, "office_name", "office_name_custom", meta_updates["office_name"])
    await db.flush()
    await invalidate_tenant_cache(tenant.slug)
    meta = config.extra_data or {}
    logo_url = await _resolve_cached_logo_url({
        "logo_storage_key": config.logo_storage_key, "logo_url": config.logo_url,
    })
    return ThemeResponse(
        primary_color=config.primary_color,
        secondary_color=config.secondary_color,
        accent_color=config.accent_color,
        logo_url=logo_url,
        logo_dark_url=config.logo_dark_url,
        favicon_url=config.favicon_url,
        app_name=config.app_name,
        office_name=meta.get("office_name"),
        slogan=meta.get("slogan"),
        is_demo=bool(tenant.is_demo),
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
    """Recebe arquivo de imagem e salva como logo do timbrado — vai pro
    object storage S3-compatível quando configurado (Fase 143, reaproveita
    app/integrations/object_storage.py da Fase 141), senão mantém o
    caminho legado (base64 inline em logo_url)."""
    import base64
    from app.integrations import object_storage

    ALLOWED = {"image/png", "image/jpeg", "image/svg+xml", "image/webp"}
    if file.content_type not in ALLOWED:
        raise HTTPException(status_code=400, detail="Tipo não suportado. Use PNG, JPG, SVG ou WebP.")
    contents = await file.read()
    if len(contents) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Arquivo muito grande. Máximo 2MB.")

    tenant, config = await _get_or_create_config(db, current_user)

    if object_storage.is_configured():
        try:
            key = await object_storage.upload_bytes(
                tenant_id=tenant.id, document_id=config.id,
                filename=file.filename or "logo", content_type=file.content_type, data=contents,
            )
        except object_storage.ObjectStorageError:
            raise HTTPException(status_code=502, detail="Falha ao enviar o logo para o armazenamento. Tente novamente.")
        config.logo_storage_key = key
        config.logo_mimetype = file.content_type
        config.logo_url = None
        await db.flush()
        await invalidate_tenant_cache(tenant.slug)
        preview_url = await object_storage.generate_presigned_url(key, expires_in=3600)
        return {"logo_url": preview_url}

    b64 = base64.b64encode(contents).decode()
    data_url = f"data:{file.content_type};base64,{b64}"
    config.logo_storage_key = None
    config.logo_mimetype = None
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
        # Fase 174.9 — sem filtrar por is_active, se o tenant raiz existisse
        # mas estivesse is_active=False (só alcançável hoje via tamper direto
        # no Postgres — update_tenant() bloqueia isso via API pro tenant
        # raiz), esta query não encontrava a linha e o bloco abaixo tentava
        # inserir um 2º Tenant(slug="afj"), estourando IntegrityError não
        # tratada (slug é unique) — um 500 genérico em vez de reaproveitar a
        # linha existente.
        tenant = (await db.execute(
            select(Tenant).where(Tenant.slug == DEFAULT_TENANT_SLUG)
        )).scalar_one_or_none()
        if tenant and not tenant.is_active:
            # O tenant raiz nunca deveria ficar inativo (Fase 170) — reativa
            # em vez de deixar a inconsistência se propagar.
            tenant.is_active = True
    if not tenant:
        # Fase 170 — mesmo invariante do backfill em app/core/events.py:
        # o tenant raiz sempre nasce no plano Máximo e isento.
        tenant = Tenant(name="Almeida, Freire & Jucá Advogados", slug=DEFAULT_TENANT_SLUG, plan="MAXIMO", isento=True)
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
def _endereco_para_texto(endereco: dict | None) -> str | None:
    """Fase 232 — formata `{logradouro, bairro, cidade, uf, cep}` numa
    linha só, mesmo formato usado em `/mapa` (`enderecoTexto()` no
    frontend) — reaproveitado aqui pra alimentar o timbrado
    automaticamente a partir do "Endereço do Escritório" (Fase 230),
    sem exigir uma segunda digitação do mesmo endereço."""
    if not endereco:
        return None
    partes = [endereco.get("logradouro"), endereco.get("bairro")]
    cidade_uf = "/".join(x for x in (endereco.get("cidade"), endereco.get("uf")) if x)
    if cidade_uf:
        partes.append(cidade_uf)
    texto = " — ".join(p for p in partes if p)
    cep = endereco.get("cep")
    if cep:
        texto = f"{texto} — CEP {cep}" if texto else f"CEP {cep}"
    return texto or None


def _sync_letterhead_derivado(config: "TenantConfig", campo: str, flag_custom: str, valor_auto) -> None:
    """Fase 232 — mantém um campo do timbrado (nome/endereço) sincronizado
    com o cadastro de origem ("Nome do Escritório"/"Endereço do
    Escritório"), a menos que o usuário tenha explicitamente
    personalizado esse campo no próprio timbrado. Chamado a partir de
    `update_endereco`/`update_branding` — mantém `document_templates.
    letterhead` sempre correto pros geradores de PDF, sem precisar
    tocar em nenhum dos 7 call sites que já leem esse JSONB direto."""
    templates = dict(config.document_templates or {})
    lh = dict(templates.get("letterhead") or {})
    if not lh.get(flag_custom):
        lh[campo] = valor_auto
        templates["letterhead"] = lh
        config.document_templates = templates


class LetterheadUpdate(BaseModel):
    office_name: str | None = None
    office_name_custom: bool = False
    address: str | None = None
    address_custom: bool = False
    contact: str | None = None
    oab: str | None = None
    footer: str | None = None
    use_logo: bool = True


@router.get("/letterhead")
async def get_letterhead(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Timbrado configurado do escritório (usado nos PDFs gerados).

    Fase 232 — "office_name"/"address" resolvem automaticamente a partir
    de "Nome do Escritório"/"Endereço do Escritório" (abas Escritório),
    a menos que tenham sido explicitamente personalizados aqui no
    timbrado (`office_name_custom`/`address_custom`). Resolvido na
    LEITURA (não só confiando no que foi sincronizado por escrita em
    `update_endereco`/`update_branding`) pra cobrir também um tenant que
    já tinha nome/endereço cadastrados antes desta fase e nunca salvou
    o timbrado — sem precisar de backfill/migração."""
    tenant, config = await _get_or_create_config(db, current_user)
    lh = (config.document_templates or {}).get("letterhead") or {}
    meta = config.extra_data or {}
    office_name_custom = bool(lh.get("office_name_custom"))
    address_custom = bool(lh.get("address_custom"))
    office_name = lh.get("office_name") if office_name_custom else (meta.get("office_name") or lh.get("office_name"))
    address = lh.get("address") if address_custom else (_endereco_para_texto(tenant.endereco_json) or lh.get("address"))
    return {
        "office_name": office_name,
        "office_name_custom": office_name_custom,
        "address": address,
        "address_custom": address_custom,
        "contact": lh.get("contact"),
        "oab": lh.get("oab"),
        "footer": lh.get("footer"),
        "use_logo": lh.get("use_logo", True),
        "has_logo": bool(config.logo_url or config.logo_storage_key),
    }


@router.put("/letterhead")
async def update_letterhead(
    body: LetterheadUpdate,
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Salva o timbrado do escritório em TenantConfig.document_templates
    (JSONB). Fase 232 — quando `office_name_custom`/`address_custom` vêm
    `False` (usuário optou por "usar automaticamente"), recalcula o
    valor a partir do cadastro de origem em vez de confiar no que o
    corpo da requisição mandou — garante que "voltar ao automático"
    sempre produz o valor certo mesmo com um frontend desatualizado."""
    tenant, config = await _get_or_create_config(db, current_user)
    meta = config.extra_data or {}

    office_name_val = ((body.office_name or "").strip() or None) if body.office_name_custom else meta.get("office_name")
    address_val = ((body.address or "").strip() or None) if body.address_custom else _endereco_para_texto(tenant.endereco_json)

    templates = dict(config.document_templates or {})
    templates["letterhead"] = {
        "office_name": office_name_val,
        "office_name_custom": body.office_name_custom,
        "address": address_val,
        "address_custom": body.address_custom,
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


# ─── Endereço do escritório ───────────────────────────────────────────────────
class EnderecoUpdate(BaseModel):
    cep: str | None = None
    logradouro: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    uf: str | None = None


@router.get("/endereco")
async def get_endereco(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fase 230 — endereço físico do próprio escritório, groundwork pro mapa
    com marcadores de escritório+clientes planejado pra uma fase futura."""
    tenant, _ = await _get_or_create_config(db, current_user)
    return tenant.endereco_json or {}


@router.put("/endereco")
async def update_endereco(
    body: EnderecoUpdate,
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Salva o endereço do escritório e geocodifica via BrasilAPI (mesma
    fonte/limitação de precisão de `Client.endereco_json`, ver
    `_geocodificar_endereco` em `app/api/v1/clients.py`).

    Fase 232 — também sincroniza o endereço do timbrado (`document_
    templates.letterhead.address`), a menos que já tenha sido
    personalizado explicitamente lá — elimina o cadastro duplicado que
    existia entre esta seção e "Timbrado dos Documentos"."""
    from app.api.v1.clients import _geocodificar_endereco

    tenant, config = await _get_or_create_config(db, current_user)
    endereco = body.model_dump(exclude_none=True)
    tenant.endereco_json = await _geocodificar_endereco(endereco) if endereco else None
    _sync_letterhead_derivado(config, "address", "address_custom", _endereco_para_texto(tenant.endereco_json))
    await db.flush()
    await invalidate_tenant_cache(tenant.slug)
    return tenant.endereco_json or {}


# ─── Modo confidencial (advogado vê só os processos da sua equipe) ───────────
class ConfidencialUpdate(BaseModel):
    modo_confidencial: bool


@router.get("/confidencial")
async def get_confidencial(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Estado do modo confidencial do escritório."""
    _, config = await _get_or_create_config(db, current_user)
    return {"modo_confidencial": bool((config.extra_data or {}).get("modo_confidencial"))}


@router.put("/confidencial")
async def update_confidencial(
    body: ConfidencialUpdate,
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Liga/desliga o modo confidencial. Ligado: advogados comuns veem só os
    processos da sua equipe; ADMIN/SOCIO/GESTOR continuam com visão total."""
    tenant, config = await _get_or_create_config(db, current_user)
    meta = dict(config.extra_data or {})
    meta["modo_confidencial"] = bool(body.modo_confidencial)
    config.extra_data = meta
    await db.flush()
    await invalidate_tenant_cache(tenant.slug)
    return {"modo_confidencial": meta["modo_confidencial"]}


# ─── OABs monitoradas do escritório (sócios capturam mesmo sem login) ────────
class OabItem(BaseModel):
    numero: str
    uf: str
    nome: str | None = None


class OabsUpdate(BaseModel):
    oabs: list[OabItem]


@router.get("/oabs")
async def get_oabs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """OABs monitoradas do escritório (varredura DJe + captura de processos)."""
    _, config = await _get_or_create_config(db, current_user)
    oabs = (config.extra_data or {}).get("oabs_monitoradas", [])
    return {"oabs": oabs if isinstance(oabs, list) else []}


@router.put("/oabs")
async def update_oabs(
    body: OabsUpdate,
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Salva as OABs monitoradas em TenantConfig.extra_data (JSONB), dedup por número+UF."""
    import re as _re
    itens: list[dict] = []
    vistos: set[tuple[str, str]] = set()
    for o in body.oabs:
        numero = _re.sub(r"\D", "", o.numero or "")
        uf = (o.uf or "").strip().upper()
        if not numero or len(uf) != 2 or not uf.isalpha():
            raise HTTPException(status_code=422, detail=f"OAB inválida: {o.numero}/{o.uf} (use número + UF de 2 letras).")
        if (numero, uf) in vistos:
            continue
        vistos.add((numero, uf))
        itens.append({"numero": numero, "uf": uf, "nome": (o.nome or "").strip() or None})

    tenant, config = await _get_or_create_config(db, current_user)
    meta = dict(config.extra_data or {})
    meta["oabs_monitoradas"] = itens
    config.extra_data = meta
    await db.flush()
    await invalidate_tenant_cache(tenant.slug)
    return {"oabs": itens}


@router.post("/oabs/capturar")
async def capturar_processos_oabs(
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Captura processos das OABs do escritório via Comunica/DJEN (fonte pública).

    Roda de forma síncrona (não usa IA) e retorna a contagem do que foi criado.
    Idempotente — só cria processos que ainda não existem no escritório.
    """
    from app.services.oab_capture import capturar_por_oab

    _, config = await _get_or_create_config(db, current_user)
    oabs_cfg = (config.extra_data or {}).get("oabs_monitoradas", [])
    # Também vale se houver advogados com OAB cadastrada (mesmo sem OAB avulsa).
    from sqlalchemy import func
    tem_user_oab = (await db.execute(
        select(func.count(User.id)).where(
            User.tenant_id == current_user.tenant_id,
            User.oab_number.isnot(None),
            User.is_active == True,  # noqa: E712
        )
    )).scalar_one() or 0
    if not oabs_cfg and not tem_user_oab:
        raise HTTPException(
            status_code=422,
            detail="Nenhuma OAB disponível. Cadastre as OABs dos sócios ou dos advogados com login.",
        )

    resultado = await capturar_por_oab(
        db, current_user.tenant_id, dias_retro=365, triggered_by=current_user.id
    )
    encontrados = resultado["processos_encontrados"]
    criados = resultado["processos_criados"]
    if criados:
        msg = f"{criados} novo(s) processo(s) capturado(s) de {resultado['oabs']} OAB(s)."
    elif encontrados:
        msg = f"{encontrados} processo(s) encontrado(s) — todos já cadastrados."
    elif not resultado.get("fonte_respondeu"):
        # A fonte pública não respondeu: quase sempre é o ambiente sem acesso à
        # internet externa (egress/rede) ou a Comunica fora do ar — não é erro de dados.
        # fonte_detalhe (se disponível) distingue "sem rede" (exceção de conexão)
        # de "rede ok, mas a Comunica recusou" (HTTP 4xx/5xx) — antes era descartado.
        detalhe = resultado.get("fonte_detalhe")
        msg = ("A fonte pública (Comunica/DJEN) não respondeu"
               + (f" ({detalhe})" if detalhe else "")
               + ". Verifique se o ambiente tem acesso à internet externa (egress) ou tente novamente mais tarde.")
    else:
        msg = "A fonte respondeu, mas não há publicações no período para as OABs do escritório."
    return {**resultado, "message": msg}


# ─── Filiais self-serve (plano ENTERPRISE) ───────────────────────────────────
class MyUnitCreate(BaseModel):
    name: str
    unit_label: str
    admin_email: EmailStr
    admin_name: str


def _plano_permite_filiais(plan: str | None) -> bool:
    return (plan or "").strip().upper() in ("ENTERPRISE", "BANCA")


async def _my_tenant(db: AsyncSession, current_user: User) -> Tenant:
    tenant = None
    if current_user.tenant_id:
        tenant = (await db.execute(
            select(Tenant).where(Tenant.id == current_user.tenant_id)
        )).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Escritório não encontrado.")
    return tenant


@router.get("/units")
async def list_my_units(
    current_user: User = Depends(require_role("ADMIN", "SOCIO")),
    db: AsyncSession = Depends(get_db),
):
    """Unidades (filiais) do meu escritório, com nº de usuários por unidade."""
    from sqlalchemy import func as _func
    tenant = await _my_tenant(db, current_user)
    units = (await db.execute(
        select(Tenant).where(Tenant.parent_tenant_id == tenant.id).order_by(Tenant.created_at)
    )).scalars().all()
    counts = dict((await db.execute(
        select(User.tenant_id, _func.count(User.id))
        .where(User.tenant_id.in_([u.id for u in units]), User.is_active == True)  # noqa: E712
        .group_by(User.tenant_id)
    )).all()) if units else {}
    return {
        "plano_permite_filiais": _plano_permite_filiais(tenant.plan),
        "units": [
            {
                "id": str(u.id),
                "name": u.name,
                "unit_label": u.unit_label,
                "is_active": u.is_active,
                "users": int(counts.get(u.id, 0)),
            }
            for u in units
        ],
    }


@router.post("/units", status_code=201)
async def create_my_unit(
    body: MyUnitCreate,
    current_user: User = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Cria uma filial do próprio escritório (self-serve, plano ENTERPRISE).

    A banca-mãe é SEMPRE o tenant do usuário (anti-escalada: um ADMIN não
    consegue criar unidade sob outro escritório).
    """
    from app.api.v1.tenants_admin import UnitCreate, _provision

    tenant = await _my_tenant(db, current_user)
    if tenant.parent_tenant_id is not None:
        raise HTTPException(status_code=422, detail="Uma unidade não pode criar sub-unidades (apenas 1 nível).")
    if not _plano_permite_filiais(tenant.plan):
        raise HTTPException(
            status_code=403,
            detail=f"Filiais estão disponíveis no plano ENTERPRISE (seu plano: {tenant.plan}). Fale com a plataforma para upgrade.",
        )

    unit_body = UnitCreate(
        name=body.name,
        unit_label=body.unit_label,
        plan=tenant.plan,
        max_users=tenant.max_users,
        admin_email=body.admin_email,
        admin_name=body.admin_name,
    )
    return await _provision(db, unit_body, parent_tenant_id=tenant.id, unit_label=body.unit_label.strip())


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

    # Estimativa de armazenamento: bytes reais dos arquivos migrados pro S3
    # (Fase 141, arquivo_size_bytes) ou o tamanho do base64 legado como
    # aproximação pras linhas ainda não migradas, + textos no banco.
    storage_bytes = (await db.execute(
        select(
            func.coalesce(func.sum(
                func.coalesce(Document.arquivo_size_bytes, func.length(Document.arquivo_url))
            ), 0)
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

    # Fase 170 — isenção de cobrança agora é a coluna Tenant.isento (o tenant
    # raiz da plataforma sempre tem isento=True, garantido pelo backfill em
    # app/core/events.py), não mais um caso especial hardcoded por slug.
    if tenant.isento:
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
