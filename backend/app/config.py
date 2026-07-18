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
    # de Integrações). Redirect deve apontar para /api/v1/integrations/google/callback.
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = ""
    DEFAULT_EMBEDDING_MODEL: str = "text-embedding-3-large"
    EMBEDDING_DIMENSIONS: int = 3072

    # ─── Polling ─────────────────────────────────────────────────────────────
    PROCESS_POLLING_INTERVAL_MINUTES: int = 30
    PROCESS_POLLING_BATCH_SIZE: int = 50
    PUBLICATION_SCAN_HOUR: int = 7
    DEADLINE_ALERT_DAYS: list[int] = [3, 7, 15]

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
