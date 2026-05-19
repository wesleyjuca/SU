"""Celery worker — tarefas agendadas e em background do AFJ CORE SYSTEM."""
from celery import Celery
from celery.schedules import crontab
from app.config import settings

celery_app = Celery(
    "afj_core",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks.process_polling", "app.workers.tasks.deadline_check"],
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
}
