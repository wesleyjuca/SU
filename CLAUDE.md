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

Push a `main` ou PR → workflow **"✅ CI — Validate"** roda apenas validação (nunca deploy):
1. TypeScript check + Next.js build
2. Backend ruff lint + pytest
3. Scan de vulnerabilidade de dependências (`pip-audit`/`npm audit`, informativo, não bloqueia)

O deploy de produção em si **não** passa pelo GitHub Actions:
- **Backend (Railway)** — integração nativa Railway↔GitHub (git-integration), auto-deploy no push para `main`. Configuração em `railway.toml` (raiz) + `Dockerfile` (raiz) + `start.sh`.
- **Frontend (Vercel)** — workflow separado `deploy-frontend-auto.yml`, dispara no push para `main` que toque `frontend/**`, roda `vercel --prod`.

Secrets do **GitHub Actions** (usados pelos workflows acima): `VERCEL_TOKEN`, `RAILWAY_URL` (não-secreta, só a URL do backend pra build do frontend).

Secrets de **runtime da aplicação** (configurados direto na plataforma — Railway dashboard ou `.env.prod` no self-host, NÃO no GitHub Actions): `SECRET_KEY`, `ENCRYPTION_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DATABASE_URL`, `REDIS_URL`, `QDRANT_URL`/`QDRANT_API_KEY`.

## Teste geral do sistema (metodologia)

Periodicamente (quando uma área grande do sistema muda, ou a pedido do
usuário) rodamos um "teste geral do sistema": simulação real (Postgres +
Redis + Celery + uvicorn + frontend reais, nunca só leitura de código) +
auditoria paralela adversarial (`Workflow`, várias frentes rodando em
paralelo, cada achado cético-verificado antes de entrar no relatório).
Entregável é sempre um relatório de achados — nenhuma correção acontece
na mesma fase; achados viram fases novas só depois que o usuário confirma
quais valem a pena.

**Regra fixa: cada rodada tem que ser mais inteligente que a anterior —
nunca repetir o mesmo teste do zero.** Antes de planejar uma nova rodada:
1. Releia o que a rodada anterior cobriu e, principalmente, o que ela
   **deixou de cobrir** (frentes cortadas por limite de sessão/tempo,
   partes só verificadas por leitura de código em vez de execução real,
   ambientes que nunca chegaram a subir — ex.: a Fase 173 nunca subiu o
   frontend de verdade).
2. Toda rodada nova tem que: (a) reconfirmar de forma independente o que
   a rodada anterior corrigiu (não assumir que o fix "resolvido antes"
   continua resolvido), (b) fechar pelo menos uma lacuna real que ficou
   pra trás, (c) ir mais fundo/mais adversarial em pelo menos uma frente
   do que a rodada anterior foi capaz.
3. Registre abaixo, em 1-2 linhas por rodada, o que foi coberto e o que
   ficou pra trás de propósito — é o que a PRÓXIMA rodada deve ler antes
   de começar.

Histórico:
- **Fase 148-163** (5 meses / 2 escritórios, 6 auditorias) — primeira
  rodada. Todos os achados viraram fases e foram entregues.
- **Fase 173** — simulação real de chains/HITL/plano Máximo (área mais
  nova na época) + 6 frentes paralelas. 3 das 6 frentes (LGPD, perf,
  frontend) tiveram a verificação adversarial cortada por limite de
  sessão; frontend nunca chegou a subir de verdade (só leitura estática).
  9 achados confirmados → viraram Fase 174.
- **Fase 174** — implementação dos 9 achados da Fase 173, cada um
  reverificado empiricamente no momento da própria correção.
- **Fase 175** — reconfirmação independente dos 9 fixes da Fase 174 (não
  só a verificação feita durante a implementação), caça a regressão na
  interação entre eles, e fechamento das 3 lacunas deixadas pela Fase 173
  (LGPD aprofundado, perf/`time_limit`, e — pela primeira vez — o
  frontend real subido e navegado via Playwright). Achado imediato só de
  subir o frontend de verdade: `frontend/next.config.js` tem um fallback
  de API local morto, fazendo `npm run dev` sem a env var `API_URL` (não
  `NEXT_PUBLIC_API_URL`) conversar com o backend de PRODUÇÃO em vez do
  local. A 2ª rodada de auditoria paralela (mesma técnica da 173, desta
  vez citando explicitamente o diff da 174 pro achado não virar
  auto-referência) achou que o próprio fix da 174.6 (retomada após
  retry) só cobre o caso `último passo = SUCCESS` — o caso mais comum de
  uma chain HITL pausar (`AWAITING_APPROVAL`) cai no branch antigo e
  reexecuta a chain inteira do zero; também achou uma regressão de
  contagem de custo introduzida pelo próprio fix (`tokens_used`/
  `cost_usd` sobrescritos em vez de somados no caminho de retomada), um
  gap real de LGPD (`erase_client_data` não alcança `ClientInteraction`/
  `ClientContact`, que continuam exportáveis com PII depois do
  "esquecimento"), uma race real em `cancel_run` (só checa `CANCELADO`
  1x no início de `resume_chain_after_approval`, não dentro do loop), e
  um banner do frontend que nunca atualiza pra disparo direto (não-chain)
  de agente. 6 achados confirmados → candidatos a virar Fase 176.
- **Fase 176** — implementação dos 6 achados da Fase 175, cada um
  reproduzido e reverificado empiricamente no momento da própria correção
  (Postgres/Redis reais para 176.1-176.3/176.5, incluindo 2 sessões
  concorrentes para reproduzir a race de 176.5; `npm run dev` real +
  Playwright/curl para 176.4/176.6). Não repetiu uma rodada de teste geral
  nova — próxima rodada deve reconfirmar estes 6 fixes de forma
  independente (mesmo padrão da transição 174→175) antes de ir atrás de
  achados novos, e considerar aprofundar uma frente que ainda não teve
  simulação de volume/concorrência real: múltiplos runs concorrentes
  disputando o mesmo `TaskLock` de retomada sob carga (só testado de forma
  sintética/isolada até aqui, nunca com volume).
- **Fase 177** — evolução de Integrações a pedido do usuário (não uma
  rodada de teste geral): login OAuth2/Keycloak (`grant_type=password`) do
  PDPJ reaproveitando o mecanismo de renovação automática já usado por
  Google/Mercado Pago, e aviso a ADMIN/SOCIO/SUPERADMIN na transição de
  qualquer credencial pra `ERRO` (antes só um badge vermelho passivo).
  Verificado com HTTP simulado + Postgres real no momento da implementação.
- **Fase 178** — reconfirmação independente dos 8 fixes das Fases 176+177,
  e fechamento da lacuna de volume/concorrência no `TaskLock` deixada pela
  Fase 176 (20 chamadas concorrentes reais contra Redis real → 1 executa,
  19 corretamente bloqueadas, sem duplicar `AgentStep` nem custo). Achado
  operacional importante desta rodada: o `Workflow` usado nas Fases
  173/175 para a auditoria paralela **não funcionou** desta vez — todos os
  ~19 subagentes lançados receberam um lembrete de "plan mode ativo"
  injetado no próprio contexto deles (mesmo a sessão principal não estando
  de fato restrita — commits/pushes/edições diretas continuaram
  funcionando o tempo todo) e corretamente se recusaram a escrever no
  Postgres/Redis real, devolvendo só leitura estática de código. A
  reconfirmação dos 8 fixes e o teste de volume do `TaskLock` tiveram que
  ser refeitos manualmente pela sessão principal (não delegados) depois
  desse achado. Isso também pegou um falso-positivo real no meio do
  caminho: a 1ª tentativa do teste de volume do `TaskLock` "achou" que 20
  chamadas concorrentes conseguiam `resumed=True` ao mesmo tempo — na
  verdade era o próprio script de teste esquecendo de exportar `REDIS_URL`
  no processo, fazendo o lock cair no fail-open por design (sem Redis
  configurado); corrigido e re-executado antes de virar achado. Por causa
  do bloqueio de subagentes, a auditoria de achados novos desta rodada foi
  mais estreita que o normal (3 checagens pontuais feitas manualmente:
  isolamento cross-tenant da notificação de erro de integração, vazamento
  de PII/credencial em audit_logs/logs estruturados, e regressão visual em
  `/integracoes` — todas limpas, nenhum achado novo) em vez do leque de 4
  frentes paralelas com verificação adversarial das rodadas anteriores.
  **Próxima rodada deve**: (a) verificar se o bloqueio de plan mode em
  subagentes ainda ocorre antes de tentar `Workflow` de novo (pode ser
  transitório desta sessão) — se persistir, é um problema de harness a
  reportar, não algo pra contornar silenciosamente toda vez; (b) cobrir as
  frentes que ficaram de fora aqui por causa do bloqueio: casos de borda
  de múltiplos gates HITL em sequência (3+), resolve_approval concorrente
  na MESMA Approval (distinto do TaskLock de retomada, nunca testado), e
  rejeição no meio de uma chain com retry parcial já aplicado.
- **Fase 183** — reconfirmação independente das Fases 179-182 (todas OK,
  sem regressão de interação entre elas) e fechamento das 3 frentes que a
  Fase 178 deixou pra trás — desta vez com `Agent` (não `Workflow`) rodando
  em paralelo sem o bloqueio de plan mode da rodada anterior (achado (a) da
  178 confirmado como transitório daquela sessão, não recorrente). 2 das 3
  frentes viraram **achados reais confirmados empiricamente contra Postgres
  real** (não hipótese de leitura de código):
  - **3+ gates HITL em sequência QUEBRA** — `execute_approved_action`
    (`app/services/approval.py`) só dá `db.flush()` nos branches
    PETITION_REVIEW/PETITION_FILING/CONTRACT_REVIEW/CONTRACT_SIGN; como
    `AsyncSessionLocal` roda com `autoflush=False` (`app/db/base.py`), pra
    qualquer outro tipo de Approval (ou seja, qualquer 2º/3º gate HITL de
    uma chain multi-agente cujo passo não é petição/contrato — ex.:
    `new_process_intake`) a mudança de status pra APROVADO nunca é
    flushada antes de `resume_chain_after_approval` → `create_approval_
    from_state` reler a Approval — a checagem de idempotência (Fase 132/
    171, `app/services/approval.py`) vê a linha ainda como PENDENTE,
    conclui "já existe aprovação pra esse run" e **não cria a Approval do
    próximo gate**. A chain fica travada em AWAITING_APPROVAL pra sempre,
    zero Approval pendente pra resolver — precisa de intervenção manual no
    banco. Reproduzido de ponta a ponta com uma chain real de 4 passos
    contra Postgres real.
  - **`AgentRun` não tem lock de linha (só a `Approval` tem, Fase 132)** —
    confirmado que um retry do Celery em voo (`app/workers/tasks/
    agent_tasks.py`, linhas 174-211: `refresh` → mutação de status/
    tokens_used/cost_usd → `commit`, sem `FOR UPDATE`) pode commitar POR
    CIMA de uma rejeição humana que já tinha sido commitada segundos
    antes na mesma `AgentRun` — a `Approval` fica corretamente REJEITADO,
    mas o `AgentRun.status` acaba refletindo o que o retry calculou (ex.:
    SUCCESS) em vez de FAILED, e `requires_approval` volta a `False`
    incorretamente. Estado final inconsistente: auditoria diz rejeitado,
    o run diz sucesso.
  - `resolve_approval` concorrente na MESMA Approval (cenário (b)) segue
    protegido pelo lock da Fase 132 — confirmado, sem achado novo aqui.
  Auditoria paralela adicional (isolamento cross-tenant das 4 features
  novas, LGPD/PII no export do Google, frontend real via Playwright): tudo
  limpo, nenhum achado novo — só uma observação de design (não bug): o
  rastro de auditoria dos 2 endpoints novos do Google (Fase 182) é
  genérico (`AuditMiddleware`, sabe quem/quando mas não quais registros
  saíram) em vez de granular como o padrão manual já usado em HITL, e
  `FinancialEntry.descricao` é campo livre que pode conter PII e passa a
  sair do perímetro de criptografia do sistema ao virar Google Sheets.
  6 achados no total (2 confirmados por reprodução empírica real — os
  mais graves desta rodada — + 2 de auditoria adicional, mais leves).
  Nenhuma correção feita nesta fase — decisão do usuário sobre quais viram
  fase nova. **Próxima rodada deve**: se os fixes dos 2 achados HITL forem
  implementados, reconfirmar especificamente (a) que um gate genérico
  (não-petição/contrato) numa chain de 3+ passos completa corretamente
  até SUCCESS, e (b) que uma rejeição sobrevive a um retry concorrente do
  Celery mesmo quando o retry calcula um status terminal diferente.
- **Fase 186** — reconfirmação independente dos fixes das Fases 184
  (flush + lock HITL, audit trail Google, aviso de PII) e 185 (doutrina
  Google Drive), desta vez indo mais fundo que a rodada anterior: os 2
  cenários HITL foram reproduzidos batendo em endpoints HTTP reais
  (`uvicorn` numa 2ª porta com só `resolve_agent_class` monkeypatched,
  requisições concorrentes via `httpx.AsyncClient` de verdade) em vez de
  chamar as funções de serviço direto em processo como a Fase 184 fez —
  e a lacuna de cobertura que isso expôs (nenhum teste commitado batia
  Postgres real pra esses 2 bugs, só um script de scratchpad) foi
  fechada com `tests/test_api/test_hitl_flush_and_lock.py`. Fases
  179-182 reconfirmadas por um agente dedicado — tudo OK, sem regressão
  de interação com 184/185. Frontend real via Playwright confirmou ao
  vivo (não só leitura de código) que a tela de Integrações não mostra
  nenhum resultado de sincronização da doutrina (processados/pulados/
  falhas/erro) e que o modal de Aprovações exige justificativa pra
  rejeitar, como esperado. 2 achados novos, ambos confirmados
  empiricamente (não hipótese de leitura de código):
  - **CRÍTICO — busca RAG inteira quebrada silenciosamente**: a versão
    exata de `qdrant-client` pinada em `requirements.txt` (`1.18.0`,
    confirmada instalada) **não tem mais o método `.search()`** em
    `AsyncQdrantClient`/`QdrantClient` (renomeado pra `.query_points()`
    numa versão anterior da lib) — confirmado por inspeção direta da
    classe instalada (`'search' not in dir(AsyncQdrantClient)`) e
    reprodução real com Qdrant em memória (motor de verdade, não mock).
    `app/rag/retrieval.py:82` (usado por **todo** agente via
    `BaseAgent.recall()`, pelo assistente do Cérebro em
    `brain_assistant.py`, e pelo endpoint `/rag/...` da tela de busca
    jurídica) chama `qdrant_client.search(...)`, que sempre lança
    `AttributeError` — engolido silenciosamente por um `except
    Exception: log.warning(...)` **por coleção**, então a busca RAG
    devolve `200 OK` com resultado sempre vazio, pra todo tenant, em
    toda coleção, sem nenhum erro visível. `app/services/
    embeddings_compare.py` (ferramenta SUPERADMIN, Fase 4.2) tem os
    mesmos 2 call sites sem esse try/except — quebra com 500 direto.
    Nenhum teste commitado pegou isso porque todos usam um Fake client
    próprio com um método `search()` definido à mão (nunca validou
    contra a API real da lib instalada) — o mesmo padrão de risco
    (mock diverge da API real de uma lib externa) vale a pena vasculhar
    mais amplo numa rodada futura.
  - **ALTO — achado introduzido pelo próprio fix da Fase 185**:
    `google_drive_sync.py` agora reprocessa arquivos `FALHOU`
    corretamente (Fase 185), mas nunca chama `delete_document_chunks()`
    antes de re-ingerir, e `ingest_document()` usa `uuid4()` (não
    determinístico) como point ID — confirmado empiricamente (Qdrant em
    memória real): reingerir o mesmo `document_id` duplica os chunks
    (2 pontos órfãos pro mesmo arquivo, 0 IDs em comum entre as 2
    tentativas). `delete_document_chunks()` já existe e funciona
    (testado no mesmo script), só nunca é chamado nesse caminho.
  Nenhuma correção feita nesta fase — decisão do usuário sobre quais
  viram fase nova. **Próxima rodada deve**: se o fix do `.search()`
  for implementado, reconfirmar que a busca RAG volta resultados de
  verdade (não só 200 vazio) em pelo menos 1 collection privada e 1
  pública, e considerar auditar outros pontos onde um Fake de teste
  pode ter divergido silenciosamente da API real de uma lib externa
  pinada. Também ficou pra trás: 3 linhas de teste órfãs na tabela
  `approvals` (tipo `GATE1`/`CONTRACT_REVIEW` — resíduo de sessões
  anteriores, não são dados reais, mas nunca foram limpas) e a decisão
  jurídica pendente sobre retenção de `audit_logs` (sem mudança desde a
  Fase 148).

## Riscos conhecidos / débito técnico

Achados de uma simulação de volume (2 escritórios, ~10 processos/dia, 1 ano —
Fase 116) que exigem decisão de produto/jurídica antes de qualquer mudança
de código, por isso ficam só documentados aqui, não implementados:

- ~~**Storage de documentos**~~ — **resolvido (Fase 141)**. `Document`
  ganhou `arquivo_storage_key`/`arquivo_mimetype`/`arquivo_size_bytes`;
  uploads novos vão pra object storage S3-compatível (AWS S3, Cloudflare
  R2, MinIO, Railway Object Storage — configurável via `S3_*` em
  `app/config.py`) quando configurado, com fallback automático pro caminho
  legado (base64 inline) sem credenciais. Sem backfill das linhas antigas
  — ficam no caminho legado indefinidamente, não é bug.
- **Retenção de auditoria (LGPD)** — `audit_logs` é imutável por trigger de
  banco (`trg_audit_logs_immutable`) e cresce indefinidamente (1 linha por
  request de escrita, não só por evento de negócio) — sem qualquer rotina de
  expurgo/arquivamento. A LGPD pede retenção limitada de dados pessoais (o
  payload pode conter IP, user_agent, `old_value`/`new_value` em JSONB), o
  que tensiona com esse design. Definir um prazo de retenção e um mecanismo
  de arquivamento (a tabela não aceita `DELETE` direto por causa do trigger)
  é uma decisão que precisa de orientação jurídica do escritório antes de
  qualquer implementação — não decidir um prazo arbitrário sem essa validação.
