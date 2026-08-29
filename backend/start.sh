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
CELERY_START_TS=0
CELERY_FAST_DEATH_COUNT=0

# Fase 249 — achado real: o watchdog abaixo religava o Celery a cada morte
# sem NUNCA distinguir um blip transitório (reconexão de Redis, OOM
# passageiro — se recupera na religada) de uma config permanentemente
# quebrada (ex.: REDIS_URL/CELERY_RESULT_BACKEND com um `${{...}}` do
# Railway não resolvido) que crasha em bem menos de 1s, toda vez, pra
# sempre — e sem soar alarme nenhum. Como só o uvicorn é observado pelo
# healthcheck do Railway, o deploy inteiro aparecia "successful" enquanto
# TODA a beat_schedule (alertas de prazo, agentes de IA, sync de
# jurisprudência, capturas periódicas) ficava morta em silêncio — passou
# 16h despercebido em produção até alguém olhar o log bruto.
CELERY_MIN_HEALTHY_SECONDS="${CELERY_MIN_HEALTHY_SECONDS:-45}"
CELERY_CRASHLOOP_THRESHOLD="${CELERY_CRASHLOOP_THRESHOLD:-3}"
CELERY_ALERT_COOLDOWN_SECONDS="${CELERY_ALERT_COOLDOWN_SECONDS:-3600}"
ALERT_MARKER_FILE="${ALERT_MARKER_FILE:-/tmp/afj_celery_crashloop_alert.ts}"

start_celery() {
  celery -A app.workers.worker worker \
    --beat \
    --loglevel=info \
    --concurrency="${CELERY_CONCURRENCY:-2}" \
    --max-tasks-per-child=50 &
  CELERY_PID=$!
  CELERY_START_TS=$(date +%s)
}

# Dispara o alerta de crash-loop (Fase 249) — nunca deve derrubar o
# watchdog. `start.sh` tem `set -e` na 1ª linha, valendo pro script
# inteiro incluindo o loop abaixo: por isso todo passo aqui dentro é
# protegido (if/condicional, nunca um comando solto que pode falhar) e a
# função sempre termina com `return 0`, e é chamada com `|| echo ...` por
# precaução extra no call site.
maybe_alert_crashloop() {
  death_count="$1"
  now=$(date +%s)
  last=0
  if [ -f "$ALERT_MARKER_FILE" ]; then
    last=$(cat "$ALERT_MARKER_FILE" 2>/dev/null) || last=0
    case "$last" in ''|*[!0-9]*) last=0 ;; esac
  fi
  elapsed=$((now - last))
  if [ "$elapsed" -lt "$CELERY_ALERT_COOLDOWN_SECONDS" ]; then
    echo "[AFJ] Crash-loop já alertado há ${elapsed}s (cooldown ${CELERY_ALERT_COOLDOWN_SECONDS}s) — não reenviando."
    return 0
  fi
  echo "[AFJ][CRITICAL] Enviando alerta de crash-loop do Celery (mortes rápidas seguidas: ${death_count})…"
  if timeout 20 python3 -m app.scripts.alert_celery_crashloop "$death_count"; then
    echo "[AFJ] Alerta de crash-loop enviado."
  else
    echo "[AFJ][WARN] Falha ao enviar alerta de crash-loop — seguindo o watchdog (não é fatal)."
  fi
  date +%s > "$ALERT_MARKER_FILE" 2>/dev/null || true
  return 0
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
    NOW=$(date +%s)
    RAN_FOR=$((NOW - CELERY_START_TS))
    echo "[AFJ][WARN] Processo Celery (pid $CELERY_PID) morreu depois de ${RAN_FOR}s — religando…"
    if [ "$RAN_FOR" -lt "$CELERY_MIN_HEALTHY_SECONDS" ]; then
      CELERY_FAST_DEATH_COUNT=$((CELERY_FAST_DEATH_COUNT + 1))
    else
      CELERY_FAST_DEATH_COUNT=0
    fi
    start_celery
    if [ "$CELERY_FAST_DEATH_COUNT" -ge "$CELERY_CRASHLOOP_THRESHOLD" ]; then
      echo "[AFJ][CRITICAL] Celery crash-loop detectado (${CELERY_FAST_DEATH_COUNT}x mortes rápidas seguidas) — avaliando alerta…"
      maybe_alert_crashloop "$CELERY_FAST_DEATH_COUNT" || echo "[AFJ][WARN] maybe_alert_crashloop falhou — watchdog continua."
    fi
  fi
  if ! kill -0 "$UVICORN_PID" 2>/dev/null; then
    echo "[AFJ][FATAL] Processo uvicorn (pid $UVICORN_PID) morreu — encerrando pra forçar restart do container."
    exit 1
  fi
done
