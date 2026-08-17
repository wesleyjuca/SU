#!/bin/sh
# Boot de produção (Railway single-service): sobe o worker Celery + beat em
# background e o uvicorn em foreground. Sem isto, tarefas enfileiradas com
# Redis ativo (agentes IA, OCR, alertas de prazo) nunca são consumidas.
# Estado ideal futuro: serviços dedicados `worker` e `scheduler` no Railway,
# separando web de background; este script cobre o deploy de serviço único.
set -e

# Migração pontual de dados de um banco antigo (Fase 199 — troca de provedor
# de Postgres sem downtime pra quem não tem acesso a terminal): se
# MIGRATE_FROM_URL estiver definida, copia o banco inteiro de lá pro banco
# atual (DATABASE_URL) ANTES do app subir. Roda em toda inicialização
# enquanto a variável existir — REMOVA `MIGRATE_FROM_URL` do Railway assim
# que confirmar que a migração deu certo, senão todo redeploy/restart
# apaga dados novos e restaura o snapshot antigo de novo.
if [ -n "$MIGRATE_FROM_URL" ]; then
  echo "[AFJ] MIGRATE_FROM_URL definida — copiando dados do banco antigo…"
  if pg_dump "$MIGRATE_FROM_URL" --no-owner --no-acl -F c -f /tmp/legacy_backup.dump; then
    # DATABASE_URL vem no formato asyncpg (postgresql+asyncpg://...?ssl=require);
    # pg_restore precisa do formato padrão (postgresql://...?sslmode=require).
    RESTORE_URL=$(echo "$DATABASE_URL" | sed -e 's#postgresql+asyncpg://#postgresql://#' -e 's#[?&]ssl=require#?sslmode=require#')
    if pg_restore --no-owner --no-acl --clean --if-exists -d "$RESTORE_URL" /tmp/legacy_backup.dump; then
      echo "[AFJ] Migração de dados concluída."
    else
      echo "[AFJ][WARN] pg_restore terminou com avisos (alguns objetos podem já não existir) — seguindo o boot."
    fi
  else
    echo "[AFJ][WARN] pg_dump do banco antigo falhou — seguindo o boot sem migrar dados."
  fi
  rm -f /tmp/legacy_backup.dump
fi

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
