import os

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from app.config import settings


# Fallback placeholder prevents crash at import when DATABASE_URL is not yet set.
# All actual queries will fail gracefully (connection refused) instead of at startup.
_db_url = settings.DATABASE_URL or "postgresql+asyncpg://notset:notset@127.0.0.1:5432/notset"

_has_real_db = bool(settings.DATABASE_URL)

# `AFJ_DB_NULLPOOL=1` desliga o pool de conexões. **Só a suíte de testes liga
# isso** (`tests/conftest.py`, antes de importar a app); produção nunca define
# essa variável e continua com o QueuePool de sempre.
#
# Por que existe: cada teste async roda no seu próprio event loop, mas o engine
# é um singleton de módulo — uma conexão criada no loop do teste N fica no pool
# e é reusada no loop do teste N+1. No teardown, o asyncpg tenta cancelar a
# operação no loop original, já fechado, e o pytest reporta
# `RuntimeError: Event loop is closed` como ERRO de teardown. Era a causa da
# maior parte dos erros de `tests/test_api/` (75 numa medição de 193 testes) e
# de ~25 fases de "flakiness de pool asyncpg" documentadas no CLAUDE.md.
# Sem pool, cada conexão nasce e morre dentro do loop que a usou, e a classe
# inteira de erro desaparece — ao custo de abrir uma conexão por request, que
# em teste é irrelevante.
_pool_kwargs: dict = (
    {"poolclass": NullPool}
    if os.getenv("AFJ_DB_NULLPOOL") == "1"
    else {
        "pool_recycle": 300,
        "pool_size": 5 if _has_real_db else 1,
        "max_overflow": 10 if _has_real_db else 0,
    }
)

engine = create_async_engine(
    _db_url,
    echo=settings.DEBUG,
    pool_pre_ping=_has_real_db,  # skip ping when using placeholder
    connect_args={"timeout": 5},  # fail fast when DB unreachable
    **_pool_kwargs,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
