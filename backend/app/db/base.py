from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings


# Fallback placeholder prevents crash at import when DATABASE_URL is not yet set.
# All actual queries will fail gracefully (connection refused) instead of at startup.
_db_url = settings.DATABASE_URL or "postgresql+asyncpg://notset:notset@127.0.0.1:5432/notset"

_has_real_db = bool(settings.DATABASE_URL)

engine = create_async_engine(
    _db_url,
    echo=settings.DEBUG,
    pool_pre_ping=_has_real_db,  # skip ping when using placeholder
    pool_recycle=300,
    pool_size=5 if _has_real_db else 1,
    max_overflow=10 if _has_real_db else 0,
    connect_args={"timeout": 5},  # fail fast when DB unreachable
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
