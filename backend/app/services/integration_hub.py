"""Hub de integrações — conexões do escritório com provedores externos.

Base genérica (Fase 67): registro de provedores, credenciais cifradas por
tenant (JSON via app.core.crypto) e helpers de estado OAuth reutilizáveis.
As fases seguintes (pagamento/assinatura/WhatsApp) usam estas credenciais
para as chamadas reais aos provedores.
"""
import json
import re
from datetime import datetime, timedelta, timezone

import httpx
import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.crypto import encrypt, decrypt
from app.models.integrations import TenantIntegration

log = structlog.get_logger()

# Fase 248.3 — camada de tradução de erro amigável. `last_error_detail`
# (exceção httpx/mensagem técnica truncada) chega até o admin não-técnico
# em 2 lugares hoje (toast de conectar/testar/desconectar, banner de erro
# do card, `frontend/.../integracoes/page.tsx`) sem nenhuma curadoria —
# aqui central pra ficar consistente em todo lugar que a string aparece,
# sem precisar tocar frontend algum de novo se um padrão novo surgir. O
# texto cru continua sendo salvo/logado como está (auditoria/suporte) —
# isso é só uma tradução ADITIVA pra exibição, nunca substitui o dado
# técnico original. Primeiro padrão que casa vence; fallback nunca
# inventa uma causa que não foi confirmada.
_FRIENDLY_ERROR_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"credencial inv[aá]lida|revogad|\b401\b|\b403\b", re.I),
     "A credencial não é válida ou foi revogada. Reconecte a integração em Integrações."),
    (re.compile(r"timeout|inalcan[çc][aá]vel|connecterror|connecttimeout", re.I),
     "Não foi possível contatar o provedor agora. Tente novamente em instantes."),
    (re.compile(r"oauth.*expirad|refresh_token", re.I),
     "A sessão conectada expirou e não pôde ser renovada automaticamente. Reconecte a integração."),
    (re.compile(r"escopo|permiss[aã]o insuficiente|insufficient.?scope", re.I),
     "A conta conectada não concedeu as permissões necessárias. Reconecte autorizando todos os acessos solicitados."),
    (re.compile(r"resposta inesperada|http 5\d\d", re.I),
     "O provedor respondeu de forma inesperada — pode ser instabilidade temporária."),
    (re.compile(r"ausente$", re.I),
     "A credencial não foi encontrada. Reconecte a integração em Integrações."),
]


def friendly_detail(raw: str | None) -> str | None:
    """Traduz `last_error_detail`/`detail` cru pra uma mensagem em português
    que um administrador não-técnico consegue agir sobre — nunca afirma uma
    causa que não foi de fato identificada (fallback honesto abaixo)."""
    if not raw:
        return None
    for pattern, friendly in _FRIENDLY_ERROR_PATTERNS:
        if pattern.search(raw):
            return friendly
    truncado = raw[:140]
    return f"Não foi possível identificar a causa exata do erro ({truncado}). Se persistir, contate o suporte técnico."

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
        # Fase 117 — alternativa de login em 1 clique (Stripe Connect OAuth),
        # em paralelo ao form de colar chave abaixo (fallback sempre disponível).
        "oauth_disponivel": True,
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
        # Fase 117 — idem Stripe: login OAuth em paralelo ao form manual.
        "oauth_disponivel": True,
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
        # Fase 168 — a instrução antiga apontava pra aba "API Setup" do Meta
        # for Developers, que só emite um token TEMPORÁRIO de 24h — seguindo
        # literalmente, o WhatsApp para de enviar 1 dia depois de conectado.
        # O caminho certo pro token PERMANENTE é via Usuário do Sistema no
        # Meta Business Suite.
        "obter": "Meta Business Suite → Configurações do negócio → Usuários do "
                 "sistema → crie (ou selecione) um usuário do sistema, atribua o "
                 "ativo \"Conta do WhatsApp Business\" e gere um token PERMANENTE "
                 "(sem expiração) com as permissões business_management, "
                 "whatsapp_business_messaging e whatsapp_business_management — "
                 "não use o token temporário de 24h da aba \"Configuração da "
                 "API\", ele expira em 1 dia e derruba o envio. Crie e aprove um "
                 "template chamado 'afj_notificacao' (pt_BR) com um parâmetro "
                 "{{1}} no corpo — mensagens fora da janela de 24h exigem "
                 "template aprovado.",
    },
    "pdpj": {
        "nome": "PJe / PDPJ — Partes dos processos",
        "desc": "Consulta credenciada à API do PDPJ (CNJ) para preencher as PARTES "
                "dos processos (autor, réu, advogados) — dado que a base pública do "
                "DataJud não expõe. Opcional e por escritório.",
        "tipo": "api_key",
        # Fase 177.1 — alternativa de login direto (usuário+senha do CNJ
        # Corporativo, sem redirect) em paralelo ao form de colar token
        # abaixo (fallback sempre disponível) — mesmo espírito do Stripe/
        # Mercado Pago acima, só que via grant_type=password, não redirect.
        "oauth_disponivel": True,
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
    "jusbrasil": {
        "nome": "Jusbrasil — Partes & descoberta",
        "desc": "Agregador comercial: monitoramento e descoberta de processos por OAB, "
                "detalhe, partes/advogados e movimentos. Opcional e por escritório.",
        "tipo": "api_key",
        "fields": [
            {"key": "token", "label": "Token de API (Bearer) do Jusbrasil", "secret": True},
            {"key": "base_url", "label": "URL base da API (opcional)", "secret": False},
        ],
        "ativa": [
            "Preenchimento de partes na captura e no botão \"Atualizar partes\" (fallback)",
        ],
        "obter": "Jusbrasil → Painel de API → gerar token. Deixe a URL base em branco "
                 "para usar o endpoint padrão.",
    },
    "google_drive_doutrina": {
        "nome": "Google Drive — Doutrina",
        "desc": "Pasta do Drive do escritório com livros/artigos próprios (direito de uso "
                "já do escritório) — sincronizada automaticamente pra base de doutrina "
                "privada, sem afetar a doutrina compartilhada entre todos os tenants. "
                "Opcional e por escritório.",
        "tipo": "api_key",  # sem form manual — só OAuth (ver oauth_disponivel)
        "oauth_disponivel": True,
        "fields": [],
        "ativa": [
            "Ingestão automática diária dos arquivos da pasta configurada (DOCX/PDF/Google Docs)",
            "Busca semântica na coleção privada de doutrina do escritório",
        ],
        "obter": "Clique em \"Conectar com login\" e escolha a conta Google do escritório. "
                 "Depois de conectado, cole a URL ou o ID da pasta do Drive.",
    },
    "google_workspace": {
        "nome": "Google Workspace (Escritório)",
        "desc": "Gmail, Agenda e Drive do escritório numa conexão única — antes eram fluxos "
                "separados por advogado; agora é 1 conta do escritório pra todo mundo. "
                "E-mails automáticos (alerta de prazo, convite de usuário) e eventos de "
                "agenda passam a usar essa conta compartilhada. Opcional e por escritório.",
        "tipo": "api_key",  # sem form manual — só OAuth (ver oauth_disponivel)
        "oauth_disponivel": True,
        "fields": [],
        "ativa": [
            "Envio de e-mails automáticos (alertas de prazo, convite de novo usuário) pela conta do escritório",
            "Sincronização de prazos com a Agenda do escritório",
            "Salvar documentos gerados no Drive do escritório",
        ],
        "obter": "Clique em \"Conectar com login\" e escolha a conta Google do escritório.",
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
    """Credenciais decifradas do provedor, ou None se não conectado.

    Transparente pra quem chama (`payment_gateway.py` etc.): se a credencial
    veio do fluxo OAuth (marcador `__oauth__`) e está perto de expirar, renova
    sozinha aqui e devolve o token já atualizado — nenhum outro código precisa
    saber a diferença entre OAuth e chave colada manualmente."""
    integ = await get_integration(db, tenant_id, provider)
    if not integ or not integ.credentials_enc:
        return None
    raw = decrypt(integ.credentials_enc)
    if not raw:
        return None
    try:
        creds = json.loads(raw)
    except Exception:
        return None
    if isinstance(creds, dict) and creds.get("__oauth__"):
        creds = await _refresh_oauth_if_needed(db, integ, provider, creds)
    return creds


async def _notify_integration_error(db: AsyncSession, integ: TenantIntegration, meta: dict, detalhe: str | None) -> None:
    """Avisa ADMIN/SOCIO/SUPERADMIN do tenant que uma credencial parou de
    funcionar (Fase 177.2) — antes só virava um badge vermelho passivo na
    página de Integrações, sem notificar ninguém (podia ficar quebrada por
    semanas até alguém abrir a página por acaso). Só o papel que pode de
    fato reconectar (mesmo guard de `require_role("ADMIN")` nos endpoints de
    conectar/testar/desconectar) — diferente do público mais amplo de
    `approval.py::_notify_tenant_of_approval` (HITL, que qualquer staff pode
    resolver). Construído inline (não `notification.create_batch`, que
    comita sozinho) pra entrar na mesma transação do caller. Fail-soft: uma
    falha ao notificar (inclusive na própria query de destinatários) nunca
    pode propagar — os chamadores (`registrar_uso`/`testar_conexao`) contam
    com isso pra garantir que a atualização de `status` sempre se salve."""
    try:
        from app.models.user import User
        from app.models.notification import Notification
        from app.services.notification import publish_notification_ws

        user_ids = (await db.execute(
            select(User.id).where(
                User.tenant_id == integ.tenant_id,
                User.role.in_(("ADMIN", "SOCIO", "SUPERADMIN")),
                User.is_active == True,  # noqa: E712
            )
        )).scalars().all()
        for uid in user_ids:
            notif = Notification(
                user_id=uid,
                tipo="INTEGRACAO_ERRO",
                titulo=f"Integração {meta['nome']} parou de funcionar",
                corpo=detalhe or "A credencial precisa ser reconectada em Integrações.",
                priority="ALTA",
                link="/integracoes",
            )
            db.add(notif)
            await publish_notification_ws(notif)
    except Exception as exc:
        log.warning("integration_error_notification_failed", provider=getattr(integ, "provider", "?"), error=str(exc))


async def registrar_uso(db: AsyncSession, tenant_id, provider: str, sucesso: bool, detalhe: str | None = None) -> None:
    """Marca `last_success_at`/`last_error_at` a partir de um uso REAL da
    credencial (envio de e-mail/WhatsApp, captura de partes etc.) — não só
    do clique manual em "Testar conexão" (`testar_conexao()` abaixo). Sem
    isso uma integração podia ficar morta há semanas com a UI ainda
    mostrando CONECTADA (Fase 165).

    Auto-commit (mesmo padrão fail-soft de `notification.create_batch` —
    Fase 118/156): os chamadores vivem em contextos de transação muito
    diferentes (request FastAPI com auto-commit no fim, task Celery com
    commit explícito, ou nenhum dos dois), então a única forma confiável de
    a marca sobreviver é ela commitar por conta própria. Nunca propaga
    exceção — um erro aqui não pode derrubar o fluxo principal."""
    try:
        integ = await get_integration(db, tenant_id, provider)
        if not integ:
            return
        era_erro = integ.status == "ERRO"
        agora = datetime.now(timezone.utc)
        if sucesso:
            integ.last_success_at = agora
            integ.status = "CONECTADA"
        else:
            integ.last_error_at = agora
            integ.last_error_detail = (detalhe or "")[:500]
            integ.status = "ERRO"
            # Fase 177.2 — só na TRANSIÇÃO pra ERRO (evita notificar de novo
            # a cada chamada falhando enquanto já está em erro).
            if not era_erro:
                meta = PROVIDERS.get(provider)
                if meta:
                    await _notify_integration_error(db, integ, meta, detalhe)
        await db.commit()
    except Exception as exc:
        log.warning("integration_registrar_uso_falhou", provider=provider, error=str(exc))


class _WhatsAppFonteTeste:
    """Adapter fino só pra expor `.testar()` no mesmo formato das fontes
    credenciadas (Fase 168) — WhatsApp não é uma `FonteProcessual` (não
    descobre/detalha processo), então não tem um `para_tenant()` próprio;
    isso só embrulha as 2 credenciais já decifradas."""

    def __init__(self, access_token: str | None, phone_number_id: str | None) -> None:
        self._access_token = access_token
        self._phone_number_id = phone_number_id

    async def testar(self) -> tuple[bool, str]:
        from app.services.whatsapp import testar_credenciais
        return await testar_credenciais(self._access_token, self._phone_number_id)


async def _fonte_credenciada_do_provider(db: AsyncSession, tenant_id, provider: str):
    """Instância da fonte credenciada de um provider (ou None se não testável)."""
    if provider == "pdpj":
        from app.integrations.fontes.pdpj_fonte import para_tenant
    elif provider == "escavador":
        from app.integrations.fontes.escavador_fonte import para_tenant
    elif provider == "judit":
        from app.integrations.fontes.judit_fonte import para_tenant
    elif provider == "jusbrasil":
        from app.integrations.fontes.jusbrasil_fonte import para_tenant
    elif provider == "whatsapp":
        creds = await get_credentials(db, tenant_id, provider)
        if not creds:
            return None
        return _WhatsAppFonteTeste(creds.get("access_token"), creds.get("phone_number_id"))
    else:
        return None
    return await para_tenant(db, tenant_id)


# Fase 242 (pagamento) + Fase 248.1 (clicksign/google_drive_doutrina/
# google_workspace) — mesma sonda "GET autenticado, 401/403 = credencial
# ruim" já usada pras fontes credenciadas, só que direto (sem a
# abstração FonteProcessual, que é de acompanhamento processual, não
# esses provedores). Cada entrada descreve como montar a chamada:
# `campo` é a chave do dict de credenciais decifradas; `auth` é "bearer"
# (header Authorization) ou "query" (token vai num query param, mesmo
# esquema que a Clicksign já usa em esign.py); `query_param`/`params`
# só valem pra auth="query"/parâmetros extras read-only.
_GET_TEST_PROBE: dict[str, dict] = {
    # Stripe: /v1/balance é o endpoint padrão de mercado pra validar uma
    # secret key (read-only, não move dinheiro).
    "stripe": {"url": "https://api.stripe.com/v1/balance", "campo": "secret_key", "auth": "bearer"},
    # Mercado Pago: /users/me é o equivalente (read-only, confirma o access_token).
    "mercadopago": {"url": "https://api.mercadopago.com/users/me", "campo": "access_token", "auth": "bearer"},
    # Clicksign autentica por query param (mesmo esquema já usado em
    # esign.py, não Bearer) — listagem paginada mínima, read-only.
    "clicksign": {
        "url": "https://app.clicksign.com/api/v1/documents", "campo": "api_token",
        "auth": "query", "query_param": "access_token", "params": {"limit": 1},
    },
    # Google Drive doutrina: `about?fields=user` é read-only e cabe no
    # escopo já concedido (drive.readonly).
    "google_drive_doutrina": {
        "url": "https://www.googleapis.com/drive/v3/about", "campo": "access_token",
        "auth": "bearer", "params": {"fields": "user"},
    },
    # Google Workspace: tokeninfo não depende de nenhum dos 4 escopos
    # concedidos (Gmail/Agenda/Drive/userinfo) — só confirma que o token
    # está vivo, mais robusto que escolher 1 das APIs concedidas.
    # `invalid_status`: confirmado empiricamente (Fase 248.1, contra a API
    # real do Google) que esse endpoint devolve 400 — não 401/403 — pra
    # token inválido/expirado; só aqui esse status extra conta como
    # "credencial inválida" em vez de "resposta inesperada".
    "google_workspace": {
        "url": "https://oauth2.googleapis.com/tokeninfo", "campo": "access_token", "auth": "query",
        "query_param": "access_token", "invalid_status": {400, 401, 403},
    },
}


async def _testar_via_get(provider: str, creds: dict) -> tuple[bool, str]:
    cfg = _GET_TEST_PROBE[provider]
    token = creds.get(cfg["campo"])
    if not token:
        return False, f"credencial '{cfg['campo']}' ausente"
    headers = {}
    params = dict(cfg.get("params") or {})
    if cfg["auth"] == "bearer":
        headers["Authorization"] = f"Bearer {token}"
    else:
        params[cfg["query_param"]] = token
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(cfg["url"], headers=headers, params=params)
        if resp.status_code == 200:
            return True, "credencial válida"
        if resp.status_code in cfg.get("invalid_status", (401, 403)):
            return False, "credencial inválida ou revogada"
        return False, f"resposta inesperada do provedor (HTTP {resp.status_code})"
    except httpx.HTTPError as exc:
        return False, f"falha de conexão: {str(exc)[:120]}"


async def testar_conexao(db: AsyncSession, tenant_id, provider: str) -> dict:
    """Testa a credencial conectada e atualiza o `status` (CONECTADA/ERRO).

    Para as fontes credenciadas (pdpj/escavador/judit/jusbrasil), pra WhatsApp
    (Fase 168) e pros gateways/serviços com sonda GET registrada em
    `_GET_TEST_PROBE` (stripe/mercadopago — Fase 242; clicksign/
    google_drive_doutrina/google_workspace — Fase 248.1) faz uma sonda
    autenticada que distingue 401/403 (credencial inválida/expirada) de
    sucesso. Para os demais provedores não há teste automático — retorna
    o status atual. Não faz commit (o chamador comita). Detecção de
    expiração = este teste marcando ERRO."""
    if provider not in PROVIDERS:
        return {"ok": False, "status": "DESCONHECIDO", "detail": "provedor desconhecido", "detail_friendly": None}
    integ = await get_integration(db, tenant_id, provider)
    if not integ or not integ.credentials_enc:
        return {"ok": False, "status": "DESCONECTADA", "detail": "não conectado", "detail_friendly": None}

    era_erro = integ.status == "ERRO"
    if provider in _GET_TEST_PROBE:
        creds = await get_credentials(db, tenant_id, provider)
        try:
            ok, detail = await _testar_via_get(provider, creds or {})
        except Exception as exc:
            ok, detail = False, str(exc)[:120]
        integ.status = "CONECTADA" if ok else "ERRO"
        agora = datetime.now(timezone.utc)
        if ok:
            integ.last_success_at = agora
        else:
            integ.last_error_at = agora
            integ.last_error_detail = (detail or "")[:500]
            if not era_erro:
                meta = PROVIDERS.get(provider)
                if meta:
                    await _notify_integration_error(db, integ, meta, detail)
        await db.flush()
        log.info("integration_test", provider=provider, tenant_id=str(tenant_id), ok=ok)
        return {"ok": ok, "status": integ.status, "detail": detail, "detail_friendly": friendly_detail(detail) if not ok else None}

    fonte = await _fonte_credenciada_do_provider(db, tenant_id, provider)
    if fonte is None:
        return {"ok": True, "status": integ.status,
                "detail": "teste automático não disponível para este provedor", "detail_friendly": None}

    try:
        ok, detail = await fonte.testar()
    except Exception as exc:
        ok, detail = False, str(exc)[:120]
    integ.status = "CONECTADA" if ok else "ERRO"
    agora = datetime.now(timezone.utc)
    if ok:
        integ.last_success_at = agora
    else:
        integ.last_error_at = agora
        integ.last_error_detail = (detail or "")[:500]
        # Fase 177.2 — mesma checagem de transição de registrar_uso() acima.
        if not era_erro:
            meta = PROVIDERS.get(provider)
            if meta:
                await _notify_integration_error(db, integ, meta, detail)
    await db.flush()
    log.info("integration_test", provider=provider, tenant_id=str(tenant_id), ok=ok)
    return {"ok": ok, "status": integ.status, "detail": detail, "detail_friendly": friendly_detail(detail) if not ok else None}


async def disconnect(db: AsyncSession, tenant_id, provider: str) -> bool:
    """Desconecta o provedor — apaga só a CREDENCIAL, não a linha inteira.

    Fase 248.1 (achado do diagnóstico de UX): antes fazia `db.delete(integ)`,
    apagando `extra_data` junto (ex.: `folder_id` do Drive) — reconectar
    perdia a config e exigia reconfigurar do zero. Agora só limpa o que é
    de fato "credencial"/estado de conexão; `extra_data` sobrevive, e
    `save_credentials()` (upsert) reaproveita a mesma linha ao reconectar."""
    integ = await get_integration(db, tenant_id, provider)
    if not integ:
        return False
    integ.credentials_enc = None
    integ.status = "DESCONECTADA"
    integ.connected_by = None
    integ.connected_at = None
    integ.last_success_at = None
    integ.last_error_at = None
    integ.last_error_detail = None
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
            "oauth_disponivel": bool(meta.get("oauth_disponivel")) and is_oauth_configured(key),
            # Fase 248.1 — deriva por `credentials_enc`, não só por
            # `integ.status`: desde que `disconnect()` passou a preservar a
            # linha (pra manter `extra_data`), uma linha sem credencial
            # precisa continuar aparecendo como DESCONECTADA mesmo que
            # `status` tenha ficado com um valor antigo por algum caminho
            # que não passe por `disconnect()`.
            "status": (integ.status if integ and integ.credentials_enc else "DESCONECTADA"),
            "connected_at": integ.connected_at.isoformat() if integ and integ.connected_at else None,
            "last_success_at": integ.last_success_at.isoformat() if integ and integ.last_success_at else None,
            "last_error_at": integ.last_error_at.isoformat() if integ and integ.last_error_at else None,
            "last_error_detail": (integ.last_error_detail if integ else None),
            # Fase 248.3 — tradução amigável do detail cru acima. Cobre os
            # 2 caminhos que escrevem `last_error_detail` (registrar_uso, uso
            # real da credencial, e testar_conexao, teste manual) num só
            # lugar, na leitura, em vez de duplicar a lógica nos dois pontos
            # de escrita.
            "last_error_friendly": friendly_detail(integ.last_error_detail if integ else None),
            # Metadados não-sensíveis (ex.: folder_id do Drive, Fase 138.2) —
            # nunca contém credencial, sempre seguro expor.
            "extra_data": (integ.extra_data or {}) if integ else {},
        })
    return out


# ─── OAuth "Conectar conta" — Fase 117 (Stripe Connect, Mercado Pago) ─────────
# Config de cada provedor OAuth. `token_field` é a MESMA chave já usada pelo
# form de colar chave manualmente (`fields` em PROVIDERS acima) — assim o
# token OAuth fica no lugar exato que payment_gateway.py já lê hoje
# (`creds["secret_key"]`/`creds["access_token"]`), sem precisar tocar em
# nenhum consumidor existente.
#
# Nota honesta (a validar contra credenciais reais na implementação — não
# verificável neste ambiente sem client_id/secret de verdade cadastrados):
# os nomes de parâmetro abaixo seguem a documentação pública de cada
# provedor (Stripe Connect OAuth / Mercado Pago OAuth Marketplace), mas só
# um teste ponta a ponta com credenciais reais confirma 100%.
OAUTH_PROVIDERS: dict[str, dict] = {
    "stripe": {
        "authorize_url": "https://connect.stripe.com/oauth/authorize",
        "token_url": "https://connect.stripe.com/oauth/token",
        "scope": "read_write",
        "client_id_setting": "STRIPE_OAUTH_CLIENT_ID",
        "client_secret_setting": "STRIPE_OAUTH_CLIENT_SECRET",
        "redirect_uri_setting": "STRIPE_OAUTH_REDIRECT_URI",
        "token_field": "secret_key",
        # Tokens do Stripe Connect OAuth não expiram (documentado pelo
        # provedor) — sem expires_in na resposta, então nunca precisam de
        # renovação; _refresh_oauth_if_needed vira no-op pra este provider.
    },
    "mercadopago": {
        "authorize_url": "https://auth.mercadopago.com.br/authorization",
        "token_url": "https://api.mercadopago.com/oauth/token",
        "scope": None,
        "client_id_setting": "MERCADOPAGO_OAUTH_CLIENT_ID",
        "client_secret_setting": "MERCADOPAGO_OAUTH_CLIENT_SECRET",
        "redirect_uri_setting": "MERCADOPAGO_OAUTH_REDIRECT_URI",
        "token_field": "access_token",
        # Expira em 180 dias (confirmado na pesquisa) — precisa renovar via
        # refresh_token, tratado em _refresh_oauth_if_needed.
    },
    # Fase 138.2 — reaproveita o mesmo client_id/secret do Google Cloud
    # Console usado pelos outros fluxos Google deste hub, só com um
    # redirect_uri próprio (Google aceita múltiplos redirect_uri por
    # client_id — os fluxos coexistem sem conflito). O refresh do Google
    # é o fluxo OAuth2 clássico que _refresh_oauth_if_needed já implementa
    # de forma genérica — nada específico de Google precisa ser adicionado ali.
    "google_drive_doutrina": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scope": "https://www.googleapis.com/auth/drive.readonly",
        "client_id_setting": "GOOGLE_CLIENT_ID",
        "client_secret_setting": "GOOGLE_CLIENT_SECRET",
        "redirect_uri_setting": "GOOGLE_DRIVE_OAUTH_REDIRECT_URI",
        "token_field": "access_token",
    },
    # Fase 139 — substitui o antigo OAuth pessoal por usuário
    # (google_workspace.py::SCOPES) por uma conexão única do escritório.
    # 4 escopos consolidados numa só tela de consentimento (antes eram
    # pedidos separadamente, sempre os mesmos 4, só que por usuário).
    "google_workspace": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        # Fase 258 — `drive.metadata.readonly` adicionado pra permitir listar
        # pastas pré-existentes do Drive do usuário (seletor real de pasta de
        # salvamento, substituindo o fluxo antigo sem pasta configurável
        # nenhuma). `drive.file` sozinho NÃO permite listar — só ver/criar
        # arquivos que a própria app criou; `drive.metadata.readonly` é o
        # escopo de menor privilégio que resolve isso (lê só nome/id/
        # mimeType, nunca conteúdo de arquivo — `drive.readonly`, usado por
        # google_drive_doutrina, seria mais amplo do que necessário aqui).
        # Contas já conectadas continuam funcionando pras 3 permissões
        # antigas; só a listagem de pasta falha (escopo_insuficiente, ver
        # client.py::_classificar_erro_drive) até o ADMIN clicar "Conectar
        # com login" de novo — access_type=offline+prompt=consent (abaixo)
        # já força a tela de consentimento a cada reconexão.
        "scope": (
            "https://www.googleapis.com/auth/calendar.events "
            "https://www.googleapis.com/auth/drive.file "
            "https://www.googleapis.com/auth/drive.metadata.readonly "
            "https://www.googleapis.com/auth/gmail.send "
            "https://www.googleapis.com/auth/userinfo.email"
        ),
        "client_id_setting": "GOOGLE_CLIENT_ID",
        "client_secret_setting": "GOOGLE_CLIENT_SECRET",
        "redirect_uri_setting": "GOOGLE_WORKSPACE_OAUTH_REDIRECT_URI",
        "token_field": "access_token",
    },
    # Fase 177.1 — Keycloak/PJe-KC SSO do PDPJ: `grant_type=password` na 1ª
    # conexão (login direto, sem redirect — ver `exchange_oauth_password`
    # abaixo) e `grant_type=refresh_token` depois, via `_exchange_oauth_refresh`
    # já genérico — por isso não tem `authorize_url`/`redirect_uri_setting`
    # (não é o fluxo authorization_code que os provedores acima usam).
    # `token_url_setting` (em vez de `token_url` fixo) porque o endpoint SSO
    # tem variante staging/produção — configurável sem mudar código.
    "pdpj": {
        "token_url_setting": "PDPJ_OAUTH_TOKEN_URL",
        "client_id_setting": "PDPJ_OAUTH_CLIENT_ID",
        "client_secret_setting": "PDPJ_OAUTH_CLIENT_SECRET",
        "token_field": "sso_token",
    },
}


def _resolve_token_url(cfg: dict) -> str:
    return cfg.get("token_url") or getattr(settings, cfg.get("token_url_setting", ""), "")


def is_oauth_configured(provider: str) -> bool:
    cfg = OAUTH_PROVIDERS.get(provider)
    if not cfg:
        return False
    ok = bool(
        getattr(settings, cfg["client_id_setting"], "")
        and getattr(settings, cfg["client_secret_setting"], "")
    )
    if cfg.get("redirect_uri_setting"):
        ok = ok and bool(getattr(settings, cfg["redirect_uri_setting"], ""))
    return ok


def build_oauth_url(provider: str, state: str) -> str:
    from urllib.parse import urlencode
    cfg = OAUTH_PROVIDERS[provider]
    params = {
        "client_id": getattr(settings, cfg["client_id_setting"]),
        "redirect_uri": getattr(settings, cfg["redirect_uri_setting"]),
        "response_type": "code",
        "state": state,
    }
    if provider == "mercadopago":
        params["platform_id"] = "mp"
    if provider in ("google_drive_doutrina", "google_workspace"):
        # Sem isso o Google só devolve refresh_token na primeira conexão de
        # todas — access_type=offline+prompt=consent garante em toda conexão.
        params["access_type"] = "offline"
        params["prompt"] = "consent"
    if cfg.get("scope"):
        params["scope"] = cfg["scope"]
    return f"{cfg['authorize_url']}?{urlencode(params)}"


async def exchange_oauth_code(provider: str, code: str) -> dict:
    """Troca o authorization code por tokens (1ª conexão)."""
    cfg = OAUTH_PROVIDERS[provider]
    data = {
        "client_secret": getattr(settings, cfg["client_secret_setting"]),
        "code": code,
        "grant_type": "authorization_code",
    }
    if provider in ("mercadopago", "google_drive_doutrina", "google_workspace"):
        # Google exige client_id+redirect_uri na troca do code (não só no refresh).
        data["client_id"] = getattr(settings, cfg["client_id_setting"])
        data["redirect_uri"] = getattr(settings, cfg["redirect_uri_setting"])
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(_resolve_token_url(cfg), data=data)
        resp.raise_for_status()
        return resp.json()


async def _exchange_oauth_refresh(provider: str, refresh_token: str) -> dict:
    cfg = OAUTH_PROVIDERS[provider]
    data = {
        "client_id": getattr(settings, cfg["client_id_setting"]),
        "client_secret": getattr(settings, cfg["client_secret_setting"]),
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(_resolve_token_url(cfg), data=data)
        resp.raise_for_status()
        return resp.json()


async def exchange_oauth_password(provider: str, username: str, password: str) -> dict:
    """Troca usuário+senha por tokens via `grant_type=password` (Fase 177.1 —
    login direto do PDPJ/Keycloak, sem redirect). A senha nunca é persistida:
    usada 1x nesta chamada e descartada — só o `access_token`/`refresh_token`
    devolvido é guardado (via `save_oauth_tokens`, mesmo caminho já usado pelo
    fluxo `authorization_code` dos outros provedores)."""
    cfg = OAUTH_PROVIDERS[provider]
    data = {
        "client_id": getattr(settings, cfg["client_id_setting"]),
        "client_secret": getattr(settings, cfg["client_secret_setting"]),
        "grant_type": "password",
        "username": username,
        "password": password,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(_resolve_token_url(cfg), data=data)
        resp.raise_for_status()
        return resp.json()


def _oauth_tokens_to_credentials(provider: str, tokens: dict, fallback_refresh: str | None = None) -> dict:
    """Monta o dict salvo em `credentials_enc` a partir da resposta do provedor.

    `token_field` é a mesma chave do form manual (ver OAUTH_PROVIDERS acima) —
    é isso que torna a leitura transparente pros consumidores existentes."""
    cfg = OAUTH_PROVIDERS[provider]
    creds = {
        "__oauth__": True,
        cfg["token_field"]: tokens["access_token"],
        "oauth_refresh_token": tokens.get("refresh_token") or fallback_refresh,
    }
    expires_in = tokens.get("expires_in")
    if expires_in:
        creds["oauth_expires_at"] = (
            datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        ).isoformat()
    return creds


async def save_oauth_tokens(
    db: AsyncSession, tenant_id, provider: str, tokens: dict, connected_by=None,
) -> TenantIntegration:
    creds = _oauth_tokens_to_credentials(provider, tokens)
    integ = await get_integration(db, tenant_id, provider)
    if not integ:
        integ = TenantIntegration(tenant_id=tenant_id, provider=provider, extra_data={})
        db.add(integ)
    integ.credentials_enc = encrypt(json.dumps(creds))
    integ.status = "CONECTADA"
    integ.connected_by = connected_by
    integ.connected_at = datetime.now(timezone.utc)
    await db.flush()
    log.info("integration_connected_oauth", provider=provider, tenant_id=str(tenant_id))
    return integ


async def _refresh_oauth_if_needed(db: AsyncSession, integ: TenantIntegration, provider: str, creds: dict) -> dict:
    """Renova o token OAuth se estiver perto de expirar. No-op se o provider
    não expõe `oauth_expires_at` (ex.: Stripe, cujo token não expira)."""
    expires_at_raw = creds.get("oauth_expires_at")
    if not expires_at_raw:
        return creds
    try:
        expires_at = datetime.fromisoformat(expires_at_raw)
    except ValueError:
        return creds
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at > datetime.now(timezone.utc) + timedelta(seconds=60):
        return creds

    refresh_token = creds.get("oauth_refresh_token")
    if not refresh_token:
        log.warning("oauth_credential_expired_no_refresh", provider=provider, tenant_id=str(integ.tenant_id))
        # Fase 165 — antes o status ficava CONECTADA pra sempre nesse caso;
        # sem refresh_token o token expirado nunca vai se renovar sozinho.
        await registrar_uso(db, integ.tenant_id, provider, sucesso=False, detalhe="token OAuth expirado, sem refresh_token disponível")
        return creds
    try:
        tokens = await _exchange_oauth_refresh(provider, refresh_token)
    except Exception as exc:
        log.warning("oauth_refresh_failed", provider=provider, error=str(exc))
        await registrar_uso(db, integ.tenant_id, provider, sucesso=False, detalhe=f"falha ao renovar token OAuth: {str(exc)[:400]}")
        return creds

    new_creds = _oauth_tokens_to_credentials(provider, tokens, fallback_refresh=refresh_token)
    integ.credentials_enc = encrypt(json.dumps(new_creds))
    integ.status = "CONECTADA"
    integ.last_success_at = datetime.now(timezone.utc)
    await db.flush()
    log.info("oauth_token_refreshed", provider=provider, tenant_id=str(integ.tenant_id))
    return new_creds


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
