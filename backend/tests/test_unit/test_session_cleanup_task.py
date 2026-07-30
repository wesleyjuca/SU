"""Fase 116 — task de limpeza de sessões expiradas está registrada no beat."""
from app.workers.worker import celery_app


def test_cleanup_sessions_registrado_no_beat_schedule():
    assert "cleanup-sessions" in celery_app.conf.beat_schedule
    entry = celery_app.conf.beat_schedule["cleanup-sessions"]
    assert entry["task"] == "app.workers.tasks.session_cleanup.cleanup_expired_sessions"


def test_task_cleanup_expired_sessions_esta_registrada():
    from app.workers.tasks import session_cleanup  # noqa: F401 — força o registro no celery_app

    assert "app.workers.tasks.session_cleanup.cleanup_expired_sessions" in celery_app.tasks
