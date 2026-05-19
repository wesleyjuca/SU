#!/usr/bin/env bash
# Executa migrações Alembic no container Docker ou diretamente.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== AFJ CORE — Database Migration ==="
echo "Project root: $PROJECT_ROOT"

cd "$PROJECT_ROOT"

if command -v docker compose &>/dev/null; then
  COMPOSE_CMD="docker compose"
elif command -v docker-compose &>/dev/null; then
  COMPOSE_CMD="docker-compose"
else
  COMPOSE_CMD=""
fi

if [ -n "$COMPOSE_CMD" ] && $COMPOSE_CMD ps backend 2>/dev/null | grep -q "Up"; then
  echo "Running migration via Docker Compose backend service..."
  $COMPOSE_CMD exec backend alembic upgrade head
  echo "Migration complete."
  exit 0
fi

if [ -n "${DATABASE_URL:-}" ]; then
  echo "Running migration directly (DATABASE_URL set)..."
  cd "$PROJECT_ROOT/backend"
  alembic upgrade head
  echo "Migration complete."
  exit 0
fi

if [ -f "$PROJECT_ROOT/.env" ]; then
  export $(grep -v '^#' "$PROJECT_ROOT/.env" | grep DATABASE_URL | xargs)
  if [ -n "${DATABASE_URL:-}" ]; then
    echo "Running migration with .env DATABASE_URL..."
    cd "$PROJECT_ROOT/backend"
    alembic upgrade head
    echo "Migration complete."
    exit 0
  fi
fi

echo "ERROR: Could not connect to database."
echo "Set DATABASE_URL environment variable or start Docker Compose services."
exit 1
