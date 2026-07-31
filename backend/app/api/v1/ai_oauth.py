"""OAuth "Conectar com login" pro OpenRouter — Fase 137.2.

Único provedor de IA com OAuth genuíno e viável pra um app de terceiro (ver
achados grounded na Fase 137.1/137.2 do plano): PKCE simples, sem
pré-registro de client_id/callback. A troca do `code` devolve uma API key
comum do OpenRouter (não um par access/refresh com expiração) — por isso o
resultado é salvo como `credentials_enc={"api_key": ...}`, igual a qualquer
outro `AIProviderConfig`.

Router próprio (não `google_integration.py`, que é só Google; não
`integrations_hub.py`, que é OAuth por TENANT — este aqui é por USUÁRIO,
mesmo padrão do Google Workspace). Diferença deliberada do padrão Google/Hub:
a exigência de autenticação fica só no endpoint `/connect`, não no router
inteiro — o `/callback` é o navegador do usuário sendo redirecionado pelo
OpenRouter (navegação de página inteira, sem header `Authorization`), então
precisa ficar público. Aplicar `Depends(get_current_user)` no router inteiro
(como o Google/Hub fazem hoje) quebraria esse redirect — achado documentado
no plano, não corrigido nos routers existentes nesta fase.
"""
import base64
import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.crypto import encrypt
from app.db.base import get_db
from app.dependencies import get_current_user
from app.models.ai_config import AIProviderConfig
from app.models.user import User
from app.services.ai_providers import get_provider

log = structlog.get_logger()

router = APIRouter(prefix="/me/ai-configs/oauth/openrouter", tags=["ai-oauth"])

_OPENROUTER_AUTH_URL = "https://openrouter.ai/auth"
_OPENROUTER_TOKEN_URL = "https://openrouter.ai/api/v1/auth/keys"


def _frontend_base_url() -> str:
    """Mesmo padrão de `integrations_hub.py::_frontend_base_url()`."""
    if settings.PUBLIC_BASE_URL:
        return settings.PUBLIC_BASE_URL.rstrip("/")
    if settings.CORS_ORIGINS:
        return settings.CORS_ORIGINS[0].rstrip("/")
    return "http://localhost:3000"


def _sign_state(user_id: str, code_verifier: str, config_id: str | None = None) -> str:
    from jose import jwt
    payload = {
        "sub": user_id,
        "code_verifier": code_verifier,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        "purpose": "openrouter_oauth",
    }
    if config_id:
        payload["config_id"] = config_id
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def _verify_state(state: str) -> dict:
    from jose import jwt, JWTError
    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=["HS256"])
        if payload.get("purpose") != "openrouter_oauth":
            raise JWTError("purpose")
        return payload
    except JWTError:
        raise HTTPException(status_code=400, detail="State OAuth inválido ou expirado. Tente conectar novamente.")


def _code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


@router.get("/connect")
async def openrouter_oauth_connect(
    request: Request,
    config_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Gera a URL de login delegado do OpenRouter ("Conectar com login")."""
    if config_id:
        existing = await db.get(AIProviderConfig, uuid.UUID(config_id))
        if not existing or existing.user_id != current_user.id or existing.provider != "openrouter":
            raise HTTPException(status_code=404, detail="Configuração não encontrada")

    code_verifier = secrets.token_urlsafe(64)
    state = _sign_state(str(current_user.id), code_verifier, config_id)
    # URL absoluta do próprio backend (domínio separado do frontend) — vem da
    # própria requisição, sem precisar de config nova: atrás do Railway,
    # request.base_url já reflete o domínio público real.
    backend_base = str(request.base_url).rstrip("/")
    callback_path = f"{settings.API_V1_STR}/me/ai-configs/oauth/openrouter/callback"
    callback_url = f"{backend_base}{callback_path}?{urlencode({'state': state})}"
    params = {
        "callback_url": callback_url,
        "code_challenge": _code_challenge(code_verifier),
        "code_challenge_method": "S256",
    }
    return {"auth_url": f"{_OPENROUTER_AUTH_URL}?{urlencode(params)}"}


@router.get("/callback")
async def openrouter_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Retorno do OpenRouter: troca o `code` por uma API key e salva cifrada.

    Público — sem `Depends(get_current_user)` (ver docstring do módulo)."""
    base = _frontend_base_url()
    claims = _verify_state(state)
    user_id = uuid.UUID(claims["sub"])
    code_verifier = claims["code_verifier"]
    config_id = claims.get("config_id")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _OPENROUTER_TOKEN_URL,
                json={"code": code, "code_verifier": code_verifier, "code_challenge_method": "S256"},
            )
            resp.raise_for_status()
            api_key = (resp.json() or {}).get("key")
        if not api_key:
            raise ValueError("resposta do OpenRouter sem campo 'key'")
    except Exception as exc:
        log.warning("openrouter_oauth_callback_erro", error=str(exc))
        return RedirectResponse(url=f"{base}/minha-ia?oauth=openrouter_erro")

    creds_enc = encrypt(json.dumps({"api_key": api_key}))

    config = None
    if config_id:
        config = await db.get(AIProviderConfig, uuid.UUID(config_id))
        if not config or config.user_id != user_id:
            config = None

    if config:
        config.credentials_enc = creds_enc
        config.auth_method = "oauth"
        config.status = "ATIVA"
        config.last_error = None
    else:
        info = get_provider("openrouter")
        existentes = (await db.execute(
            select(AIProviderConfig.id).where(AIProviderConfig.user_id == user_id)
        )).scalars().all()
        is_default = not existentes
        if is_default:
            await db.execute(
                update(AIProviderConfig).where(AIProviderConfig.user_id == user_id).values(is_default=False)
            )
        config = AIProviderConfig(
            user_id=user_id, tenant_id=None,
            provider="openrouter", display_name=(info or {}).get("nome", "OpenRouter"),
            auth_method="oauth", credentials_enc=creds_enc,
            model=(info or {}).get("modelo_sugerido"), base_url=None,
            enabled=True, is_default=is_default,
        )
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if user:
            config.tenant_id = user.tenant_id
        db.add(config)

    await db.flush()
    await db.commit()
    return RedirectResponse(url=f"{base}/minha-ia?oauth=openrouter_ok")
