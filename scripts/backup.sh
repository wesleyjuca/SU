#!/usr/bin/env bash
# Backup manual do PostgreSQL — AFJ CORE SYSTEM
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="afj_backup_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

if [ -z "${DATABASE_URL:-}" ]; then
  echo "Erro: variável DATABASE_URL não definida" >&2
  exit 1
fi

echo "Iniciando backup: ${FILENAME}"
pg_dump "$DATABASE_URL" | gzip > "${BACKUP_DIR}/${FILENAME}"

SIZE=$(du -h "${BACKUP_DIR}/${FILENAME}" | cut -f1)
echo "Backup concluído: ${BACKUP_DIR}/${FILENAME} (${SIZE})"

# Manter apenas os últimos 30 backups
cd "$BACKUP_DIR"
ls -t afj_backup_*.sql.gz 2>/dev/null | tail -n +31 | xargs -r rm --
echo "Limpeza concluída. Backups retidos: $(ls afj_backup_*.sql.gz 2>/dev/null | wc -l)"
