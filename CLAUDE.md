# AFJ CORE SYSTEM

## Architecture

```
frontend/  → Next.js 14 App Router (Vercel)
backend/   → FastAPI Python 3.12 (Railway)
```

- **Database**: PostgreSQL (Railway) — SQLAlchemy async ORM
- **Cache**: Redis (Railway) — Celery task queue + session cache
- **Vector Search**: Qdrant — RAG for jurisprudência search
- **AI**: Anthropic Claude 3 + LangGraph orchestration + 19 specialized agents
- **Auth**: JWT (access + refresh tokens) + httpOnly cookies for session

## Local Development

```bash
# All services via Docker
docker compose up -d

# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev  # http://localhost:3000
```

## Environment Variables

### Backend (`.env`)
```
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://localhost:6379
SECRET_KEY=<random-64-chars>
ENCRYPTION_KEY=<random-32-chars>
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
ENVIRONMENT=development
CORS_ORIGINS=["http://localhost:3000"]
```

### Frontend (`.env.local`)
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Backend Structure

```
backend/app/
  api/v1/          — 82 REST endpoints (15 routers)
  agents/          — 19 LangGraph agents + orchestrator
  models/          — SQLAlchemy ORM models
  schemas/         — Pydantic request/response schemas
  services/        — Business logic layer
  workers/         — Celery background tasks
  core/            — Config, security, exceptions
```

Key endpoints:
- `POST /api/v1/auth/login` — JWT login
- `GET /api/v1/processes` — list processes (tenant-scoped)
- `POST /api/v1/agents/trigger` — start agent run
- `GET /api/v1/agents/runs` — list runs (tenant-scoped)
- `GET /api/v1/system/metrics` — dashboard KPIs

## Frontend Structure

```
frontend/src/
  app/
    (auth)/login/       — Login page
    (dashboard)/        — Protected dashboard layout
      dashboard/        — Main dashboard
      processos/        — Case management
      clientes/         — CRM
      agentes/          — AI agents panel
      financeiro/       — Financial management
      admin/            — Admin-only pages
  components/
    ui/Toast.tsx        — Global toast notifications (useToast hook)
    layout/             — Sidebar, header, breadcrumb, notifications
    agents/             — Agent status cards
  lib/theme.ts          — applyTheme() sets CSS vars from tenant config
  store/index.ts        — Zustand stores (user, theme, notifications)
```

## Design System

AFJ palette (Tailwind):
- `afj-gold`: `#B8954A` — primary brand color
- `afj-navy`: `#1E2229` / `#3D4557` — sidebar, dark backgrounds
- `afj-cream`: `#F4F0EA` — page background
- `afj-black`: `#1A1A1A` — body text

Key CSS classes (globals.css):
- `.afj-stat-card` — KPI card with left gold border
- `.afj-table` — premium table with uppercase headers
- `.afj-section-header` — section title bar with bottom border
- `.afj-page-header` — page title + action button row
- `.afj-card` — standard white card with subtle shadow
- `.btn-afj-primary` — gold filled button
- `.btn-afj-outline` — gold outlined button

## Multi-Tenant

Every model has `tenant_id` (FK to `tenants`). All queries MUST filter by `current_user.tenant_id`. Failing to do so leaks data across clients.

## HITL (Human-in-the-Loop)

AI agents that perform critical actions (file petition, sign contract, send email) create an `Approval` record with `status=PENDENTE`. The action is NOT executed until a human approves it via `/aprovacoes`. This is a security invariant — never bypass it.

## Test Credentials

After running migrations + seed:
- Admin: `admin@afj.com.br` / `Admin@123`
- Advogado: `advogado@afj.com.br` / `Adv@123`

## Deploy

Push to `main` → GitHub Actions runs:
1. TypeScript check + Next.js build
2. Backend ruff lint + pytest
3. Deploy backend to Railway (`RAILWAY_TOKEN` secret)
4. Deploy frontend to Vercel (`VERCEL_TOKEN` secret)

Required GitHub Secrets: `RAILWAY_TOKEN`, `VERCEL_TOKEN`, `SECRET_KEY`, `ENCRYPTION_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`
