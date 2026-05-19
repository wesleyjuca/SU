.PHONY: up down logs backend frontend migrate seed

# ─── Docker ───────────────────────────────────────────────────────────────────
up:
	cp -n .env.example .env 2>/dev/null || true
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

restart-backend:
	docker compose restart backend worker scheduler

# ─── Banco ────────────────────────────────────────────────────────────────────
migrate:
	docker compose exec backend alembic upgrade head

migrate-create:
	docker compose exec backend alembic revision --autogenerate -m "$(msg)"

seed:
	docker compose exec backend python scripts/seed_db.py

# ─── Dev ──────────────────────────────────────────────────────────────────────
backend-shell:
	docker compose exec backend bash

frontend-shell:
	docker compose exec frontend sh

# ─── Status ───────────────────────────────────────────────────────────────────
status:
	docker compose ps
	@echo ""
	@echo "Health check:"
	@curl -s http://localhost:8000/health | python3 -m json.tool 2>/dev/null || echo "Backend não disponível"
