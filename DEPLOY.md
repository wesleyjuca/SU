# Deploy — AFJ CORE SYSTEM

> **Self-hosted em VPS (HostGator VPS/Cloud etc.)?** Veja o guia dedicado
> [`DEPLOY_VPS.md`](./DEPLOY_VPS.md) — `docker-compose.prod.yml` com
> frontend + backend + Caddy (HTTPS automático) num único servidor.

## Topologia
- **Frontend**: Vercel (auto-deploy no push a `main` que toque `frontend/**`).
- **Backend**: Railway (auto-deploy; build pelo `Dockerfile` da raiz, config em `railway.toml`).
  O `start.sh` sobe **uvicorn + Celery worker + beat no mesmo container** — sem worker,
  agentes de IA, OCR e alertas de prazo ficam enfileirados para sempre.
- **Estado ideal futuro**: serviços dedicados `worker` (`celery -A app.workers.worker worker
  --loglevel=info --concurrency=4 -Q celery,agents`) e `scheduler` (`celery -A app.workers.worker
  beat --loglevel=info --scheduler celery.beat:PersistentScheduler`) no Railway, separando web
  de background.

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
| `API_URL` | URL canônica server-side do backend Railway (`https://su-production-4561.up.railway.app`); usada pelos rewrites HTTP do Next/Vercel para `/api/v1/*` |
| `NEXT_PUBLIC_API_URL` | Mesma URL canônica do backend Railway (`https://su-production-4561.up.railway.app`), exposta ao browser somente para conexões diretas necessárias, como WebSocket (os rewrites do Next não fazem proxy de WS) |

## CI (GitHub Actions — "Validate")
Gates que **quebram** o PR: `tsc --noEmit`, `next build` (com TS estrito) e
`ruff check` do backend (config documentada em `backend/ruff.toml`).
`pytest` ainda é informativo (exige Postgres de serviço — pendência futura).

## Backend canônico

O backend canônico atual é `https://su-production-4561.up.railway.app`. Mantenha `API_URL` (server-side, rewrites HTTP) e `NEXT_PUBLIC_API_URL` (browser, apenas conexões diretas como WebSocket) apontando para esse mesmo host em produção.

## Reduzir custo do Railway (tirar Postgres/Redis de dentro dele)

O Railway cobra por serviço provisionado — hoje Postgres e Redis rodam
como plugins gerenciados *dentro* do próprio projeto Railway, junto com o
container de compute (uvicorn+worker+beat). Isso costuma ser a maior
fatia da fatura num projeto pequeno. Como o app já lê `DATABASE_URL` e
`REDIS_URL` de variável de ambiente (sem nenhuma dependência de código do
Railway em si — `app/config.py` é provider-agnostic), dá pra apontar
essas duas peças para provedores com camada gratuita e manter só o
compute (uvicorn+worker+beat) no Railway. **Isto é infraestrutura, não
código** — os passos abaixo são manuais, feitos fora deste repositório:

1. Checar o tamanho atual do banco no dashboard do Railway (Database →
   Metrics). Se passar de ~500MB, nem Neon nem Supabase cabem no plano
   gratuito — reavalie antes de prosseguir.
2. Criar um projeto gratuito na [Neon](https://neon.tech) (Postgres
   puro, escala a zero quando ocioso — ~1s de latência extra na 1ª query
   após período parado) ou [Supabase](https://supabase.com) (500MB, sem
   cold start de compute, mas traz mais funcionalidades que não são
   usadas aqui). Copiar a connection string fornecida.
3. Fazer backup do banco atual do Railway e restaurar no novo provedor:
   ```bash
   pg_dump "$RAILWAY_DATABASE_URL" > backup.sql
   psql "$NEON_DATABASE_URL" < backup.sql
   ```
4. Ajustar a string para o formato que `app/config.py` espera
   (`postgresql+asyncpg://usuario:senha@host/banco?ssl=require`) e trocar
   `DATABASE_URL` nas variáveis do serviço Railway (Settings →
   Variables). Fazer o deploy e confirmar `GET /ping` funcionando e login
   normal.
5. Criar um banco gratuito na [Upstash](https://upstash.com) (Redis,
   500k comandos/mês, 256MB) e trocar `REDIS_URL`/`CELERY_BROKER_URL`
   (formato `rediss://...`, TLS) da mesma forma.
6. Validar por alguns dias — login, `/ping`, e principalmente o Celery
   Beat rodando (logs devem mostrar as 9 tarefas periódicas disparando
   nos horários certos, ver `backend/app/workers/worker.py`) — antes de
   remover os plugins Postgres/Redis do projeto Railway. É essa remoção
   que efetivamente para de cobrar por eles.
7. Monitorar o teto de comandos/mês da Upstash e o limite de
   armazenamento do Neon/Supabase na primeira semana; se estourar
   rotineiramente, o volume de uso não cabe mais no nível gratuito.

Resultado esperado: a fatura do Railway cai para perto do piso do plano
Hobby (compute apenas), já que os dois itens gerenciados que mais pesam
saem da conta.

## Auditoria de infraestrutura (2026) — dá pra rodar tudo de graça?

Levantamento peça-por-peça de toda a infra (não só Postgres/Redis) contra
o que existe de free tier real em 2026, feito a pedido do usuário. Preços/
limites abaixo foram confirmados por busca, não só memória — esse tipo de
termo muda com frequência.

| Peça | Hoje | Alternativa grátis viável | Risco da opção grátis |
|---|---|---|---|
| Compute backend (uvicorn+Celery) | Railway (pago, sem free tier desde 2023) | Self-host numa VM sempre-ligada | — |
| Frontend Next.js | Vercel | Self-host (mesma VM) | Plano Hobby do Vercel **proíbe uso comercial** — risco de ToS independente de custo, se o projeto atual estiver em Hobby |
| Postgres | Railway plugin (pago) | Self-host (mesma VM) — Neon/Supabase free têm teto pequeno + scale-to-zero/pausa por inatividade | Indisponibilidade num sistema de produção |
| Redis | Railway plugin (pago) | Self-host (mesma VM) — Upstash free (500k comandos/mês) pode não sobrar pro volume real de Beat+WS+rate-limit+cache | Estouro de cota sem alarme prévio |
| Qdrant | Serviço externo pago (não documentado onde) | Self-host (mesma VM) — Qdrant Cloud free suspende após 1 semana sem uso, apaga após 4 | Perda de índice jurídico por inatividade |
| Object storage | Opt-in, hoje provavelmente OFF (cai em base64 no Postgres) | Cloudflare R2 (10GB grátis, egress grátis, já S3-compatível) | Nenhum até passar de 10GB |
| Email/SMTP | Gmail SMTP (já $0) | Manter | — |
| Sentry | Já $0 (plano Developer, opt-in) | Manter | Monitorar se passa de 5k erros/mês |
| CI (GitHub Actions) | Já $0 (sem cron, só push/PR) | Manter | — |

**Recomendação**: consolidar compute+frontend+Postgres+Redis+Qdrant numa
única VM Oracle Cloud "Always Free" via o `docker-compose.prod.yml` já
existente — ver a seção **"Provisionar de graça: Oracle Cloud 'Always
Free'"** em [`DEPLOY_VPS.md`](./DEPLOY_VPS.md#provisionar-de-graça-oracle-cloud-always-free)
pro passo a passo. Evita depender de 3-4 free tiers gerenciados diferentes,
cada um com sua própria forma de "sumir sozinho" por inatividade — um
único ponto de operação, reaproveitando 100% do que já existe no repo.

## Verificação pós-deploy (fumaça)
1. `GET /ping` → `{"ok": true}` e `GET /health` → `status: operational`.
2. Logs do serviço devem mostrar `celery@… ready` além do uvicorn.
3. Disparar um agente (ex.: Documentos → Processar OCR) e ver o run sair de
   `RUNNING` em ~segundos; texto extraído aparece na ficha do documento.
4. `POST /api/v1/rag/search` autenticado → 200 (exige `OPENAI_API_KEY`).
5. Conferir nos painéis da Vercel e Railway que `API_URL` aponta para o backend canônico acima e para o Railway cujo banco contém os usuários reais.
