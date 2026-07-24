"""Hub de integrações — conexões do escritório com provedores externos.

Base genérica (Fase 67): registro de provedores, credenciais cifradas por
tenant (JSON via app.core.crypto) e helpers de estado OAuth reutilizáveis.
As fases seguintes (pagamento/assinatura/WhatsApp) usam estas credenciais
para as chamadas reais aos provedores.
"""
import json
from datetime import datetime, timedelta, timezone

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.crypto import encrypt, decrypt
from app.models.integrations import TenantIntegration

log = structlog.get_logger()

# ─── Registro de provedores ───────────────────────────────────────────────────
# tipo "api_key": conectar = colar credenciais do painel do provedor (o fluxo
# mais simples que todos os provedores suportam). Provedores com OAuth próprio
# (ex.: Stripe Connect) podem ganhar o fluxo "1 clique" em fase dedicada,
# reusando sign_oauth_state/verify_oauth_state abaixo.
PROVIDERS: dict[str, dict] = {
    "stripe": {
        "nome": "Stripe — Pagamento online",
        "desc": "Cobrança de faturas e da assinatura do SaaS com cartão/Pix via Stripe.",
        "tipo": "api_key",
        "fields": [
            {"key": "secret_key", "label": "Secret key (sk_live_… ou sk_test_…)", "secret": True},
        ],
        "ativa": [
            "Cobrança automática de faturas (fase Pagamento)",
            "Webhook de confirmação de pagamento",
        ],
        "obter": "Dashboard Stripe → Developers → API keys.",
    },
    "mercadopago": {
        "nome": "Mercado Pago — Pagamento online",
        "desc": "Cobrança por Pix/cartão/boleto via Mercado Pago (alternativa nacional).",
        "tipo": "api_key",
        "fields": [
            {"key": "access_token", "label": "Access token de produção (APP_USR-…)", "secret": True},
        ],
        "ativa": [
            "Cobrança automática de faturas (fase Pagamento)",
            "Webhook de confirmação de pagamento",
        ],
        "obter": "Mercado Pago → Suas integrações → Credenciais de produção.",
    },
    "clicksign": {
        "nome": "Clicksign — Assinatura eletrônica",
        "desc": "Envio de contratos para assinatura eletrônica direto do módulo de Contratos.",
        "tipo": "api_key",
        "fields": [
            {"key": "api_token", "label": "Access token da API", "secret": True},
        ],
        "ativa": [
            "Botão \"Enviar para assinatura\" nos contratos (fase Assinatura)",
            "Webhook de retorno atualiza o status do contrato",
        ],
        "obter": "Clicksign → Configurações → API → Gerar access token.",
    },
    "whatsapp": {
        "nome": "WhatsApp — Notificações",
        "desc": "Alertas de prazos, intimações e faturas por WhatsApp (Meta Cloud API).",
        "tipo": "api_key",
        "fields": [
            {"key": "access_token", "label": "Access token permanente (Meta)", "secret": True},
            {"key": "phone_number_id", "label": "Phone number ID", "secret": False},
        ],
        "ativa": [
            "Alertas de prazo para o advogado (telefone no Perfil)",
            "Aviso de nova intimação para a equipe do processo",
            "Fatura com link de pagamento enviada ao cliente",
        ],
        "obter": "Meta for Developers → app WhatsApp Business → API Setup. "
                 "Crie e aprove um template chamado 'afj_notificacao' (pt_BR) com "
                 "um parâmetro {{1}} no corpo — mensagens fora da janela de 24h "
                 "exigem template aprovado.",
    },
    "pdpj": {
        "nome": "PJe / PDPJ — Partes dos processos",
        "desc": "Consulta credenciada à API do PDPJ (CNJ) para preencher as PARTES "
                "dos processos (autor, réu, advogados) — dado que a base pública do "
                "DataJud não expõe. Opcional e por escritório.",
        "tipo": "api_key",
        "fields": [
            {"key": "sso_token", "label": "Token SSO (Bearer) do PDPJ/CNJ Corporativo", "secret": True},
            {"key": "base_url", "label": "URL base da API PDPJ (opcional)", "secret": False},
        ],
        "ativa": [
            "Preenchimento das partes/advogados na captura por OAB",
            "Botão \"Atualizar partes\" no processo (backfill sob demanda)",
        ],
        "obter": "Acesso via CNJ Corporativo (SSO). Cole o token Bearer emitido para "
                 "o PDPJ. Deixe a URL base em branco para usar o portal nacional.",
    },
    "escavador": {
        "nome": "Escavador — Partes & descoberta",
        "desc": "Agregador comercial: descoberta de processos por OAB, detalhe, "
                "partes/advogados e movimentos. Opcional e por escritório.",
        "tipo": "api_key",
        "fields": [
            {"key": "token", "label": "Token de API (Bearer) do Escavador", "secret": True},
            {"key": "base_url", "label": "URL base da API (opcional)", "secret": False},
        ],
        "ativa": [
            "Descoberta por OAB e preenchimento de partes na captura",
            "Botão \"Atualizar partes\" no processo (fallback além do PDPJ)",
        ],
        "obter": "Escavador → Painel → API → gerar token. Deixe a URL base em branco "
                 "para usar o endpoint padrão.",
    },
    "judit": {
        "nome": "Judit — Partes dos processos",
        "desc": "Agregador comercial (judit.io): consulta de processo por número com "
                "partes/advogados e movimentos. Opcional e por escritório.",
        "tipo": "api_key",
        "fields": [
            {"key": "token", "label": "API key da Judit", "secret": True},
            {"key": "base_url", "label": "URL base da API (opcional)", "secret": False},
        ],
        "ativa": [
            "Preenchimento de partes na captura e no botão \"Atualizar partes\"",
        ],
        "obter": "Judit → Dashboard → API keys. Deixe a URL base em branco para o padrão.",
    },
}


# ─── CRUD de credenciais (cifradas) ───────────────────────────────────────────
async def get_integration(db: AsyncSession, tenant_id, provider: str) -> TenantIntegration | None:
    return (await db.execute(
        select(TenantIntegration).where(
            TenantIntegration.tenant_id == tenant_id,
            TenantIntegration.provider == provider,
        )
    )).scalar_one_or_none()


async def save_credentials(
    db: AsyncSession, tenant_id, provider: str, credentials: dict, connected_by=None,
) -> TenantIntegration:
    """Valida contra o registro e salva as credenciais cifradas (upsert)."""
    meta = PROVIDERS.get(provider)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Provedor desconhecido: {provider}")
    faltando = [f["label"] for f in meta["fields"] if not (credentials.get(f["key"]) or "").strip()]
    if faltando:
        raise HTTPException(status_code=422, detail=f"Preencha: {', '.join(faltando)}")

    limpo = {f["key"]: credentials[f["key"]].strip() for f in meta["fields"]}
    integ = await get_integration(db, tenant_id, provider)
    if not integ:
        integ = TenantIntegration(tenant_id=tenant_id, provider=provider, extra_data={})
        db.add(integ)
    integ.credentials_enc = encrypt(json.dumps(limpo))
    integ.status = "CONECTADA"
    integ.connected_by = connected_by
    integ.connected_at = datetime.now(timezone.utc)
    await db.flush()
    log.info("integration_connected", provider=provider, tenant_id=str(tenant_id))
    return integ


async def get_credentials(db: AsyncSession, tenant_id, provider: str) -> dict | None:
    """Credenciais decifradas do provedor, ou None se não conectado."""
    integ = await get_integration(db, tenant_id, provider)
    if not integ or not integ.credentials_enc:
        return None
    raw = decrypt(integ.credentials_enc)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


async def _fonte_credenciada_do_provider(db: AsyncSession, tenant_id, provider: str):
    """Instância da fonte credenciada de um provider (ou None se não testável)."""
    if provider == "pdpj":
        from app.integrations.fontes.pdpj_fonte import para_tenant
    elif provider == "escavador":
        from app.integrations.fontes.escavador_fonte import para_tenant
    elif provider == "judit":
        from app.integrations.fontes.judit_fonte import para_tenant
    else:
        return None
    return await para_tenant(db, tenant_id)


async def testar_conexao(db: AsyncSession, tenant_id, provider: str) -> dict:
    """Testa a credencial conectada e atualiza o `status` (CONECTADA/ERRO).

    Para as fontes credenciadas (pdpj/escavador/judit) faz uma sonda autenticada
    que distingue 401/403 (credencial inválida/expirada) de sucesso. Para os
    demais provedores não há teste automático — retorna o status atual. Não faz
    commit (o chamador comita). Detecção de expiração = este teste marcando ERRO."""
    if provider not in PROVIDERS:
        return {"ok": False, "status": "DESCONHECIDO", "detail": "provedor desconhecido"}
    integ = await get_integration(db, tenant_id, provider)
    if not integ or not integ.credentials_enc:
        return {"ok": False, "status": "DESCONECTADA", "detail": "não conectado"}

    fonte = await _fonte_credenciada_do_provider(db, tenant_id, provider)
    if fonte is None:
        return {"ok": True, "status": integ.status,
                "detail": "teste automático não disponível para este provedor"}

    try:
        ok, detail = await fonte.testar()
    except Exception as exc:
        ok, detail = False, str(exc)[:120]
    integ.status = "CONECTADA" if ok else "ERRO"
    await db.flush()
    log.info("integration_test", provider=provider, tenant_id=str(tenant_id), ok=ok)
    return {"ok": ok, "status": integ.status, "detail": detail}


async def disconnect(db: AsyncSession, tenant_id, provider: str) -> bool:
    integ = await get_integration(db, tenant_id, provider)
    if not integ:
        return False
    await db.delete(integ)
    await db.flush()
    log.info("integration_disconnected", provider=provider, tenant_id=str(tenant_id))
    return True


async def list_status(db: AsyncSession, tenant_id) -> list[dict]:
    """Todos os provedores do registro com o estado de conexão do tenant."""
    rows = (await db.execute(
        select(TenantIntegration).where(TenantIntegration.tenant_id == tenant_id)
    )).scalars().all()
    por_provider = {r.provider: r for r in rows}
    out = []
    for key, meta in PROVIDERS.items():
        integ = por_provider.get(key)
        out.append({
            "provider": key,
            "nome": meta["nome"],
            "desc": meta["desc"],
            "tipo": meta["tipo"],
            "fields": meta["fields"],
            "ativa": meta["ativa"],
            "obter": meta["obter"],
            "status": integ.status if integ else "DESCONECTADA",
            "connected_at": integ.connected_at.isoformat() if integ and integ.connected_at else None,
        })
    return out


# ─── Estado OAuth genérico (reuso do padrão Google, para fases futuras) ───────
def sign_oauth_state(user_id: str, provider: str) -> str:
    from jose import jwt
    return jwt.encode(
        {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
         "purpose": f"{provider}_oauth"},
        settings.SECRET_KEY, algorithm="HS256",
    )


def verify_oauth_state(state: str, provider: str) -> str:
    from jose import jwt, JWTError
    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=["HS256"])
        if payload.get("purpose") != f"{provider}_oauth":
            raise JWTError("purpose")
        return payload["sub"]
    except JWTError:
        raise HTTPException(status_code=400, detail="State OAuth inválido ou expirado. Tente conectar novamente.")
