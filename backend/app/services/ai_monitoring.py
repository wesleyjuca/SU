"""Monitoramento por IA (Fase 137.7) — grava 1 `AICallLog` por chamada de LLM
feita com uma `AIProviderConfig` do usuário. Fail-soft por design: uma falha
aqui NUNCA pode derrubar a chamada de LLM real nem propagar erro pro
usuário — é só telemetria."""
import structlog

log = structlog.get_logger()


async def registrar_chamada_ia(
    config_id: str | None, provider: str, model: str | None, success: bool,
    error: str | None, input_tokens: int, output_tokens: int, cost_usd: float, latency_ms: int,
) -> None:
    """No-op se `config_id` for `None` (chamada sem uma IA do usuário
    atribuível — chave do sistema, fallback legado, etc.). Abre sua própria
    sessão (o chamador, `llm_client.py`, não tem uma `db` session à mão)."""
    if not config_id:
        return
    try:
        from app.db.base import AsyncSessionLocal
        from app.models.ai_call_log import AICallLog
        import uuid

        async with AsyncSessionLocal() as db:
            db.add(AICallLog(
                config_id=uuid.UUID(config_id), provider=provider, model=model,
                success=success, error=(str(error)[:255] if error else None),
                input_tokens=input_tokens or 0, output_tokens=output_tokens or 0,
                cost_usd=cost_usd or 0, latency_ms=latency_ms or 0,
            ))
            await db.commit()
    except Exception as exc:
        log.warning("ai_call_log_falhou", error=str(exc))
