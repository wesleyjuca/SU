"""Balanceamento automático entre as várias `AIProviderConfig` de um usuário
(Fase 137.6) — escolhe automaticamente qual config tentar primeiro em cada
chamada, em vez de só a ordem manual (padrão + prioridade) de sempre.

`ordenar_configs()` é a única função que decide a ordem — pura, sem I/O,
testável sem DB/crypto. `buscar_stats_recentes()`/`calcular_rotation_offset()`
são os únicos pontos com I/O (rodam dentro de `byok.py::user_ai_creds()`,
que já tem uma `session` em mãos — diferente de `ai_monitoring.py`, não
precisam abrir sessão própria).

Modo desconhecido/None é tratado como "padrao" (fail-soft) — nunca lança."""
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func, Integer

MODOS_VALIDOS = ("padrao", "round_robin", "performance")

# Janela de recência pro modo "performance" — deliberadamente diferente do
# all-time de GET /me/ai-configs/stats (que é um dashboard histórico). Uma
# decisão de roteamento ao vivo precisa reagir a comportamento RECENTE, não
# carregar pra sempre uma falha de meses atrás (ex.: chave que expirou e já
# foi corrigida). 7 dias é curto o bastante pra "esquecer" problemas já
# resolvidos, longo o bastante pra suavizar ruído de 1-2 chamadas isoladas
# em usuários de baixo volume.
JANELA_PERFORMANCE_DIAS = 7

_SCORE_NEUTRO_SEM_DADOS = 0.75
_PESO_SUCESSO = 0.60
_PESO_CUSTO = 0.25
_PESO_LATENCIA = 0.15


def _chave_padrao(config) -> tuple:
    prioridade = config.priority if config.priority is not None else float("inf")
    return (0 if config.is_default else 1, prioridade, config.created_at)


def _ordenar_padrao(configs: list) -> list:
    return sorted(configs, key=_chave_padrao)


def _ordenar_round_robin(configs: list, rotation_offset: int) -> list:
    # Ordena por (created_at, id) — ignora is_default/priority de propósito,
    # é o ponto do modo: todo mundo entra igual na roda.
    base = sorted(configs, key=lambda c: (c.created_at, str(c.id)))
    offset = rotation_offset % len(base)
    return base[offset:] + base[:offset]


def _score_performance(config_id: str, stats: dict, min_c: float, max_c: float, min_l: float, max_l: float) -> float:
    s = stats.get(config_id)
    if not s or not s.get("total_calls"):
        return _SCORE_NEUTRO_SEM_DADOS
    norm_custo = 1.0 if max_c == min_c else 1 - (s["avg_cost_usd"] - min_c) / (max_c - min_c)
    norm_lat = 1.0 if max_l == min_l else 1 - (s["avg_latency_ms"] - min_l) / (max_l - min_l)
    return _PESO_SUCESSO * s["success_rate"] + _PESO_CUSTO * norm_custo + _PESO_LATENCIA * norm_lat


def _ordenar_performance(configs: list, stats: dict) -> list:
    com_dados = [stats[str(c.id)] for c in configs if stats.get(str(c.id), {}).get("total_calls")]
    if com_dados:
        min_c, max_c = min(s["avg_cost_usd"] for s in com_dados), max(s["avg_cost_usd"] for s in com_dados)
        min_l, max_l = min(s["avg_latency_ms"] for s in com_dados), max(s["avg_latency_ms"] for s in com_dados)
    else:
        min_c = max_c = min_l = max_l = 0.0

    def _chave(c):
        score = _score_performance(str(c.id), stats, min_c, max_c, min_l, max_l)
        return (-score, c.created_at, str(c.id))  # score desc; empate determinístico

    return sorted(configs, key=_chave)


def ordenar_configs(
    configs: list, mode: str | None, *,
    stats: dict | None = None, rotation_offset: int = 0,
) -> list:
    """Reordena `configs` (objetos `AIProviderConfig`-like: `.id`,
    `.is_default`, `.priority`, `.created_at`) conforme `mode`. Modo
    desconhecido/None -> "padrao". 0 ou 1 config -> no-op sempre."""
    if len(configs) <= 1:
        return list(configs)
    if mode == "round_robin":
        return _ordenar_round_robin(configs, rotation_offset)
    if mode == "performance":
        return _ordenar_performance(configs, stats or {})
    return _ordenar_padrao(configs)


async def buscar_stats_recentes(session, user_id) -> dict:
    """Agregação em AICallLog (Fase 137.7) janelada aos últimos
    JANELA_PERFORMANCE_DIAS dias, escopada ao usuário. Devolve
    {config_id_str: {total_calls, success_rate, avg_latency_ms, avg_cost_usd}}."""
    from app.models.ai_call_log import AICallLog
    from app.models.ai_config import AIProviderConfig

    janela = datetime.now(timezone.utc) - timedelta(days=JANELA_PERFORMANCE_DIAS)
    rows = (await session.execute(
        select(
            AICallLog.config_id,
            func.count().label("total_calls"),
            func.sum(func.cast(AICallLog.success, Integer)).label("total_success"),
            func.avg(AICallLog.latency_ms).label("avg_latency_ms"),
            func.avg(AICallLog.cost_usd).label("avg_cost_usd"),
        )
        .join(AIProviderConfig, AIProviderConfig.id == AICallLog.config_id)
        .where(AIProviderConfig.user_id == user_id, AICallLog.created_at >= janela)
        .group_by(AICallLog.config_id)
    )).all()

    stats = {}
    for row in rows:
        total = row.total_calls or 0
        if not total:
            continue
        stats[str(row.config_id)] = {
            "total_calls": total,
            "success_rate": (row.total_success or 0) / total,
            "avg_latency_ms": float(row.avg_latency_ms or 0),
            "avg_cost_usd": float(row.avg_cost_usd or 0),
        }
    return stats


async def calcular_rotation_offset(session, user_id) -> int:
    """"Relógio" do round-robin: conta total de chamadas já registradas
    (todas as configs do usuário) — sem contador persistido. Chamadas
    simultâneas podem calcular o mesmo offset (aceito, ver docstring da
    fase no plano — não é um bug a perseguir)."""
    from app.models.ai_call_log import AICallLog
    from app.models.ai_config import AIProviderConfig

    total = (await session.execute(
        select(func.count()).select_from(AICallLog)
        .join(AIProviderConfig, AIProviderConfig.id == AICallLog.config_id)
        .where(AIProviderConfig.user_id == user_id)
    )).scalar_one()
    return total or 0
