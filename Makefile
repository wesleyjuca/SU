.PHONY: up down logs backend frontend migrate seed test lint format test-cov backup build-prod

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

# ─── Testes e qualidade ───────────────────────────────────────────────────────
test:
	docker compose exec backend pytest -v

test-cov:
	docker compose exec backend pytest --cov=app --cov-report=html --cov-report=term-missing

lint:
	docker compose exec backend ruff check app/

format:
	docker compose exec backend black app/

# ─── Produção ─────────────────────────────────────────────────────────────────
backup:
	bash scripts/backup.sh

build-prod:
	docker build -f backend/Dockerfile -t afj-backend:prod backend/

prod-up:
	docker compose -f docker-compose.prod.yml up -d

prod-down:
	docker compose -f docker-compose.prod.yml down

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
