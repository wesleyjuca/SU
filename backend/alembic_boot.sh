#!/bin/sh
# Decide, sozinho, o que fazer com o alembic no boot: CARIMBAR ou MIGRAR.
#
# Regra: "carimbar, nunca migrar" — qualquer banco SEM carimbo recebe
# `stamp head`; só um banco JÁ carimbado recebe `upgrade head`.
#
# Por que banco vazio também é carimbado, e não migrado: medido na fase
# pós-260.7 que `upgrade head` num banco vazio produz um schema DIFERENTE do de
# todo ambiente existente — 27 tabelas (a cadeia de migração conhece 45% do
# schema; o app tem 58), mais as extensões uuid-ossp/pgcrypto e o trigger de
# imutabilidade de audit_logs, cuja criação é decisão jurídica em aberto
# (docs/juridico/RETENCAO_AUDIT_LOGS.md). Quem monta o schema neste projeto é o
# `create_all` + `DDL_IDEMPOTENTE` de events.py, em TODO ambiente; o alembic
# serve daqui pra frente, para migrações novas.
#
# Este script existe separado do start.sh porque tem DOIS chamadores com
# necessidades diferentes: o start.sh (Railway, que também sobe Celery
# worker+beat em background) e o docker-compose.prod.yml (VPS, onde Celery são
# serviços SEPARADOS — chamar o start.sh ali subiria um worker duplicado).
# A regra precisa valer nos dois, e viver num lugar só.
#
# Nunca derruba o boot: todo caminho termina em sucesso, porque o startup da
# app aplica create_all + DDL de qualquer forma.

echo "[AFJ] Auto-migrando banco de dados (alembic)…"

ALEMBIC_ESTADO="$(python3 - <<'PYEOF' 2>/dev/null || echo indeterminado
import asyncio, os, re, sys

url = os.getenv("DATABASE_URL", "")
if not url:
    print("indeterminado"); sys.exit(0)
# asyncpg fala o DSN puro, sem o dialeto do SQLAlchemy
dsn = re.sub(r"^postgresql\+asyncpg://", "postgresql://", url)

async def main():
    import asyncpg
    con = await asyncpg.connect(dsn, timeout=10)
    try:
        carimbado = await con.fetchval("SELECT to_regclass('public.alembic_version')")
        # Uma tabela conhecida basta pra dizer se o schema já existe.
        montado = await con.fetchval("SELECT to_regclass('public.users')")
    finally:
        await con.close()
    if carimbado: print("carimbado")
    elif montado: print("montado_sem_carimbo")
    else: print("vazio")

asyncio.run(main())
PYEOF
)"

case "$ALEMBIC_ESTADO" in
  vazio|montado_sem_carimbo)
    echo "[AFJ] Banco sem carimbo do alembic — aplicando 'stamp head' (não altera schema)."
    if ! alembic stamp head; then
      echo "[AFJ][WARN] alembic stamp falhou — seguindo; o startup aplica create_all/DDL."
    fi
    ;;
  carimbado)
    if ! alembic upgrade head; then
      echo "[AFJ][WARN] alembic upgrade falhou — seguindo; o startup aplica create_all/DDL."
    fi
    ;;
  *)
    echo "[AFJ][WARN] estado do alembic indeterminado — pulando; o startup aplica create_all/DDL."
    ;;
esac

exit 0
