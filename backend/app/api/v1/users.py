from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func, update
from pydantic import BaseModel, EmailStr
from datetime import datetime, timezone
from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.models.ai_config import AIProviderConfig  # import no topo: garante registro no Base.metadata antes do create_all
from app.core.security import hash_password
from app.services.ai_providers import AI_PROVIDERS, get_provider
import uuid
import secrets
import string

import re

router = APIRouter(prefix="/users", tags=["users"])

# Modelos sugeridos (para hints/UX). NÃO é uma allowlist rígida: o Google e a
# Anthropic adicionam/aposentam modelos com frequência, então a validação real
# é por FORMATO (regex abaixo) e a API é a fonte de verdade sobre disponibilidade.
SUGGESTED_MODELS = {
    "gemini": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
    "anthropic": ["claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5"],
}

# Formato esperado: prefixo do provider + versão. Rejeita entradas genéricas
# como "Gemini" ou "Claude" (que causam 400 "unexpected model name format").
_MODEL_FORMAT = {
    "gemini": re.compile(r"^gemini-[\d.]+-[a-z0-9-]+$", re.IGNORECASE),
    "anthropic": re.compile(r"^claude-[a-z0-9.-]+$", re.IGNORECASE),
}


def _validate_model_format(provider: str, model: str) -> str | None:
    """Retorna mensagem de erro se o modelo tiver formato inválido, senão None."""
    pattern = _MODEL_FORMAT.get(provider)
    if pattern and not pattern.match(model):
        examples = ", ".join(SUGGESTED_MODELS.get(provider, [])[:2])
        return f"Modelo '{model}' tem formato inválido para {provider}. Use algo como: {examples}"
    return None


def _require_admin(current_user: User) -> None:
    if current_user.role not in ("ADMIN", "SUPERADMIN"):
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")


# Papéis que um administrador de escritório pode atribuir. SUPERADMIN (dono da
# plataforma, atravessa todos os tenants) só pode ser atribuído por outro
# SUPERADMIN; CLIENT nasce apenas pelo fluxo do portal — nunca por convite/edição.
_OFFICE_ROLES = {"ASSISTENTE", "ADVOGADO", "GESTOR", "SOCIO", "ADMIN"}


def _validate_role_assignment(role: str, current_user: User) -> None:
    if role in _OFFICE_ROLES:
        return
    if role == "SUPERADMIN" and current_user.role == "SUPERADMIN":
        return
    raise HTTPException(
        status_code=422,
        detail=f"Papel inválido. Permitidos: {', '.join(sorted(_OFFICE_ROLES))}.",
    )


class ProfileUpdate(BaseModel):
    full_name: str | None = None
    telefone: str | None = None   # WhatsApp p/ alertas de prazo/intimação (Fase 70)
    oab_number: str | None = None
    oab_uf: str | None = None


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


class AIConfigCreate(BaseModel):
    provider: str
    display_name: str | None = None
    auth_method: str = "api_key"
    api_key: str | None = None
    model: str | None = None
    base_url: str | None = None          # obrigatório só pra ollama (self-hosted)
    enabled: bool = True
    is_default: bool = False


class AIConfigUpdate(BaseModel):
    display_name: str | None = None
    api_key: str | None = None           # se omitido, mantém a chave atual
    model: str | None = None
    base_url: str | None = None
    enabled: bool | None = None
    priority: int | None = None          # ordem no fallback (menor = tentada antes) — Fase 137.3


def _config_to_dict(c: AIProviderConfig) -> dict:
    """Nunca inclui a chave/credencial — só `has_credential` (bool)."""
    return {
        "id": str(c.id),
        "provider": c.provider,
        "display_name": c.display_name,
        "auth_method": c.auth_method,
        "model": c.model or "",
        "base_url": c.base_url,
        "enabled": c.enabled,
        "is_default": c.is_default,
        "priority": c.priority,
        "status": c.status,
        "has_credential": bool(c.credentials_enc),
        "last_tested_at": c.last_tested_at.isoformat() if c.last_tested_at else None,
        "last_error": c.last_error,
    }


@router.get("/me/ai-providers")
async def list_ai_providers():
    """Registro estático dos provedores suportados (Fase 137.1) — o frontend
    monta o formulário de "Adicionar IA" a partir disto."""
    return {"providers": AI_PROVIDERS}


@router.get("/me/ai-configs")
async def list_my_ai_configs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lista as IAs cadastradas pelo usuário (BYOK multi-provedor, Fase 137.1).
    Ordem = ordem real de fallback (Fase 137.3): padrão primeiro, depois por
    prioridade, mesmo `ORDER BY` usado em `byok.user_ai_creds()`."""
    rows = (await db.execute(
        select(AIProviderConfig)
        .where(AIProviderConfig.user_id == current_user.id)
        .order_by(
            AIProviderConfig.is_default.desc(),
            AIProviderConfig.priority.asc().nullslast(),
            AIProviderConfig.created_at.asc(),
        )
    )).scalars().all()
    return {"configs": [_config_to_dict(c) for c in rows]}


@router.post("/me/ai-configs", status_code=201)
async def create_my_ai_config(
    body: AIConfigCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.core.crypto import encrypt
    import json

    prov = body.provider.lower().strip()
    info = get_provider(prov)
    if not info:
        raise HTTPException(status_code=422, detail=f"Provedor desconhecido: {prov}")

    auth_method = body.auth_method if body.auth_method in info["auth_methods"] else info["auth_methods"][0]
    if info["requires_key"] and auth_method == "api_key" and not (body.api_key and body.api_key.strip()):
        raise HTTPException(status_code=422, detail="Configure uma chave de API")
    base_url = (body.base_url or info.get("base_url") or "").strip() or None
    # Só provedores openai-compatíveis SEM URL fixa (hoje: ollama, self-hosted)
    # exigem que o usuário informe uma — Anthropic usa o SDK próprio e nunca lê
    # `base_url` (também tem `info["base_url"] is None`, mas por outro motivo:
    # não roteia por URL nenhuma, não é "self-hosted sem URL fixa"). Bug real
    # corrigido na Fase 137.3: a checagem antiga usava só `not info["base_url"]`,
    # que também dava True pra Anthropic — bloqueava cadastrar BYOK Anthropic.
    if prov != "anthropic" and not info["base_url"] and not base_url:
        raise HTTPException(status_code=422, detail="Informe a URL do servidor")

    model = (body.model or "").strip() or info.get("modelo_sugerido")
    if model:
        err = _validate_model_format(prov, model)
        if err:
            raise HTTPException(status_code=422, detail=err)

    creds_enc = None
    if body.api_key and body.api_key.strip():
        creds_enc = encrypt(json.dumps({"api_key": body.api_key.strip()}))

    # A 1ª IA cadastrada sempre vira a padrão, mesmo sem marcar explicitamente
    # — sem isso o usuário cadastraria uma IA e ela nunca seria usada.
    existentes = (await db.execute(
        select(AIProviderConfig.id).where(AIProviderConfig.user_id == current_user.id)
    )).scalars().all()
    is_default = body.is_default or not existentes
    if is_default:
        await db.execute(
            update(AIProviderConfig).where(AIProviderConfig.user_id == current_user.id).values(is_default=False)
        )

    config = AIProviderConfig(
        user_id=current_user.id, tenant_id=current_user.tenant_id,
        provider=prov, display_name=(body.display_name or info["nome"]).strip(),
        auth_method=auth_method, credentials_enc=creds_enc, model=model, base_url=base_url,
        enabled=body.enabled, is_default=is_default,
    )
    db.add(config)
    await db.flush()
    return _config_to_dict(config)


@router.patch("/me/ai-configs/{config_id}")
async def update_my_ai_config(
    config_id: str,
    body: AIConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.core.crypto import encrypt
    import json

    config = await db.get(AIProviderConfig, uuid.UUID(config_id))
    if not config or config.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Configuração não encontrada")

    if body.display_name is not None and body.display_name.strip():
        config.display_name = body.display_name.strip()
    if body.model is not None:
        model = body.model.strip() or None
        if model:
            err = _validate_model_format(config.provider, model)
            if err:
                raise HTTPException(status_code=422, detail=err)
        config.model = model
    if body.base_url is not None:
        config.base_url = body.base_url.strip() or None
    if body.api_key and body.api_key.strip():
        config.credentials_enc = encrypt(json.dumps({"api_key": body.api_key.strip()}))
    if body.enabled is not None:
        config.enabled = body.enabled
    if body.priority is not None:
        config.priority = body.priority

    await db.flush()
    return _config_to_dict(config)


@router.delete("/me/ai-configs/{config_id}", status_code=204)
async def delete_my_ai_config(
    config_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    config = await db.get(AIProviderConfig, uuid.UUID(config_id))
    if not config or config.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Configuração não encontrada")
    era_default = config.is_default
    await db.delete(config)
    await db.flush()
    if era_default:
        # Promove a config mais recente restante a padrão — sem isso o
        # usuário ficaria sem IA ativa nenhuma sem perceber.
        proxima = (await db.execute(
            select(AIProviderConfig).where(AIProviderConfig.user_id == current_user.id)
            .order_by(AIProviderConfig.created_at.desc()).limit(1)
        )).scalar_one_or_none()
        if proxima:
            proxima.is_default = True
            await db.flush()


@router.post("/me/ai-configs/{config_id}/duplicate", status_code=201)
async def duplicate_my_ai_config(
    config_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    original = await db.get(AIProviderConfig, uuid.UUID(config_id))
    if not original or original.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Configuração não encontrada")
    copia = AIProviderConfig(
        user_id=current_user.id, tenant_id=current_user.tenant_id,
        provider=original.provider, display_name=f"{original.display_name} (cópia)",
        auth_method=original.auth_method, credentials_enc=original.credentials_enc,
        model=original.model, base_url=original.base_url, enabled=original.enabled,
        is_default=False,
    )
    db.add(copia)
    await db.flush()
    return _config_to_dict(copia)


@router.post("/me/ai-configs/{config_id}/set-default")
async def set_default_my_ai_config(
    config_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    config = await db.get(AIProviderConfig, uuid.UUID(config_id))
    if not config or config.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Configuração não encontrada")
    await db.execute(
        update(AIProviderConfig).where(AIProviderConfig.user_id == current_user.id).values(is_default=False)
    )
    config.is_default = True
    config.enabled = True  # padrão desativada nunca seria usada — força ativa
    await db.flush()
    return _config_to_dict(config)


@router.post("/me/ai-configs/{config_id}/test")
async def test_my_ai_config(
    config_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Faz uma chamada mínima com a IA cadastrada para validar a credencial."""
    from app.core.crypto import decrypt
    from app.integrations.llm_client import call_llm, ai_creds_ctx
    import json

    config = await db.get(AIProviderConfig, uuid.UUID(config_id))
    if not config or config.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Configuração não encontrada")

    api_key = None
    if config.credentials_enc:
        raw = decrypt(config.credentials_enc)
        if raw:
            try:
                api_key = (json.loads(raw) or {}).get("api_key")
            except Exception:
                api_key = None

    if config.auth_method != "none" and not api_key:
        raise HTTPException(
            status_code=422,
            detail="Sua chave precisa ser salva novamente (a configuração de segurança do servidor mudou).",
        )

    suggested = ", ".join(SUGGESTED_MODELS.get(config.provider, [])[:2]) or "ver documentação"
    token = ai_creds_ctx.set({
        "provider": config.provider,
        "api_key": api_key or "",
        "model": config.model,
        "base_url": config.base_url,
    })
    try:
        # max_tokens generoso: os modelos "thinking" (ex.: Gemini 2.5, Claude com
        # reasoning) gastam tokens no raciocínio interno antes de emitir texto.
        # Com um teto baixo (ex.: 10) a resposta volta VAZIA (finish=length).
        content, _in, _out, _cost = await call_llm(
            messages=[{"role": "user", "content": "Responda apenas: OK"}],
            system="Você é um teste de conexão. Responda em uma palavra.",
            max_tokens=256,
            temperature=0,
        )
        sample = (content or "").strip()
        config.last_tested_at = datetime.now(timezone.utc)
        if not sample:
            config.status = "ERRO"
            config.last_error = "Modelo retornou vazio"
            await db.flush()
            return {
                "ok": False,
                "error": "Conexão feita, mas o modelo retornou vazio. Tente um modelo estável como "
                         f"'{config.model or suggested}'.",
            }
        config.status = "ATIVA"
        config.last_error = None
        await db.flush()
        return {"ok": True, "provider": config.provider, "model": config.model, "sample": sample[:40]}
    except Exception as exc:
        msg = _friendly_ai_error(exc, config.provider, config.model, suggested)
        config.status = "ERRO"
        config.last_error = msg[:255]
        config.last_tested_at = datetime.now(timezone.utc)
        await db.flush()
        return {"ok": False, "error": msg}
    finally:
        ai_creds_ctx.reset(token)


def _friendly_ai_error(exc: Exception, provider: str, model: str | None, suggested: str) -> str:
    """Traduz erros do SDK/API (Gemini/Anthropic) em mensagens acionáveis em PT."""
    err_str = str(exc).lower()
    # 404 → modelo inexistente/aposentado (ex.: gemini-1.5-* fora de circulação)
    if "404" in err_str or "not_found" in err_str or "not found" in err_str:
        return (f"Modelo '{model}' não está disponível (pode ter sido aposentado). "
                f"Use um modelo atual: {suggested}.")
    # 429 → quota/free-tier zerada ou rate limit
    if "429" in err_str or "resource_exhausted" in err_str or "quota" in err_str or "rate limit" in err_str:
        return ("Cota da sua chave esgotada ou indisponível para este modelo. "
                "Ative faturamento no Google AI Studio ou troque de modelo/chave.")
    # 400 formato de modelo
    if "unexpected model name format" in err_str or ("invalid" in err_str and "model" in err_str):
        return f"Modelo '{model}' com formato inválido. Tente: {suggested}."
    # Auth
    if any(k in err_str for k in ("401", "403", "api key", "api_key", "authentication", "permission", "unauthorized")):
        return "Chave de API inválida, expirada ou sem permissão. Verifique a chave no provedor."
    return str(exc)[:200]


# ─── Overrides de modelo por tipo de tarefa (IA por área) ────────────────────
# Tipos de tarefa expostos na UI. Devem casar com o router de agentes
# (app/agents/brain/router.py) e com os task_type passados a user_ai_creds.
OVERRIDABLE_TASKS = [
    "generate_petition",
    "review_document",
    "manage_contract",
    "search_jurisprudence",
    "generate_strategy",
    "analytics_report",
]


class AIOverrideItem(BaseModel):
    task_type: str
    provider_config_id: str | None = None  # Fase 137.4 — IA inteira pra essa tarefa
    model: str | None = None               # legado da Fase 137.1 — só string de modelo


class AIOverridesUpdate(BaseModel):
    overrides: list[AIOverrideItem]


def _override_to_dict(r) -> dict:
    return {
        "task_type": r.task_type,
        "provider_config_id": str(r.provider_config_id) if r.provider_config_id else None,
        "model": r.model,
    }


@router.get("/me/ai-settings/overrides")
async def get_my_ai_overrides(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ajuste por área: qual IA usar (ou só qual modelo) por tipo de tarefa.
    Sem override → usa a IA padrão do usuário."""
    from app.models.user import AITaskOverride

    result = await db.execute(
        select(AITaskOverride).where(AITaskOverride.user_id == current_user.id)
    )
    rows = result.scalars().all()
    return {
        "tasks": OVERRIDABLE_TASKS,
        "overrides": [_override_to_dict(r) for r in rows],
    }


@router.put("/me/ai-settings/overrides")
async def update_my_ai_overrides(
    body: AIOverridesUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Substitui o conjunto de overrides do usuário (lista vazia limpa tudo)."""
    from app.models.user import AITaskOverride

    # Provider da config PADRÃO real do usuário (Fase 137.4) — só usado pra
    # validar o formato do `model` no caminho legado (sem provider_config_id).
    # Antes validava contra `current_user.ai_provider`, a coluna de provider
    # único de antes da Fase 137.1 — já não reflete a IA padrão real desde a
    # fundação multi-provedor (bug corrigido nesta fase).
    default_config = (await db.execute(
        select(AIProviderConfig).where(
            AIProviderConfig.user_id == current_user.id,
            AIProviderConfig.is_default == True,  # noqa: E712
        )
    )).scalar_one_or_none()
    prov = (default_config.provider if default_config else current_user.ai_provider) or "gemini"

    seen: set[str] = set()
    configs_do_usuario: dict[str, AIProviderConfig] = {}
    for item in body.overrides:
        if item.task_type not in OVERRIDABLE_TASKS:
            raise HTTPException(status_code=422, detail=f"Tipo de tarefa inválido: {item.task_type}")
        if item.task_type in seen:
            raise HTTPException(status_code=422, detail=f"Tipo de tarefa duplicado: {item.task_type}")
        seen.add(item.task_type)

        if item.provider_config_id:
            config = await db.get(AIProviderConfig, uuid.UUID(item.provider_config_id))
            if not config or config.user_id != current_user.id:
                raise HTTPException(status_code=404, detail=f"IA não encontrada para a tarefa {item.task_type}")
            configs_do_usuario[item.task_type] = config
        elif item.model and item.model.strip():
            err = _validate_model_format(prov, item.model.strip())
            if err:
                raise HTTPException(status_code=422, detail=err)
        else:
            raise HTTPException(status_code=422, detail=f"Informe uma IA ou um modelo para {item.task_type}")

    # Substituição integral: remove os atuais e insere os enviados.
    existing = (await db.execute(
        select(AITaskOverride).where(AITaskOverride.user_id == current_user.id)
    )).scalars().all()
    for row in existing:
        await db.delete(row)
    novas = []
    for item in body.overrides:
        override = AITaskOverride(
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            task_type=item.task_type,
            provider_config_id=configs_do_usuario[item.task_type].id if item.task_type in configs_do_usuario else None,
            model=item.model.strip() if item.model else None,
        )
        db.add(override)
        novas.append(override)
    await db.flush()
    return {"overrides": [_override_to_dict(o) for o in novas], "message": "Ajustes por área salvos"}


@router.get("/me")
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Flags de banca (Fase 29): destravam o menu de Relatórios Consolidados.
    from app.models.tenant import Tenant
    from app.core.tenant import DEFAULT_TENANT_SLUG
    is_root = is_unit = has_units = False
    if current_user.tenant_id:
        tenant = (await db.execute(
            select(Tenant).where(Tenant.id == current_user.tenant_id)
        )).scalar_one_or_none()
        if tenant:
            is_root = tenant.slug == DEFAULT_TENANT_SLUG
            is_unit = tenant.parent_tenant_id is not None
            has_units = (await db.execute(
                select(func.count(Tenant.id)).where(Tenant.parent_tenant_id == tenant.id)
            )).scalar_one() > 0
    return {
        "id": str(current_user.id),
        "full_name": current_user.full_name,
        "email": current_user.email,
        "role": current_user.role,
        "is_active": current_user.is_active,
        "tenant_id": str(current_user.tenant_id) if current_user.tenant_id else None,
        "oab_number": current_user.oab_number,
        "oab_uf": current_user.oab_uf,
        "telefone": current_user.telefone,
        "is_root": is_root,
        "is_unit": is_unit,
        "has_units": has_units,
    }


@router.put("/me")
async def update_me(
    body: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.full_name is not None:
        current_user.full_name = body.full_name
    if body.telefone is not None:
        current_user.telefone = body.telefone.strip() or None
    if body.oab_number is not None:
        current_user.oab_number = body.oab_number.strip() or None
    if body.oab_uf is not None:
        current_user.oab_uf = body.oab_uf.strip().upper()[:2] or None
    await db.commit()
    return {"message": "Perfil atualizado"}


@router.get("/colegas")
async def list_colegas(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lista reduzida dos colaboradores ativos do escritório (id, nome, papel,
    OAB) — para o seletor de equipe do processo. Aberta a qualquer staff (o
    router já barra CLIENT); a lista completa continua admin-only em GET /users."""
    rows = (await db.execute(
        select(User.id, User.full_name, User.role, User.oab_number, User.oab_uf)
        .where(
            User.tenant_id == current_user.tenant_id,
            User.is_active == True,  # noqa: E712
            User.role != "CLIENT",
        )
        .order_by(User.full_name.asc())
    )).all()
    return [
        {
            "id": str(r[0]),
            "full_name": r[1],
            "role": r[2],
            "oab": f"{r[3]}/{r[4]}" if r[3] and r[4] else None,
        }
        for r in rows
    ]


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
    _validate_role_assignment(body.role, current_user)

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="E-mail já cadastrado")

    # Limite de usuários do plano (0 = ilimitado). Conta só o staff ativo —
    # clientes do portal não ocupam assento.
    if current_user.tenant_id:
        from sqlalchemy import func as _func
        from app.models.tenant import Tenant
        tenant = (await db.execute(
            select(Tenant).where(Tenant.id == current_user.tenant_id)
        )).scalar_one_or_none()
        if tenant and (tenant.max_users or 0) > 0:
            ativos = (await db.execute(
                select(_func.count(User.id)).where(
                    User.tenant_id == current_user.tenant_id,
                    User.is_active == True,  # noqa: E712
                    User.role != "CLIENT",
                )
            )).scalar_one() or 0
            if ativos >= tenant.max_users:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Limite do plano {tenant.plan} atingido ({tenant.max_users} usuários ativos). "
                        "Desative um usuário ou fale com a plataforma para ampliar o plano."
                    ),
                )

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
    # Senha temporária: enviar por email se disponível, nunca expor no JSON
    from app.config import settings as _cfg
    if _cfg.EMAIL_ENABLED:
        try:
            from app.services.email import send_email
            texto = (
                f"Bem-vindo(a), {body.full_name}!\n\n"
                f"Senha temporária: {temp_password}\n\n"
                "Altere-a no primeiro acesso."
            )
            await send_email(
                to=body.email,
                subject="Seu acesso ao AFJ CORE SYSTEM",
                html_body=(
                    f"<p>Bem-vindo(a), {body.full_name}!</p>"
                    f"<p>Senha temporária: <strong>{temp_password}</strong></p>"
                    "<p>Altere-a no primeiro acesso.</p>"
                ),
                text_body=texto,
                db=db,
                sender_user_id=current_user.id,  # envia pela conta Google conectada, se houver
            )
        except Exception:
            pass
    return {"id": str(user.id), "message": "Usuário convidado com sucesso. Senha enviada por email."}



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

    updates = body.model_dump(exclude_none=True)
    if "role" in updates:
        _validate_role_assignment(updates["role"], current_user)

    # Proteção contra lockout: não permitir desativar ou rebaixar o ÚLTIMO
    # ADMIN ativo do escritório (senão ninguém mais administra o sistema).
    vai_desativar = updates.get("is_active") is False
    vai_rebaixar = "role" in updates and updates["role"] not in ("ADMIN", "SUPERADMIN")
    if (vai_desativar or vai_rebaixar) and user.role in ("ADMIN", "SUPERADMIN") and user.is_active:
        from sqlalchemy import func as _func
        outros_admins = (await db.execute(
            select(_func.count(User.id)).where(
                User.tenant_id == current_user.tenant_id,
                User.role.in_(["ADMIN", "SUPERADMIN"]),
                User.is_active == True,  # noqa: E712
                User.id != user.id,
            )
        )).scalar_one() or 0
        if outros_admins == 0:
            raise HTTPException(
                status_code=422,
                detail="Este é o último administrador ativo do escritório — promova outro usuário a ADMIN antes de desativá-lo ou rebaixá-lo.",
            )

    for field, value in updates.items():
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


@router.post("/{client_id}/invite-portal", status_code=201)
async def invite_portal_user(
    client_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cria acesso ao portal do cliente para um Client entity (apenas ADMIN)."""
    _require_admin(current_user)
    from app.models.client import Client

    client = (await db.execute(
        select(Client).where(
            Client.id == uuid.UUID(client_id),
            Client.tenant_id == current_user.tenant_id,
        )
    )).scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    if not client.email:
        raise HTTPException(status_code=422, detail="Cliente sem e-mail cadastrado")

    existing_portal = (await db.execute(
        select(User).where(User.linked_client_id == client.id)
    )).scalar_one_or_none()
    if existing_portal:
        raise HTTPException(status_code=409, detail="Este cliente já possui acesso ao portal")

    existing_email = (await db.execute(
        select(User).where(User.email == client.email)
    )).scalar_one_or_none()
    if existing_email:
        raise HTTPException(status_code=409, detail="E-mail já possui acesso interno ao sistema")

    alphabet = string.ascii_letters + string.digits + "!@#$"
    temp_password = "".join(secrets.choice(alphabet) for _ in range(12))

    portal_user = User(
        id=uuid.uuid4(),
        email=client.email,
        full_name=client.nome_completo,
        role="CLIENT",
        hashed_password=hash_password(temp_password),
        is_active=True,
        tenant_id=current_user.tenant_id,
        linked_client_id=client.id,
    )
    db.add(portal_user)
    await db.commit()
    return {
        "portal_user_id": str(portal_user.id),
        "email": client.email,
        "temp_password": temp_password,
        "portal_url": "/portal/login",
        "message": "Acesso ao portal criado com sucesso",
    }


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
            "timestamp": entry.timestamp.isoformat(),
            "action": entry.action,
            "resource_type": entry.resource_type,
            "resource_id": str(entry.resource_id) if entry.resource_id else None,
            "success": entry.success,
            "error_detail": entry.error_detail,
            "ip_address": entry.ip_address,
        }
        for entry in logs
    ]
