"""Utilitários para execução de corrotinas dentro de tasks Celery."""
import asyncio


def run_worker_coro(coro):
    """Roda uma corrotina em um event loop dedicado e descarta o pool do engine
    ao fim.

    Cada task Celery cria um novo loop via asyncio.run(); sem descartar o pool,
    a conexão asyncpg reutilizada na task seguinte fica presa ao loop anterior
    (já fechado) → 'got Future attached to a different loop' / 'Event loop is
    closed'. Chamar engine.dispose() ao término garante que nenhuma conexão
    sobreviva ao loop que a criou. Roda apenas no processo worker (a API nunca
    executa estas tasks).
    """
    async def _runner():
        try:
            return await coro
        finally:
            from app.db.base import engine
            await engine.dispose()

    return asyncio.run(_runner())
