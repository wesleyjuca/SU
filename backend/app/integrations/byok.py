"""BYOK (Bring Your Own Key) — aplica a IA própria do usuário disparador.

Ponto único e reutilizável para setar o contextvar `ai_creds_ctx` com as
credenciais de IA do usuário (quando há uma `AIProviderConfig` padrão ativa)
ao redor de uma execução de agente. Usado tanto pelo orquestrador quanto
pelos endpoints que invocam agentes diretamente (generate_petition,
review_document, geração de contrato), garantindo que a chave do usuário
economize os tokens do sistema.

Uso:
    async with user_ai_creds(session, current_user.id):
        result = await agent.run(ctx)

Fase 137.1 — resolve primeiro via `AIProviderConfig` (múltiplas IAs por
usuário, a config marcada `is_default=True` vence); se não houver nenhuma
config cadastrada (usuário nunca migrou/nunca usou BYOK), cai nas 4 colunas
antigas do `User` (`ai_provider`/`ai_api_key_enc`/`ai_model`/`ai_enabled`) —
zero regressão. Se nada decifrar/existir, o contexto é um no-op e o agente
cai no provider/chave do sistema — sem quebrar a execução.

Fase 137.3 — também monta a cadeia de fallback: além da config padrão, busca
as demais `enabled=True` do usuário (ordenadas `is_default DESC, priority ASC
NULLS LAST, created_at ASC`, até `_MAX_FALLBACK_CHAIN`) e expõe as restantes
via `ai_fallback_ctx`, pra `call_llm` tentar automaticamente se a padrão
falhar de um jeito recuperável. Efeito colateral bem-vindo: se a config
marcada como padrão estiver com a chave indecifrável (ex.: `ENCRYPTION_KEY`
trocada), a próxima config decifrável da lista vira a padrão efetiva desta
chamada, em vez do usuário cair de vez no provider do sistema.

Fase 137.4 — o "ajuste por área" (`AITaskOverride`) pode substituir a config
padrão por uma `AIProviderConfig` INTEIRA (provider+chave+modelo próprios)
pra um `task_type` específico, não só trocar a string do modelo. Se a config
referenciada sumiu/foi desativada/ficou indecifrável, cai pro `model` legado
da própria `AITaskOverride` (se houver) e, na ausência de qualquer um dos
dois, mantém a config padrão sem alteração — fail-soft em 3 níveis.

Fase 137.6 — a ordem final das configs (antes só `is_default DESC, priority
ASC NULLS LAST, created_at ASC`) agora pode vir de um "modo de balanceamento"
(`User.ai_balance_mode`, ver `app/services/ai_balance.py`): "padrao" (mesma
ordem de sempre), "round_robin" (revezamento) ou "performance" (score de
sucesso/custo/latência recentes via `AICallLog`). A busca deixa de aplicar
`ORDER BY`/`LIMIT` no SQL — busca todas as configs `enabled=True`, aplica o
modo em Python, só então corta pra `_MAX_FALLBACK_CHAIN`. `is_default`/
`priority` viram decorativos (não consultados) quando um modo automático
está ativo — o `_resolver_override()` acima continua rodando por cima do
resultado, então o ajuste por área sempre vence, não importa o modo.
"""
import json
from contextlib import asynccontextmanager
import structlog

log = structlog.get_logger()

# Padrão + até 2 fallbacks — bound de latência/custo no pior caso (o
# `BaseAgent.run()` já tem seu próprio retry externo, ver comentário em
# `llm_client.py`; uma cadeia maior componentizaria demais numa falha
# persistente).
_MAX_FALLBACK_CHAIN = 3


async def _resolver_override(session, user_id, task_type, primaria: dict) -> dict:
    """Aplica o "ajuste por área" (`AITaskOverride`) em cima da config já
    resolvida (`primaria`, mesmo formato de `ai_creds_ctx`). Fase 137.4:
    - `provider_config_id` válido/decifrável → substitui `primaria` inteira
      por essa outra `AIProviderConfig` (provider+chave+modelo próprios).
    - senão, `model` (legado da Fase 137.1) → troca só a string do modelo,
      mantendo provider/chave de `primaria`.
    - senão → devolve `primaria` sem alteração. Nunca lança — override
      quebrado/removido só significa "sem ajuste pra essa tarefa"."""
    if not task_type:
        return primaria
    from sqlalchemy import select
    from app.models.user import AITaskOverride

    override = (await session.execute(
        select(AITaskOverride).where(
            AITaskOverride.user_id == user_id,
            AITaskOverride.task_type == task_type,
        )
    )).scalar_one_or_none()
    if not override:
        return primaria

    if override.provider_config_id:
        from app.models.ai_config import AIProviderConfig
        from app.core.crypto import decrypt

        config = await session.get(AIProviderConfig, override.provider_config_id)
        if config and config.user_id == user_id and config.enabled:
            api_key = None
            if config.credentials_enc:
                raw = decrypt(config.credentials_enc)
                if raw:
                    try:
                        api_key = (json.loads(raw) or {}).get("api_key")
                    except Exception:
                        api_key = None
            if api_key or config.auth_method == "none":
                return {
                    "provider": config.provider, "api_key": api_key or "",
                    "model": config.model, "base_url": config.base_url,
                    "config_id": str(config.id),
                }
        # Config removida/desativada/indecifrável — cai pro model legado abaixo.

    if override.model:
        return {**primaria, "model": override.model}
    return primaria


@asynccontextmanager
async def user_ai_creds(session, user_id, task_type=None):
    """Context manager que ativa a IA própria (BYOK) do usuário, se houver,
    e a cadeia de fallback com as demais (Fase 137.3)."""
    token = None
    fallback_token = None
    if user_id is not None:
        try:
            from sqlalchemy import select
            from app.models.ai_config import AIProviderConfig
            from app.core.crypto import decrypt
            from app.integrations.llm_client import ai_creds_ctx, ai_fallback_ctx

            rows = (await session.execute(
                select(AIProviderConfig).where(
                    AIProviderConfig.user_id == user_id,
                    AIProviderConfig.enabled == True,  # noqa: E712
                )
            )).scalars().all()

            # Fase 137.6 — balanceamento automático: com mais de 1 config, a
            # ordem final pode vir de um modo diferente de "padrao" (ver
            # app/services/ai_balance.py). Com 0 ou 1 config, `ordenar_configs`
            # já é um no-op garantido — nem dispara as queries extras de
            # modo/stats abaixo.
            from app.services.ai_balance import (
                MODOS_VALIDOS, ordenar_configs, buscar_stats_recentes, calcular_rotation_offset,
            )

            modo = "padrao"
            stats = None
            offset = 0
            if len(rows) > 1:
                from app.models.user import User

                modo_raw = (await session.execute(
                    select(User.ai_balance_mode).where(User.id == user_id)
                )).scalar_one_or_none()
                modo = modo_raw if modo_raw in MODOS_VALIDOS else "padrao"
                if modo == "performance":
                    stats = await buscar_stats_recentes(session, user_id)
                elif modo == "round_robin":
                    offset = await calcular_rotation_offset(session, user_id)

            rows = ordenar_configs(rows, modo, stats=stats, rotation_offset=offset)[:_MAX_FALLBACK_CHAIN]

            resolvidas = []
            for config in rows:
                api_key = None
                if config.credentials_enc:
                    raw = decrypt(config.credentials_enc)
                    if raw:
                        try:
                            api_key = (json.loads(raw) or {}).get("api_key")
                        except Exception:
                            api_key = None
                if api_key or config.auth_method == "none":
                    resolvidas.append({
                        "provider": config.provider,
                        "api_key": api_key or "",
                        "model": config.model,
                        "base_url": config.base_url,
                        "config_id": str(config.id),
                    })
                else:
                    # Credencial salva mas indecifrável — normalmente a
                    # ENCRYPTION_KEY do servidor mudou. Pula pra próxima da
                    # cadeia (se houver); se for a única, cai no sistema.
                    log.warning("byok_decrypt_failed", user_id=str(user_id), config_id=str(config.id))

            if resolvidas:
                primaria = await _resolver_override(session, user_id, task_type, dict(resolvidas[0]))
                token = ai_creds_ctx.set(primaria)
                if len(resolvidas) > 1:
                    fallback_token = ai_fallback_ctx.set(resolvidas[1:])
            else:
                token = await _fallback_legado(session, user_id, task_type)
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
        if fallback_token is not None:
            try:
                from app.integrations.llm_client import ai_fallback_ctx
                ai_fallback_ctx.reset(fallback_token)
            except Exception:
                pass


async def _fallback_legado(session, user_id, task_type):
    """Compatibilidade: usuário sem nenhuma AIProviderConfig ainda (não
    migrado pelo backfill, ou linha removida manualmente) — lê as 4 colunas
    antigas do User, exatamente como antes da Fase 137.1. Retorna o token do
    contextvar (pra o chamador poder resetar no finally) ou None se no-op."""
    from sqlalchemy import select
    from app.models.user import User
    from app.core.crypto import decrypt
    from app.integrations.llm_client import ai_creds_ctx

    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not (user and getattr(user, "ai_enabled", False) and user.ai_api_key_enc):
        return None
    key = decrypt(user.ai_api_key_enc)
    if not key:
        log.warning("byok_decrypt_failed", user_id=str(user_id))
        return None
    primaria = await _resolver_override(session, user_id, task_type, {
        "provider": user.ai_provider or None,
        "api_key": key,
        "model": user.ai_model or None,
        "base_url": None,
    })
    return ai_creds_ctx.set(primaria)
