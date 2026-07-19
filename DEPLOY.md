# Deploy — AFJ CORE SYSTEM

> **Self-hosted em VPS (HostGator VPS/Cloud etc.)?** Veja o guia dedicado
> [`DEPLOY_VPS.md`](./DEPLOY_VPS.md) — `docker-compose.prod.yml` com
> frontend + backend + Caddy (HTTPS automático) num único servidor.

## Topologia
- **Frontend**: Vercel (auto-deploy no push a `main` que toque `frontend/**`).
- **Backend**: Railway (auto-deploy; build pelo `Dockerfile` da raiz, config em `railway.toml`).
  O `start.sh` sobe **uvicorn + Celery worker + beat no mesmo container** — sem worker,
  agentes de IA, OCR e alertas de prazo ficam enfileirados para sempre.
- **Estado ideal futuro**: serviços dedicados `worker` e `scheduler` no Railway
  (comandos de referência em `infra/railway.toml`), separando web de background.

## Variáveis obrigatórias no Railway (Backend → Variables)

| Variável | Por quê | Sem ela |
|---|---|---|
| `DATABASE_URL` | Postgres (`${{Postgres.DATABASE_URL}}`) | app em modo degradado |
| `REDIS_URL` | fila Celery + cache/blacklist | tarefas rodam in-process (sem beat) |
| `SECRET_KEY` | assinatura JWT — **fixa** (64 chars aleatórios) | **boot falha em produção** |
| `ENCRYPTION_KEY` | cifra as chaves BYOK (32 chars, fixa) | derivada da SECRET_KEY |
| `ANTHROPIC_API_KEY` | agentes de IA (petições, contratos etc.) | IA indisponível (só BYOK) |
| `OPENAI_API_KEY` | embeddings da Pesquisa Jurídica (RAG) | busca semântica retorna 503 |
| `QDRANT_URL` / `QDRANT_API_KEY` | vetor store do RAG | busca/indexação inoperantes |
| `ENVIRONMENT=production` | ativa validações de produção | validações relaxadas |
| `CORS_ORIGINS` | JSON com a URL do frontend | CORS bloqueia o app |
| `SENTRY_DSN` *(opcional)* | monitoramento de erros | sem telemetria de erros |

### Frontend (Vercel → Environment Variables)
| Variável | Por quê |
|---|---|
| `NEXT_PUBLIC_API_URL` | URL pública do backend Railway — usada também pelo WebSocket de notificações (os rewrites do Next não fazem proxy de WS) |

## CI (GitHub Actions — "Validate")
Gates que **quebram** o PR: `tsc --noEmit`, `next build` (com TS estrito) e
`ruff check` do backend (config documentada em `backend/ruff.toml`).
`pytest` ainda é informativo (exige Postgres de serviço — pendência futura).

## Verificação pós-deploy (fumaça)
1. `GET /ping` → `{"ok": true}` e `GET /health` → `status: operational`.
2. Logs do serviço devem mostrar `celery@… ready` além do uvicorn.
3. Disparar um agente (ex.: Documentos → Processar OCR) e ver o run sair de
   `RUNNING` em ~segundos; texto extraído aparece na ficha do documento.
4. `POST /api/v1/rag/search` autenticado → 200 (exige `OPENAI_API_KEY`).
