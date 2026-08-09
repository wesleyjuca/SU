"""Task Celery: alerta proativo de infra pro Cérebro (Fase 164).

Antes desta fase, `coletar_infra()` (Celery/Redis/Qdrant/circuit breakers das
fontes de captura) só rodava quando um SUPERADMIN abria a aba Infraestrutura
do painel Cérebro — 100% pull-based. Se algo quebrasse fora desse momento
(madrugada, fim de semana), ninguém era avisado. Esta task roda periodicamente
(Celery Beat) e reaproveita o fan-out já usado pra propostas de agente
customizado (`custom_agents.py::propose_custom_agent`, `create_batch` pra
todos os SUPERADMIN da plataforma).

Debounce: cada subsistema tem seu último estado conhecido ("ok"/"broken")
persistido no Redis (`infra_alert_state:<chave>`, TTL de 7 dias como rede de
segurança contra crescimento ilimitado de chaves por nome de fonte dinâmico).
Notifica só na TRANSIÇÃO de estado (ok→broken dispara alerta; broken→ok
dispara aviso de normalização) — nunca a cada tick de 5min enquanto o
problema persiste. Sem Redis configurado, não há como detectar transição
(toda leitura de estado voltaria vazia) — a task pula o fan-out inteiro
nesse caso (loga e sai) em vez de notificar a cada execução, o que seria
spam, não alerta.

Redis/Qdrant não configurados (`configured: False`) NÃO contam como
"quebrado" — são infra opcional, ausência é esperada em ambientes sem essas
credenciais (mesmo espírito de degradação graciosa do resto do sistema).
"""
from sqlalchemy import select
import structlog

from app.workers.worker import celery_app

log = structlog.get_logger()

_ESTADO_TTL_SEGUNDOS = 7 * 24 * 3600


def _checks_de(infra: dict) -> list[tuple[str, bool, str]]:
    """Extrai (chave, quebrado, label) dos subsistemas alertáveis do snapshot
    de `coletar_infra()`. Só entram subsistemas configurados/aplicáveis —
    Redis/Qdrant ausentes por falta de credencial não contam como quebra."""
    checks: list[tuple[str, bool, str]] = [
        ("celery", not infra["celery"].get("ok"), "Celery (workers)"),
    ]
    redis_info = infra.get("redis", {})
    if redis_info.get("configured"):
        checks.append(("redis", not redis_info.get("ok"), "Redis"))
    qdrant_info = infra.get("qdrant", {})
    if qdrant_info.get("configured"):
        checks.append(("qdrant", not qdrant_info.get("ok"), "Qdrant"))
    for f in (infra.get("fontes") or {}).get("fontes", []):
        nome = f.get("nome") or "?"
        checks.append((f"fonte:{nome}", f.get("breaker") == "OPEN", f"Fonte de captura ({nome})"))
    return checks


async def executar_infra_check(db) -> dict:
    """Lógica separada do wrapper Celery pra ser testável/chamável direto com
    uma sessão real e um cliente Redis fake."""
    from app.services.brain_infra import coletar_infra
    from app.services.notification import create_batch
    from app.db.redis import get_redis
    from app.models.user import User

    infra = await coletar_infra()
    checks = _checks_de(infra)

    try:
        redis = await get_redis()
    except Exception as exc:
        log.warning("infra_check_redis_indisponivel", error=str(exc))
        redis = None
    if redis is None:
        log.info("infra_check_sem_redis_pulando_alertas", checks=len(checks))
        return {"checks": len(checks), "alertas": 0, "normalizacoes": 0, "sem_redis": True}

    superadmin_ids = (await db.execute(select(User.id).where(User.role == "SUPERADMIN"))).scalars().all()

    alertas = 0
    normalizacoes = 0
    for chave, quebrado, label in checks:
        redis_key = f"infra_alert_state:{chave}"
        try:
            estado_anterior = await redis.get(redis_key)
        except Exception as exc:
            log.warning("infra_check_redis_get_falhou", key=redis_key, error=str(exc))
            continue
        novo_estado = "broken" if quebrado else "ok"
        if estado_anterior == novo_estado:
            continue  # sem mudança de estado — nada a notificar
        if quebrado and superadmin_ids:
            await create_batch(
                db, superadmin_ids,
                titulo=f"Infra indisponível: {label}",
                tipo="INFRA_ALERTA",
                corpo=f"{label} está reportando falha na checagem periódica de infraestrutura. Revise em Cérebro → Infraestrutura.",
                priority="ALTA",
                link="/admin/cerebro?aba=infra",
            )
            alertas += 1
        elif not quebrado and estado_anterior == "broken" and superadmin_ids:
            await create_batch(
                db, superadmin_ids,
                titulo=f"Infra normalizada: {label}",
                tipo="INFRA_ALERTA",
                corpo=f"{label} voltou a responder normalmente na checagem periódica de infraestrutura.",
                priority="NORMAL",
                link="/admin/cerebro?aba=infra",
            )
            normalizacoes += 1
        try:
            await redis.set(redis_key, novo_estado, ex=_ESTADO_TTL_SEGUNDOS)
        except Exception as exc:
            log.warning("infra_check_redis_set_falhou", key=redis_key, error=str(exc))

    log.info("infra_check_complete", checks=len(checks), alertas=alertas, normalizacoes=normalizacoes)
    return {"checks": len(checks), "alertas": alertas, "normalizacoes": normalizacoes}


@celery_app.task(
    name="app.workers.tasks.infra_check.checar_infra_periodico", bind=True, max_retries=3,
    time_limit=120, soft_time_limit=90,
)
def checar_infra_periodico(self):
    """Executa `executar_infra_check()` — roda via Beat a cada 5min."""
    from app.workers.async_utils import run_worker_coro

    async def _run():
        from app.db.base import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            return await executar_infra_check(db)

    async def _run_with_lock():
        from app.workers.task_lock import TaskLock

        lock = TaskLock("checar_infra_periodico", ttl_seconds=280)
        if not await lock.acquire():
            log.info("task_skipped_lock_held", task="checar_infra_periodico")
            return {"skipped": True, "reason": "lock_held"}
        try:
            return await _run()
        finally:
            await lock.release()

    try:
        return run_worker_coro(_run_with_lock())
    except Exception as exc:
        log.error("infra_check_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=60)
