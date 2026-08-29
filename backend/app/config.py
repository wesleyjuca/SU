from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, model_validator
from urllib.parse import urlparse
import json


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ─── Aplicação ───────────────────────────────────────────────────────────
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    PROJECT_NAME: str = "AFJ CORE SYSTEM"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    # ─── Banco de dados ──────────────────────────────────────────────────────
    DATABASE_URL: str = ""  # obrigatório em produção; vazio → app inicia em modo degradado
    POSTGRES_USER: str = "afj"
    POSTGRES_PASSWORD: str = ""   # auto-derived from DATABASE_URL if empty
    POSTGRES_DB: str = "afj_core"

    # ─── Redis ───────────────────────────────────────────────────────────────
    REDIS_URL: str = ""            # opcional — sem Redis, rate-limit/blacklist viram no-op
    REDIS_PASSWORD: str = ""       # auto-derived from REDIS_URL if empty
    CELERY_BROKER_URL: str = ""    # defaults to REDIS_URL
    CELERY_RESULT_BACKEND: str = ""  # defaults to REDIS_URL

    # ─── Qdrant ──────────────────────────────────────────────────────────────
    QDRANT_URL: str = "http://qdrant:6333"
    QDRANT_API_KEY: str = ""

    # ─── Segurança ───────────────────────────────────────────────────────────
    SECRET_KEY: str = ""           # opcional — gera fallback efêmero se vazio (ver derive_from_urls)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ENCRYPTION_KEY: str = ""       # generated from SECRET_KEY if empty

    # ─── CORS ────────────────────────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # URL pública do sistema (usada em redirects de pagamento e webhooks).
    # Se vazio, usa o primeiro CORS origin.
    PUBLIC_BASE_URL: str = ""

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return [v]
        return v

    # ─── Integrações externas ────────────────────────────────────────────────
    # Chave PÚBLICA do CNJ DataJud (compartilhada abertamente na doc:
    # https://datajud-wiki.cnj.jus.br/api-publica/acesso). O CNJ pode rotacioná-la
    # a qualquer momento — se o enriquecimento parar, basta setar a env CNJ_API_KEY.
    CNJ_API_KEY: str = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="

    # ─── IA ──────────────────────────────────────────────────────────────────
    AI_PROVIDER: str = "anthropic"          # "anthropic" | "gemini" (Google)
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""                # chave do Google AI Studio / Vertex (aceita GOOGLE_API_KEY)
    GOOGLE_API_KEY: str = ""                # alias — copiado para GEMINI_API_KEY se este estiver vazio
    DEFAULT_CLAUDE_MODEL: str = "claude-sonnet-5"
    DEFAULT_GEMINI_MODEL: str = "gemini-2.5-flash"

    # ─── Google Workspace (OAuth) ────────────────────────────────────────────
    # Sem credenciais, a integração fica "não configurada" (instruções no card
    # de Integrações).
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # Fase 117 — OAuth do hub de integrações (Stripe Connect / Mercado Pago),
    # mesmo padrão do Google acima: sem credenciais, o provedor continua
    # oferecendo só o fluxo de colar chave manualmente (fallback existente).
    # Redirect deve apontar para /api/v1/integrations/hub/{provider}/oauth/callback.
    STRIPE_OAUTH_CLIENT_ID: str = ""
    STRIPE_OAUTH_CLIENT_SECRET: str = ""
    STRIPE_OAUTH_REDIRECT_URI: str = ""
    MERCADOPAGO_OAUTH_CLIENT_ID: str = ""
    MERCADOPAGO_OAUTH_CLIENT_SECRET: str = ""
    MERCADOPAGO_OAUTH_REDIRECT_URI: str = ""
    # Fase 248.1 — assinatura HMAC do webhook (camada extra sobre a
    # re-verificação real já existente em payment_gateway.py, que sempre
    # confirma via GET autenticado antes de marcar qualquer fatura como
    # paga). Um segredo só por plataforma (não por tenant): a URL do
    # webhook é única (`/integrations/webhooks/{provider}`) e recebe
    # eventos de todos os escritórios conectados — mesmo modelo do
    # Stripe Connect/Mercado Pago marketplace. Opcional: sem o secret
    # configurado, a verificação é pulada silenciosamente (mesmo padrão
    # de opcionalidade de `is_oauth_configured`) — senão o deploy
    # quebraria o webhook de todo tenant já conectado no instante em que
    # o código sobe, antes de alguém configurar o secret na plataforma.
    STRIPE_WEBHOOK_SECRET: str = ""
    MERCADOPAGO_WEBHOOK_SECRET: str = ""
    # Fase 138.2 — OAuth do Google Drive em nível de TENANT (pasta de doutrina
    # do escritório), distinto do OAuth pessoal (GOOGLE_REDIRECT_URI acima).
    # Reaproveita GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET (mesmo client do Google
    # Cloud Console já configurado) — só o redirect_uri é próprio, já que o
    # Google permite múltiplos redirect_uri cadastrados no mesmo client_id.
    # Deve apontar para /api/v1/integrations/hub/google_drive_doutrina/oauth/callback.
    GOOGLE_DRIVE_OAUTH_REDIRECT_URI: str = ""
    # Fase 139 — OAuth do Google Workspace em nível de TENANT (Gmail+Agenda+
    # Drive do escritório, substitui o antigo fluxo pessoal por usuário).
    # Reaproveita GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET, redirect_uri próprio
    # (3º redirect cadastrado no mesmo client_id — Google permite múltiplos).
    # Deve apontar para /api/v1/integrations/hub/google_workspace/oauth/callback.
    GOOGLE_WORKSPACE_OAUTH_REDIRECT_URI: str = ""
    # Fase 177.1 — login OAuth2 (Keycloak, grant_type=password) do PDPJ/CNJ
    # Corporativo, mesmo padrão de "só liga quando configurado" dos outros
    # OAuth acima. Sem redirect_uri: o SSO do PJe-KC aceita usuário+senha
    # direto no POST do token endpoint (não é o fluxo authorization_code com
    # redirect que Stripe/Mercado Pago/Google usam) — client_id/client_secret
    # precisam ser obtidos com o CNJ (integracaopdpj@cnj.jus.br).
    PDPJ_OAUTH_CLIENT_ID: str = ""
    PDPJ_OAUTH_CLIENT_SECRET: str = ""
    PDPJ_OAUTH_TOKEN_URL: str = "https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/token"
    # Fase 217 — Consulta CPF/CNPJ (Loja SERPRO, canal comercial self-service,
    # fora do Conecta gov.br gratuito). Sem CONSUMER_KEY/SECRET configurados,
    # a validação de documento simplesmente não roda (fail-soft, nunca bloqueia
    # cadastro de cliente). Base URLs apontam pro modo trial/sandbox por
    # padrão — trocar pra produção só depois de um contrato pago ativo.
    SERPRO_TOKEN_URL: str = "https://gateway.apiserpro.serpro.gov.br/token"
    SERPRO_API_CONSUMER_KEY: str = ""
    SERPRO_API_CONSUMER_SECRET: str = ""
    SERPRO_CPF_BASE_URL: str = "https://gateway.apiserpro.serpro.gov.br/consulta-cpf-df-trial/v1"
    SERPRO_CNPJ_BASE_URL: str = "https://gateway.apiserpro.serpro.gov.br/consulta-cnpj-df-trial/v2"
    DEFAULT_EMBEDDING_MODEL: str = "text-embedding-3-large"
    EMBEDDING_DIMENSIONS: int = 3072

    # ─── Polling ─────────────────────────────────────────────────────────────
    PROCESS_POLLING_INTERVAL_MINUTES: int = 30
    PROCESS_POLLING_BATCH_SIZE: int = 50
    # Resumir cada andamento com IA no polling em LOTE é caro (1 chamada Claude por
    # movimento × todos os processos, a cada 30 min). Desligado por padrão — o resumo
    # continua disponível sob demanda. Ligue (env POLL_AI_SUMMARY=true) se quiser.
    POLL_AI_SUMMARY: bool = False
    PUBLICATION_SCAN_HOUR: int = 7
    DEADLINE_ALERT_DAYS: list[int] = [3, 7, 15]
    # Fase 191 — prazo padrão pra uma Approval PENDENTE ser escalada (nunca
    # auto-resolvida — HITL nunca pode pular a aprovação humana) se ninguém
    # decidir a tempo.
    APPROVAL_EXPIRY_DAYS: int = 5

    @field_validator("DEADLINE_ALERT_DAYS", mode="before")
    @classmethod
    def parse_deadline_alert_days(cls, v):
        if isinstance(v, str):
            try:
                import json as _json
                return _json.loads(v)
            except Exception:
                return [int(x.strip()) for x in v.split(",") if x.strip().isdigit()]
        return v

    # ─── Email (SMTP) ─────────────────────────────────────────────────────────
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "afj-core@afjadvogados.com.br"
    SMTP_FROM_NAME: str = "AFJ CORE SYSTEM"
    EMAIL_ENABLED: bool = False      # set True when SMTP_USER and SMTP_PASSWORD are configured

    # ─── Sentry ──────────────────────────────────────────────────────────────
    SENTRY_DSN: str = ""             # leave empty to disable Sentry

    # ─── Web Push (VAPID) ────────────────────────────────────────────────────
    VAPID_PRIVATE_KEY: str = ""      # generate: py_vapid.Vapid().generate_keys()
    VAPID_PUBLIC_KEY: str = ""       # corresponding DER base64url public key
    VAPID_EMAIL: str = "mailto:dev@afjadvogados.com.br"
    PUSH_ENABLED: bool = False       # True when VAPID keys are configured

    # ─── Armazenamento de objetos (S3/MinIO) ────────────────────────────────
    # Fase 141 — migra uploads novos de Document.arquivo_url (base64 no
    # Postgres, ver CLAUDE.md "Storage de documentos") para object storage
    # S3-compatível. Funciona igual para AWS S3, Cloudflare R2, MinIO ou
    # Railway Object Storage — todos falam a API S3. Sem credenciais, o
    # upload continua gravando base64 inline como sempre fez (fail-soft) —
    # fica pro primeiro ADMIN que configurar depois do deploy, mesmo padrão
    # do Google Workspace/Stripe Connect/Mercado Pago OAuth já shipados.
    S3_ENDPOINT_URL: str = ""        # ex.: https://<account>.r2.cloudflarestorage.com. Vazio = endpoint padrão da AWS.
    S3_BUCKET: str = ""
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""
    S3_REGION: str = "auto"          # "auto" funciona pra R2/MinIO; na AWS real, setar a região (ex. "us-east-1")
    S3_ADDRESSING_STYLE: str = "path"  # path-style: exigido por MinIO/R2, aceito pela AWS

    @model_validator(mode="after")
    def derive_from_urls(self) -> "Settings":
        # DATABASE_URL obrigatória em produção — avisa mas não impede startup
        if not self.DATABASE_URL:
            print(
                "[AFJ][ERROR] DATABASE_URL não definido — banco indisponível. "
                "No Railway: Variables → DATABASE_URL = ${{Postgres.DATABASE_URL}}",
                flush=True,
            )
        # Normalizar DATABASE_URL para o driver async — o Railway fornece postgresql://
        if self.DATABASE_URL:
            url = self.DATABASE_URL
            if url.startswith("postgres://"):
                url = "postgresql://" + url[len("postgres://"):]
            if url.startswith("postgresql://"):
                url = "postgresql+asyncpg://" + url[len("postgresql://"):]
            # asyncpg rejeita params libpq na URL (sslmode/channel_binding/gssencmode)
            if "?" in url:
                base, _, query = url.partition("?")
                kept = [kv for kv in query.split("&")
                        if kv and kv.split("=", 1)[0] not in {"sslmode", "channel_binding", "gssencmode"}]
                url = base + ("?" + "&".join(kept) if kept else "")
            self.DATABASE_URL = url

        # Gemini: aceitar GOOGLE_API_KEY como alias de GEMINI_API_KEY
        if not self.GEMINI_API_KEY and self.GOOGLE_API_KEY:
            self.GEMINI_API_KEY = self.GOOGLE_API_KEY

        # Fill Celery URLs from Redis if not set
        if not self.CELERY_BROKER_URL:
            self.CELERY_BROKER_URL = self.REDIS_URL
        if not self.CELERY_RESULT_BACKEND:
            self.CELERY_RESULT_BACKEND = self.REDIS_URL
        # Extract REDIS_PASSWORD from REDIS_URL if not set
        if not self.REDIS_PASSWORD and self.REDIS_URL:
            parsed = urlparse(self.REDIS_URL)
            if parsed.password:
                self.REDIS_PASSWORD = parsed.password
        # Extract POSTGRES_PASSWORD from DATABASE_URL if not set
        if not self.POSTGRES_PASSWORD and self.DATABASE_URL:
            parsed = urlparse(self.DATABASE_URL)
            if parsed.password:
                self.POSTGRES_PASSWORD = parsed.password
        # SECRET_KEY: obrigatório em produção (chave efêmera invalidaria todos os
        # JWT a cada restart e tornaria indecifráveis as chaves BYOK cifradas).
        # Em dev/test, mantém o fallback efêmero com aviso.
        if not self.SECRET_KEY:
            if self.ENVIRONMENT == "production":
                raise RuntimeError(
                    "SECRET_KEY é obrigatório em produção — configure SECRET_KEY "
                    "(e ENCRYPTION_KEY) nas variáveis do Railway antes de subir o serviço."
                )
            import secrets as _secrets
            self.SECRET_KEY = _secrets.token_urlsafe(48)
            print(
                "[AFJ][WARN] SECRET_KEY não definido — gerado valor efêmero. "
                "Tokens são invalidados a cada restart. "
                "Configure SECRET_KEY para sessões estáveis.",
                flush=True,
            )
        # Derive ENCRYPTION_KEY from SECRET_KEY if not set
        if not self.ENCRYPTION_KEY and self.SECRET_KEY:
            self.ENCRYPTION_KEY = self.SECRET_KEY[:32].ljust(32, "0")
        return self


settings = Settings()
