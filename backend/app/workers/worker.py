"""Celery worker — tarefas agendadas e em background do AFJ CORE SYSTEM."""
from celery import Celery
from celery.schedules import crontab
from app.config import settings

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
}
