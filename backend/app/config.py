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
    DATABASE_URL: str
    POSTGRES_USER: str = "afj"
    POSTGRES_PASSWORD: str = ""   # auto-derived from DATABASE_URL if empty
    POSTGRES_DB: str = "afj_core"

    # ─── Redis ───────────────────────────────────────────────────────────────
    REDIS_URL: str
    REDIS_PASSWORD: str = ""       # auto-derived from REDIS_URL if empty
    CELERY_BROKER_URL: str = ""    # defaults to REDIS_URL
    CELERY_RESULT_BACKEND: str = ""  # defaults to REDIS_URL

    # ─── Qdrant ──────────────────────────────────────────────────────────────
    QDRANT_URL: str = "http://qdrant:6333"
    QDRANT_API_KEY: str = ""

    # ─── Segurança ───────────────────────────────────────────────────────────
    SECRET_KEY: str
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

    # ─── IA ──────────────────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    DEFAULT_CLAUDE_MODEL: str = "claude-opus-4-7"
    DEFAULT_EMBEDDING_MODEL: str = "text-embedding-3-large"
    EMBEDDING_DIMENSIONS: int = 3072

    # ─── Polling ─────────────────────────────────────────────────────────────
    PROCESS_POLLING_INTERVAL_MINUTES: int = 30
    PROCESS_POLLING_BATCH_SIZE: int = 50
    PUBLICATION_SCAN_HOUR: int = 7

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
        # Derive ENCRYPTION_KEY from SECRET_KEY if not set
        if not self.ENCRYPTION_KEY and self.SECRET_KEY:
            self.ENCRYPTION_KEY = self.SECRET_KEY[:32].ljust(32, "0")
        return self


settings = Settings()
