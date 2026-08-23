#!/bin/sh
# Boot de produção (Railway single-service): sobe o worker Celery + beat em
# background e o uvicorn em background também, com um watchdog observando os
# dois. Sem isto, tarefas enfileiradas com Redis ativo (agentes IA, OCR,
# alertas de prazo) nunca são consumidas.
# Estado ideal futuro: serviços dedicados `worker` e `scheduler` no Railway,
# separando web de background; este script cobre o deploy de serviço único.
#
# Fase 227 — achado real: antes deste watchdog, o Celery subia em background
# (`&`) e o script terminava com `exec uvicorn ...`, que troca o processo do
# shell pelo do uvicorn — a partir daí, NADA observava o Celery. O healthcheck
# do Railway (`railway.toml`, `healthcheckPath = "/ping"`) e o
# `restartPolicyType = "ON_FAILURE"` só enxergam o uvicorn: se o Celery cair
# por qualquer motivo depois do boot (blip de reconexão do Redis, OOM por
# concorrência com o uvicorn no mesmo container, exceção não tratada no
# bootstrap), o site continuava respondendo normalmente e o Railway nunca
# percebia nada errado — as 12 tarefas agendadas (agentes de IA, OCR, alertas
# de prazo, capturas periódicas) ficavam mortas silenciosamente até o próximo
# deploy manual. Bate exatamente com o sintoma "Celery não funciona" sem
# nenhum erro visível na aplicação web.
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

CELERY_PID=""

start_celery() {
  celery -A app.workers.worker worker \
    --beat \
    --loglevel=info \
    --concurrency="${CELERY_CONCURRENCY:-2}" \
    --max-tasks-per-child=50 &
  CELERY_PID=$!
}

if [ -n "$REDIS_URL" ] || [ -n "$CELERY_BROKER_URL" ]; then
  echo "[AFJ] Iniciando Celery worker + beat (broker configurado)…"
  start_celery
else
  echo "[AFJ] Sem broker (REDIS_URL/CELERY_BROKER_URL) — tarefas rodarão no fallback in-process."
fi

uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" &
UVICORN_PID=$!

# Propaga sinal de encerramento (ex.: Railway matando o container num
# redeploy) pros processos filhos — antes disso era garantido de graça pelo
# `exec uvicorn` (que virava o processo principal); como uvicorn agora roda
# em background igual o Celery, sem este trap um SIGTERM mataria só o shell,
# deixando os filhos órfãos sem aviso de shutdown.
trap 'echo "[AFJ] Sinal de encerramento recebido — propagando…"; kill -TERM "$UVICORN_PID" "$CELERY_PID" 2>/dev/null; wait; exit 0' TERM INT

# Watchdog: se o Celery morrer, religa só ele (zero downtime do site por um
# problema isolado do lado de background tasks). Se o uvicorn morrer, encerra
# o script — é o processo que o healthcheck /ping observa, então deixar o
# restartPolicyType=ON_FAILURE do railway.toml (já configurado) reiniciar o
# container inteiro é o comportamento certo, igual já era antes.
while true; do
  sleep 10
  if [ -n "$CELERY_PID" ] && ! kill -0 "$CELERY_PID" 2>/dev/null; then
    echo "[AFJ][WARN] Processo Celery (pid $CELERY_PID) morreu — religando…"
    start_celery
  fi
  if ! kill -0 "$UVICORN_PID" 2>/dev/null; then
    echo "[AFJ][FATAL] Processo uvicorn (pid $UVICORN_PID) morreu — encerrando pra forçar restart do container."
    exit 1
  fi
done
