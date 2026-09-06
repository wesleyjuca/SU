"""Sessão de banco com engine próprio, criado dentro do event loop do teste.

O engine de produção (`app.db.base.engine`) é singleton de módulo, mas o
pytest-asyncio cria um event loop por teste. Uma conexão aberta no loop de
um teste, devolvida ao pool e reusada no loop do teste seguinte, estoura
"attached to a different loop" — era a metade restante da flakiness
crônica documentada desde a Fase 199 (a outra metade, o conflito de dois
plugins async, foi corrigida em `pytest.ini`).

Testes que falam com Postgres de verdade usam este helper: o engine nasce
e morre dentro do próprio loop, e `NullPool` garante que nenhuma conexão
sobreviva ao teste para ser reusada em outro loop.

Alternativas medidas e descartadas na rodada pós-260.5, registradas para
não serem retentadas às cegas:
  - loop de escopo de sessão (`asyncio_default_*_loop_scope=session`):
    zera os erros, mas faz uma falha de fixture cascatear em ~38 pulos
    silenciosos — teste pulado num gate de CI é pior que teste que falha;
  - `engine.dispose()` autouse a cada teste: subiu os pulos de 42 para 78.
"""
import contextlib

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings


@contextlib.asynccontextmanager
async def sessao_isolada():
    """Devolve uma `AsyncSession` ligada a um engine exclusivo deste teste."""
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        criar_sessao = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with criar_sessao() as sessao:
            yield sessao
    finally:
        await engine.dispose()
