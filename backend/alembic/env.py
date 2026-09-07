import asyncio
import os
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool

from alembic import context

# Importar todos os models para que o metadata seja populado
from app.db.base import Base
import app.models  # noqa: F401 — registra todos os modelos no metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Sobrescreve a URL com a variável de ambiente (produção e Docker).
# `or` em vez de `os.getenv(x, default)`: o 2º argumento de `getenv` é avaliado
# SEMPRE, e `get_main_option` levantava a exceção de interpolação mesmo com a
# env var setada — foi o que manteve todo comando alembic quebrado desde a
# Fase 136. Com `or`, o fallback do .ini só é lido se a env var faltar.
DATABASE_URL = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL não configurada — defina a variável de ambiente (ou "
        "sqlalchemy.url no alembic.ini) antes de rodar o alembic."
    )
# asyncpg → psycopg2 para alembic (que é síncrono no run_migrations_offline)
SYNC_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://") if DATABASE_URL else DATABASE_URL


def run_migrations_offline() -> None:
    context.configure(
        url=SYNC_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = DATABASE_URL
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
