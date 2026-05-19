from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl, field_validator
from typing import Annotated
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
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str = "afj_core"

    # ─── Redis ───────────────────────────────────────────────────────────────
    REDIS_URL: str
    REDIS_PASSWORD: str
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str

    # ─── Qdrant ──────────────────────────────────────────────────────────────
    QDRANT_URL: str = "http://qdrant:6333"
    QDRANT_API_KEY: str = ""

    # ─── Segurança ───────────────────────────────────────────────────────────
    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ENCRYPTION_KEY: str

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
    ANTHROPIC_API_KEY: str
    OPENAI_API_KEY: str
    DEFAULT_CLAUDE_MODEL: str = "claude-opus-4-7"
    DEFAULT_EMBEDDING_MODEL: str = "text-embedding-3-large"
    EMBEDDING_DIMENSIONS: int = 3072

    # ─── Polling ─────────────────────────────────────────────────────────────
    PROCESS_POLLING_INTERVAL_MINUTES: int = 30
    PROCESS_POLLING_BATCH_SIZE: int = 50
    PUBLICATION_SCAN_HOUR: int = 7


settings = Settings()
