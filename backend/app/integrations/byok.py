"""BYOK (Bring Your Own Key) — aplica a IA própria do usuário disparador.

Ponto único e reutilizável para setar o contextvar `ai_creds_ctx` com as
credenciais de IA do usuário (quando `ai_enabled` + chave decifrável) ao redor
de uma execução de agente. Usado tanto pelo orquestrador quanto pelos endpoints
que invocam agentes diretamente (generate_petition, review_document, geração de
contrato), garantindo que a chave do usuário economize os tokens do sistema.

Uso:
    async with user_ai_creds(session, current_user.id):
        result = await agent.run(ctx)

Se o usuário não tem IA própria ativa, ou a chave não decifra (ex.: a
ENCRYPTION_KEY do servidor mudou), o contexto é um no-op e o agente cai no
provider/chave do sistema — sem quebrar a execução.
"""
from contextlib import asynccontextmanager
import structlog

log = structlog.get_logger()


@asynccontextmanager
async def user_ai_creds(session, user_id):
    """Context manager que ativa a IA própria (BYOK) do usuário, se houver."""
    token = None
    if user_id is not None:
        try:
            from sqlalchemy import select
            from app.models.user import User
            from app.core.crypto import decrypt
            from app.integrations.llm_client import ai_creds_ctx

            user = (
                await session.execute(select(User).where(User.id == user_id))
            ).scalar_one_or_none()
            if user and getattr(user, "ai_enabled", False) and user.ai_api_key_enc:
                key = decrypt(user.ai_api_key_enc)
                if key:
                    token = ai_creds_ctx.set({
                        "provider": user.ai_provider or None,
                        "api_key": key,
                        "model": user.ai_model or None,
                    })
                else:
                    # Chave salva mas indecifrável — normalmente a ENCRYPTION_KEY
                    # do servidor mudou. Cai no sistema; usuário deve re-salvar.
                    log.warning("byok_decrypt_failed", user_id=str(user_id))
        except Exception as exc:
            log.warning("byok_load_failed", error=str(exc))
    try:
        yield
    finally:
        if token is not None:
            try:
                from app.integrations.llm_client import ai_creds_ctx
                ai_creds_ctx.reset(token)
            except Exception:
                pass
