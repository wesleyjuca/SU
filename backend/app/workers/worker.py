"""Celery worker — tarefas agendadas e em background do AFJ CORE SYSTEM."""
import structlog
from celery import Celery
from celery.schedules import crontab
from app.config import settings

# Fase 174.1 — garante que TODOS os models (incluindo Tenant/TenantConfig,
# registrados no Base.metadata só quando a classe é importada) estejam
# carregados antes de qualquer task rodar. Sem isto, o processo do worker
# nunca tocava app.models.tenant (nenhuma task incluída abaixo importa
# Tenant), e o primeiro commit envolvendo uma FK pra "tenants"
# (agent_runs.tenant_id, sync_runs.tenant_id) explodia com
# NoReferencedTableError — o processo do FastAPI só escapava disso porque
# app/core/events.py::lifespan importa Tenant explicitamente no boot.
import app.models  # noqa: F401

log = structlog.get_logger()

# Fase 163 — Sentry só era inicializado em main.py (processo web); exceções
# do lado do worker (falha de poll, falha de sync, lock preso mid-loop)
# nunca eram reportadas em lugar nenhum externo, só nos logs locais.
# Mesmo padrão opcional de main.py (só inicializa se SENTRY_DSN estiver
# configurado), com CeleryIntegration no lugar de FastApiIntegration.
if settings.SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENVIRONMENT,
            release=f"afj-core@{settings.VERSION}",
            traces_sample_rate=0.1,
            integrations=[CeleryIntegration(), SqlalchemyIntegration()],
            send_default_pii=False,
        )
        log.info("sentry_initialized_worker", environment=settings.ENVIRONMENT)
    except ImportError:
        log.warning("sentry_sdk_not_installed", hint="pip install sentry-sdk[celery]")

celery_app = Celery(
    "afj_core",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.tasks.process_polling",
        "app.workers.tasks.deadline_check",
        "app.workers.tasks.agent_tasks",
        "app.workers.tasks.ocr_tasks",
        "app.workers.tasks.session_cleanup",
        "app.workers.tasks.jurisprudencia_sync",
        "app.workers.tasks.google_drive_sync",
        "app.workers.tasks.legislacao_sync",
        "app.workers.tasks.infra_check",
        "app.workers.tasks.sync_reaper",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Fortaleza",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
)

celery_app.conf.beat_schedule = {
    # Polling de processos a cada 30 minutos
    "poll-processes": {
        "task": "app.workers.tasks.process_polling.poll_all_processes",
        "schedule": crontab(minute=f"*/{settings.PROCESS_POLLING_INTERVAL_MINUTES}"),
    },
    # Verificação de prazos vencendo (diária às 7h)
    "check-deadlines": {
        "task": "app.workers.tasks.deadline_check.check_upcoming_deadlines",
        "schedule": crontab(hour=7, minute=0),
    },
    # Scan de publicações DJe (diário às 7h30)
    "scan-publications": {
        "task": "app.workers.tasks.deadline_check.scan_daily_publications",
        "schedule": crontab(hour=7, minute=30),
    },
    # Limpeza de sessões expiradas (semanal, madrugada de domingo — baixo custo)
    "cleanup-sessions": {
        "task": "app.workers.tasks.session_cleanup.cleanup_expired_sessions",
        "schedule": crontab(hour=3, minute=0, day_of_week=0),
    },
    # Sincronização diária de jurisprudência do STJ (Fase 138.1) — casa com a
    # cadência de atualização incremental do próprio portal.
    "sync-stj-jurisprudencia": {
        "task": "app.workers.tasks.jurisprudencia_sync.sync_stj_diario",
        "schedule": crontab(hour=4, minute=0),
    },
    # Sincronização diária das pastas de doutrina do Google Drive, por
    # escritório (Fase 138.2).
    "sync-google-drive-doutrina": {
        "task": "app.workers.tasks.google_drive_sync.sync_google_drive_doutrina",
        "schedule": crontab(hour=5, minute=0),
    },
    # Sincronização diária de legislação federal via LexML/Planalto
    # (Fase 138.3) — horário distinto de STJ (4h) e Drive (5h) pra não
    # competir por I/O/CPU no mesmo minuto.
    "sync-legislacao-federal": {
        "task": "app.workers.tasks.legislacao_sync.sync_legislacao_diario",
        "schedule": crontab(hour=6, minute=0),
    },
    # Alerta proativo de infra (Fase 164) — antes o painel Cérebro só via
    # o estado das fontes/Celery/Redis/Qdrant quando um SUPERADMIN abria a
    # aba manualmente; agora avisa por notificação na transição de estado.
    "checar-infra-periodico": {
        "task": "app.workers.tasks.infra_check.checar_infra_periodico",
        "schedule": crontab(minute="*/5"),
    },
    # Reaper de SyncRun travados em RUNNING (Fase 167) — rede de segurança
    # pro cenário residual que try/except não cobre (processo morto sem
    # desenrolar a pilha, ex.: OOM kill).
    "reapear-syncs-travados": {
        "task": "app.workers.tasks.sync_reaper.reapear_syncs_travados_periodico",
        "schedule": crontab(minute="*/30"),
    },
}
