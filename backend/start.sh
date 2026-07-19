#!/bin/sh
# Boot de produção (Railway single-service): sobe o worker Celery + beat em
# background e o uvicorn em foreground. Sem isto, tarefas enfileiradas com
# Redis ativo (agentes IA, OCR, alertas de prazo) nunca são consumidas.
# Estado ideal futuro: serviços dedicados `worker` e `scheduler` no Railway
# (ver infra/railway.toml); este script cobre o deploy de serviço único.
set -e

# Auto-migração best-effort: em bancos legados criados via create_all (sem
# carimbo do alembic), `upgrade head` falha em "table already exists" — não pode
# derrubar o boot (set -e). O startup do app aplica create_all + ALTERs de
# qualquer forma; para alinhar o alembic num banco legado, rode uma única vez:
#   alembic stamp head
echo "[AFJ] Auto-migrando banco de dados (alembic upgrade head)…"
if ! alembic upgrade head; then
  echo "[AFJ][WARN] alembic falhou (banco legado sem carimbo?) — seguindo; o startup aplica create_all/ALTERs."
fi

if [ -n "$REDIS_URL" ] || [ -n "$CELERY_BROKER_URL" ]; then
  echo "[AFJ] Iniciando Celery worker + beat (broker configurado)…"
  celery -A app.workers.worker worker \
    --beat \
    --loglevel=info \
    --concurrency="${CELERY_CONCURRENCY:-2}" \
    --max-tasks-per-child=50 &
else
  echo "[AFJ] Sem broker (REDIS_URL/CELERY_BROKER_URL) — tarefas rodarão no fallback in-process."
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
