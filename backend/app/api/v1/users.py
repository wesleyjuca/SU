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

router = APIRouter(prefix="/users", tags=["users"])

VALID_MODELS = {
    "gemini": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
    "anthropic": ["claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5"],
}


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


class AISettingsUpdate(BaseModel):
    provider: str | None = None          # anthropic | gemini
    model: str | None = None
    api_key: str | None = None           # se omitido, mantém a chave atual
    enabled: bool | None = None


@router.get("/me/ai-settings")
async def get_my_ai_settings(current_user: User = Depends(get_current_user)):
    """Configuração de IA própria (BYOK) do usuário. Nunca retorna a chave."""
    return {
        "provider": current_user.ai_provider or "gemini",
        "model": current_user.ai_model or "",
        "enabled": bool(getattr(current_user, "ai_enabled", False)),
        "has_key": bool(current_user.ai_api_key_enc),
    }


@router.put("/me/ai-settings")
async def update_my_ai_settings(
    body: AISettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.core.crypto import encrypt

    if body.provider is not None:
        prov = body.provider.lower()
        if prov not in ("anthropic", "gemini"):
            raise HTTPException(status_code=422, detail="Provider inválido (anthropic | gemini)")
        current_user.ai_provider = prov
    if body.model is not None:
        model = body.model.strip() or None
        if model:
            prov = (body.provider or current_user.ai_provider or "gemini").lower()
            valid = VALID_MODELS.get(prov, [])
            if valid and model not in valid:
                examples = ", ".join(valid[:2])
                raise HTTPException(
                    status_code=422,
                    detail=f"Modelo inválido para {prov}. Use um destes: {examples}"
                )
        current_user.ai_model = model
    if body.api_key:  # só atualiza a chave se enviada
        enc = encrypt(body.api_key.strip())
        if not enc:
            raise HTTPException(status_code=422, detail="Não foi possível salvar a chave")
        current_user.ai_api_key_enc = enc
    if body.enabled is not None:
        current_user.ai_enabled = body.enabled

    if current_user.ai_enabled and not current_user.ai_api_key_enc:
        raise HTTPException(status_code=422, detail="Configure uma chave de API antes de ativar")

    await db.flush()
    return {
        "provider": current_user.ai_provider or "gemini",
        "model": current_user.ai_model or "",
        "enabled": bool(current_user.ai_enabled),
        "has_key": bool(current_user.ai_api_key_enc),
        "message": "Configuração de IA salva",
    }


@router.post("/me/ai-settings/test")
async def test_my_ai_settings(current_user: User = Depends(get_current_user)):
    """Faz uma chamada mínima com a IA do usuário para validar a chave."""
    from app.core.crypto import decrypt
    from app.integrations.llm_client import call_llm, ai_creds_ctx

    if not current_user.ai_api_key_enc:
        raise HTTPException(status_code=422, detail="Nenhuma chave configurada")
    key = decrypt(current_user.ai_api_key_enc)
    if not key:
        # Token existe mas não decifra: a ENCRYPTION_KEY do servidor mudou
        # (ex.: reinício com chave efêmera). O usuário precisa re-salvar.
        raise HTTPException(
            status_code=422,
            detail="Sua chave precisa ser salva novamente (a configuração de segurança do servidor mudou).",
        )

    prov = current_user.ai_provider or "gemini"
    model = current_user.ai_model or None

    if model and model not in VALID_MODELS.get(prov, []):
        valid = VALID_MODELS.get(prov, [])
        examples = ", ".join(valid[:2]) if valid else "nenhum configurado"
        raise HTTPException(
            status_code=422,
            detail=f"Modelo '{model}' inválido para {prov}. Tente: {examples}"
        )

    token = ai_creds_ctx.set({
        "provider": prov,
        "api_key": key,
        "model": model,
    })
    try:
        content, _in, _out, _cost = await call_llm(
            messages=[{"role": "user", "content": "Responda apenas: OK"}],
            system="Você é um teste de conexão.",
            max_tokens=10,
            temperature=0,
        )
        return {"ok": True, "provider": prov, "sample": (content or "").strip()[:40]}
    except Exception as exc:
        err_str = str(exc).lower()
        if "invalid" in err_str and "model" in err_str:
            valid = VALID_MODELS.get(prov, [])
            examples = ", ".join(valid[:2]) if valid else "ver documentação"
            return {
                "ok": False,
                "error": f"Modelo '{model}' inválido para {prov}. Use um destes: {examples}"
            }
        elif "api" in err_str or "key" in err_str or "authentication" in err_str:
            return {"ok": False, "error": "Chave de API inválida ou expirada. Verifique em Google AI Studio."}
        else:
            return {"ok": False, "error": str(exc)[:200]}
    finally:
        ai_creds_ctx.reset(token)


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
    # Senha temporária: enviar por email se disponível, nunca expor no JSON
    from app.config import settings as _cfg
    if _cfg.EMAIL_ENABLED:
        try:
            from app.services.email import send_email
            await send_email(
                to=body.email,
                subject="Seu acesso ao AFJ CORE SYSTEM",
                body=f"Bem-vindo(a), {body.full_name}!\n\nSenha temporária: {temp_password}\n\nAlterá-la no primeiro acesso.",
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
