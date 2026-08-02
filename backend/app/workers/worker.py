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
        "app.workers.tasks.google_drive_sync",
        "app.workers.tasks.legislacao_sync",
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
}
