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
  - **Fase 187** (implementação do achado CRÍTICO acima, usuário optou
    por não corrigir o achado ALTO da duplicação no Qdrant nem a
    observabilidade de sincronização nesta rodada): `retrieval.py` e
    `embeddings_compare.py` trocam `.search()` por `.query_points()` (a
    Query API real do qdrant-client 1.18.0) nos 3 call sites. Novo teste
    `test_rag_retrieval_real_qdrant.py` usa Qdrant real em memória
    (`location=":memory:"`, não um Fake escrito à mão) — confirmado que
    ele falha contra o código antigo (`AttributeError` capturado) e
    passa com o fix, fechando exatamente a lacuna que permitiu o bug
    passar despercebido. Os 2 Fakes existentes que tinham `search()`
    manual (`test_rag_cache.py`, `test_reindex_test_collection.py`)
    também foram corrigidos pra `query_points()`. Reconfirmação da busca
    RAG de verdade (não só 200 vazio) com Qdrant real fica pra próxima
    rodada de teste geral, conforme a guidance acima.
  - **Fases 188-196** — sequência contínua a pedido do usuário (não uma
    rodada de teste geral): fecha os 2 achados da Fase 186 que ficaram
    sem fase, implementa os "próximos passos do programa" de Ética e
    Integridade, e trabalha a lista `PENDENCIAS` de `/sobre` inteira
    (exceto retenção de auditoria LGPD, mantida travada — mesma decisão
    do CLAUDE.md, não reaberta sob nenhuma leitura de "débito técnico").
    Cada fase foi testada (unitário + verificação empírica contra
    Postgres/Redis reais) e verificada (ruff/py_compile/pytest/tsc/eslint)
    antes do commit, sem parar pra confirmar entre fases.
    - **Fase 188** — fecha os 2 achados pendentes da Fase 186:
      `google_drive_sync.py` chama `delete_document_chunks()` antes de
      reingerir um arquivo `FALHOU` (fix da duplicação de chunks no
      Qdrant, confirmado com Qdrant real em memória); novo endpoint
      `GET .../google_drive_doutrina/last-sync` + card na tela de
      Integrações mostrando o resultado da última sincronização de
      doutrina (processados/pulados/falhas), fechando o gap de
      observabilidade visto ao vivo via Playwright na Fase 186.
    - **Fase 189** — próximos passos do programa de Ética e Integridade
      (antes só cards estáticos em `PROGRAMA_PLANEJADO`): 3 modelos novos
      (`IntegrityRisk`, `IntegrityTraining`+`IntegrityTrainingCompletion`,
      `IntegrityCommitteeCase`) com CRUD completo e frontend real — Matriz
      de Riscos de Integridade, Treinamentos Obrigatórios (com % de
      conclusão da equipe) e Comitê de Integridade (casos ligados a
      `IntegrityReport`, quando houver).
    - **Fase 190** (débito A) — `AgentAttachment` ganha `storage_key`,
      reaproveitando `object_storage.py` (padrão da Fase 141) com
      fallback automático pro base64 legado quando S3 não está
      configurado.
    - **Fase 191** (débito B) — `Approval.expires_at` (existia, nunca era
      lido) passa a ser setado em `create_approval_from_state`; novo
      reaper periódico (`escalar_aprovacoes_vencidas`, Celery Beat)
      **só escala/notifica** gestores do tenant quando uma aprovação
      pendente vence — nunca auto-aprova/auto-rejeita, invariante HITL
      do CLAUDE.md respeitado.
    - **Fase 192** (débito C) — `execute_approved_action` no branch de
      contrato dispara `enviar_para_assinatura` (Clicksign) automaticamente
      após a aprovação humana, fail-soft (falha no envio nunca desfaz a
      aprovação, só deixa "aprovado, aguardando envio manual").
      Deliberadamente fora de escopo: protocolo automático em tribunal
      (`PETITION_FILING`) — o próprio cliente PJe documenta isso como um
      "NEVER" da integração; petição aprovada continua exigindo protocolo
      manual, como antes.
    - **Fase 193** (débito D) — novo modelo `CustomAgentVersion` (mesmo
      padrão de snapshot de `AgentPromptVersion`) + `PATCH
      /custom-agents/{id}` (SUPERADMIN-only) pra editar um agente de IA
      customizado já `APROVADO` sem reabrir fluxo de aprovação.
    - **Fase 194** (débito E) — `capturar_por_oab()` (já existia, só
      disparava manual ou sob demanda) ganha uma task Celery Beat diária,
      fail-soft por tenant.
    - **Fase 195** (débito F) — Google Vertex AI como provedor BYOK em
      `AI_PROVIDERS`, com branch dedicado em `llm_client.py`
      (`_call_vertex_ai` — fluxo OAuth2 JWT Bearer + REST puro via httpx,
      sem SDK novo, mesmo padrão das demais integrações Google do
      projeto). Corrigiu de quebra um bug real exposto pelo novo
      provedor: `minha-ia/page.tsx` decidia "precisa URL própria"
      checando só `!base_url` (pensado só pro Ollama) — como Vertex
      também tem `base_url` nulo (reaproveitado como região do GCP), o
      formulário teria escondido o campo de credencial e mostrado em vez
      disso o campo de URL de servidor do Ollama, tornando impossível
      configurar Vertex pela UI.
    - **Fase 196** (débito G) — resposta de IA em streaming nos agentes:
      `BaseAgent.ask_llm()` usa `call_llm_stream` (WebSocket, evento
      `AGENT_RUN_DELTA`) em vez de `call_claude` quando
      `ctx.stream_enabled` — setado por `execute_chain_step` só pra
      disparo direto (chain de 1 passo); chains multi-agente nunca
      streamam (uma chain já usa a saída de um passo como entrada do
      próximo antes do usuário ver qualquer coisa). Verificado com Redis
      real (pub/sub de verdade, não mockado) confirmando os deltas
      publicados/recebidos na ordem certa.
    - Não repetiu nem tentou reconfirmar achados de rodadas de teste geral
      anteriores (não era esse o objetivo desta sequência) — a próxima
      rodada de teste geral deve reconfirmar os 9 itens acima de forma
      independente antes de ir atrás de achados novos, no mesmo padrão
      já estabelecido (174→175, 176→178, etc.).
- **Fase 197** — rodada de teste geral (ambiente real: Postgres+Redis+Celery
  worker+uvicorn+frontend subidos de verdade). Reconfirmou de forma
  independente, via HTTP real contra o backend rodando (não chamando
  serviço em processo), os 9 itens das Fases 188-196: 188.2 (endpoint
  last-sync), 189 (CRUD completo de risco/treinamento/comitê + isolamento
  cross-tenant testado explicitamente), 190 (upload de anexo confirma
  fallback base64 com S3 não configurado — `storage_key` NULL,
  `data_url` populado), 191 (Approval vencida escala via Celery real,
  nunca resolve sozinha, idempotente numa 2ª rodada do reaper), 192
  (aprovação de contrato dispara tentativa de Clicksign, fail-soft
  correto sem credencial configurada), 193 (propor→aprovar→PATCH→
  snapshot de versão com o prompt ANTIGO, 403 pra não-SUPERADMIN), 194
  (task Celery roda limpo contra 2 tenants reais, 0 OABs configuradas).
  Também reconfirmou a Fase 187 (RAG real com Qdrant em memória, 1
  collection pública + 1 privada, isolamento cross-tenant) e a Fase
  188.1 (reingest não duplica chunks). Limpou os itens de "próxima
  rodada" documentados pela Fase 186: as 3 linhas órfãs viraram 28 (residual
  acumulado de várias rodadas anteriores, nunca limpo) — apagadas da
  tabela `approvals`.
  **2 achados novos, ambos CRÍTICOS e confirmados empiricamente:**
  - **Fase 196 nunca ativa em nenhum agente real.** Streaming foi
    implementado inteiramente dentro de `BaseAgent.ask_llm()`, mas
    `grep -rn "\.ask_llm("` no código de produção mostra zero call
    sites — todos os 19 agentes chamam `call_claude`/`call_llm`
    diretamente e replicam manualmente o bookkeeping de tokens/auditoria
    que `ask_llm()` faria (padrão estabelecido desde a Fase 125).
    Confirmado ao vivo: disparo real de `generate_strategy` via HTTP
    contra Celery real (com `call_llm_stream`/`call_llm` monkeypatchados
    pra reconhecer qual caminho rodou) — zero eventos `AGENT_RUN_DELTA`
    publicados; o agente usou o `call_llm` de fallback, não o stream.
    A Fase 196 só "funcionava" no `_StubAgent` sintético dos próprios
    testes, que é o único código de produção ou teste que chama
    `self.ask_llm()` de verdade.
  - **`ensure_collections()` (`app/rag/collections.py:105`) quebra
    contra o qdrant-client 1.18.0 real.** `{c.name for c in await
    qdrant_client.get_collections()}` itera o objeto pydantic
    `CollectionsResponse` diretamente — isso não devolve a lista de
    collections, devolve `[("collections", [...])]` (iteração padrão de
    BaseModel), e `c.name` explode com `AttributeError: 'tuple' object
    has no attribute 'name'`. Confirmado com Qdrant real em memória.
    Só não derruba o boot porque `_background_warmup()`
    (`app/core/events.py:154-162`) engole a exceção num
    `except Exception: log.warning(...)` — mas isso significa que em
    QUALQUER ambiente com `QDRANT_URL` real configurado (nunca foi o
    caso deste sandbox nem, aparentemente, de nenhuma rodada anterior),
    as collections nunca são criadas automaticamente no primeiro boot, e
    toda ingestão/busca RAG subsequente falharia silenciosamente com
    "collection not found" — engolido de novo pelos `except Exception`
    já documentados em `retrieval.py` (Fase 186). É a mesma classe de
    risco já achada na Fase 186 (Fake de teste divergindo da API real de
    lib externa pinada): o teste da própria Fase 187
    (`test_rag_retrieval_real_qdrant.py`) cria as collections
    manualmente com `client.create_collection(...)`, nunca passando por
    `ensure_collections()` — por isso esse bug sobreviveu mesmo num
    teste que já usa Qdrant real.
  Escopo cortado desta rodada por decisão de tempo: não rodou uma
  auditoria paralela formal via `Workflow`/vários `Agent`s — os 2
  achados foram todos encontrados por teste direto e leitura de código
  guiada pelos resultados, mais rápido que armar um fan-out pra esta
  rodada específica. Cross-tenant nos 3 modelos novos de Ética (Fase
  189) foi testado manualmente (limpo, sem achado). Nenhuma correção
  feita nesta fase — decisão do usuário sobre quais achados viram fase
  nova. **Próxima rodada deve**: se o fix de `ensure_collections()` for
  implementado, reconfirmar com Qdrant real que collections novas são
  criadas no boot; se o fix da Fase 196 for implementado, decidir (e
  documentar a decisão) se streaming passa a rodar por trás de
  `call_claude`/`call_llm` diretamente (tocando todos os 19 agentes) ou
  se os agentes passam a ser migrados pra usar `ask_llm()` de fato —
  qualquer uma das duas é uma mudança bem maior que a Fase 196 original
  presumiu. Considerar também levantar se algum dos outros itens
  "reconfirmados" desta rodada (188.2, 189, 190, 191, 192, 193, 194)
  tem o mesmo tipo de gap estrutural do 196 (feature implementada mas
  nunca alcançada pelo fluxo real) — não foi verificado de propósito
  além do próprio smoke test de cada um.
- **Fase 198** — fecha os 2 achados críticos da Fase 197.
  - **198.A** — `app/rag/collections.py::ensure_collections()` trocou
    `{c.name for c in await qdrant_client.get_collections()}` por
    `{c.name for c in (await qdrant_client.get_collections()).collections}`
    (o retorno é um `CollectionsResponse` pydantic, não uma lista).
    Novo teste `test_rag_ensure_collections_real_qdrant.py` com Qdrant
    real em memória (não um Fake) confirma que falha contra o código
    antigo e passa com o fix.
  - **198.B** — por escolha do usuário ("Mover streaming pro
    call_claude direto"), o streaming da Fase 196 deixou de depender de
    `BaseAgent.ask_llm()` (que nenhum dos 19 agentes chama) e passou a
    rodar por trás de `call_llm()` (`app/integrations/llm_client.py`) —
    o único ponto que todo agente já atravessa, direto ou via
    `ask_llm()`. Novo contextvar `agent_stream_ctx`, setado só pra
    disparo direto (chain de 1 passo) em `execute_chain_step()`
    (orchestrator.py). Verificado com um agente real no padrão de
    produção (`call_claude` direto, `strategy_agent`) disparado via
    HTTP+Celery real, confirmando `AGENT_RUN_DELTA` publicado via Redis
    pub/sub — não só teste unitário.
- **Fase 199** — dois pedidos do usuário, sem relação com o ciclo de
  "teste geral": (1) reduzir o custo do Railway (hoje hospeda
  Postgres+Redis+compute juntos no mesmo projeto) e (2) um tenant
  público de demonstração, todas as funcionalidades liberadas mas sem
  nenhum efeito externo real, resetável a qualquer momento.
  - **Custo Railway**: runbook novo em `DEPLOY.md` (migrar Postgres pra
    Neon/Supabase free e Redis pra Upstash free, mantendo só o compute
    no Railway) — infraestrutura pura, sem mudança de código
    necessária (`DATABASE_URL`/`REDIS_URL` já são genéricas). Não
    executado nesta sessão — exige conta em provedor externo e acesso
    ao dashboard do Railway, fora do alcance desta sessão.
  - **Tenant demo**: `Tenant.is_demo` (mesmo padrão idempotente do
    `isento` da Fase 170, `core/events.py`). **Achado de segurança do
    Plan agent, confirmado em código**: `role == "SUPERADMIN"` neste
    sistema é o dono da plataforma inteira (`DELETE /processes/{id}
    /permanente` e o de usuário não filtram por tenant, só por
    `em_producao`) — por isso o usuário demo é `role=ADMIN`, nunca
    SUPERADMIN, confirmado explicitamente com o usuário. Novo
    `app/services/demo_guard.py` (`tenant_is_demo`) bloqueia, sem
    tocar nos call sites, os 4 pontos de efeito externo real:
    `esign.py::enviar_para_assinatura`, `email.py::send_email`,
    `payment_gateway.py::criar_link_pagamento`, e (achado extra do Plan
    agent) `PUT /system/ai-budgets` — sem esse último, o próprio ADMIN
    demo poderia remover o teto de IA da própria conta. Seed/reset
    fatorados em `app/services/demo_fixtures.py`
    (`criar_elenco_demo`/`gerar_dados_ficticios`, reaproveitados por
    `scripts/seed_db.py`, agora idempotente) e
    `app/services/demo_reset.py` (`resetar_tenant_demo` — não recebe
    `tenant_id` como parâmetro, resolve o alvo internamente e aborta se
    não for exatamente o tenant `demo`, eliminando por construção
    qualquer risco de vazar pro tenant `afj`). Reset diário via Celery
    Beat (`app/workers/tasks/demo_reset.py`, `crontab(hour=4,
    minute=45)`) + endpoint manual `POST /tenants/demo/reset`
    (`SUPERADMIN` real, nunca o ADMIN do próprio tenant demo). Frontend:
    banner "modo demonstração" (`AlertBanner` variant `info` novo) e
    botão "Entrar como visitante" na tela de login com a credencial
    pública (`demo@afjdemo.com.br` / `Demo@2026`, documentada e
    resetada periodicamente, não é secreta).
  - **Achado real desta fase** (fora do escopo original, pego pelos
    testes): `GET /tenant/theme`/`PUT /tenant/branding` quebravam com
    `ValidationError` quando o objeto `Tenant` em memória não tinha
    `is_demo` carregado do banco (`None` em vez de `bool`) — corrigido
    com `bool(tenant.is_demo)`; pego por um teste pré-existente
    (`test_tenant_logo_fase143.py`) que constrói um `Tenant()` sem
    passar por sessão.
  - Verificado com Postgres+Redis reais: seed idempotente (rodar 2x não
    duplica), login público funcional, os 3 guards de I/O bloqueando
    via HTTP real (fatura de teste emitida → `POST .../payment-link`
    devolve 422 sem tentar Mercado Pago/Stripe; `PUT /system/ai-budgets`
    devolve 403 pro próprio ADMIN demo), reset manual via SUPERADMIN
    real confirmando que a contagem de linhas do tenant `afj` não muda
    nem uma unidade antes/depois, e que o login público continua
    funcionando imediatamente após o reset (usuários recriados com IDs
    novos). Suíte completa: 809 passed — a flutuação de ~35-40
    ERROR/FAILED entre rodadas é um artefato de infraestrutura
    pré-existente e não relacionado (pool de conexão asyncpg reutilizado
    entre event loops por-teste do pytest-asyncio), reproduzido de forma
    idêntica isolando um teste já existente e não tocado nesta fase
    (`test_hitl_flush_and_lock.py`) — todo teste novo desta fase passa
    limpo quando rodado isolado.
- **Fase 200** — pedido do usuário: a entrada de visitante na tela de
  login não devia mais exigir senha, já que os dados do tenant demo são
  sempre temporários (resetados periodicamente) e não afetam usuários
  reais. Novo endpoint `POST /auth/demo-login` (`app/api/v1/auth.py`),
  sem nenhum parâmetro de entrada — resolve o único destino possível
  (ADMIN do tenant `slug=="demo" AND is_demo=True`) internamente, mesmo
  padrão de segurança do `resetar_tenant_demo` (Fase 199), tornando
  estruturalmente impossível usar essa rota pra entrar em qualquer outro
  tenant. Não participa do rate-limiter de senha errada (não há senha a
  errar); ganhou teto próprio, só anti-abuso (20 requisições/5min por
  IP), pra não virar gerador infinito de `Session` rows. O botão "Entrar
  como visitante" do frontend (`login/page.tsx`) passou a chamar essa
  rota em vez do `/auth/login` com a credencial fixa embutida no bundle
  — a senha `Demo@2026` continua válida pra quem quiser logar manualmente
  (documentada, não é secreta), só deixou de ser necessária pro clique
  único. Verificado via HTTP real contra o backend local (Postgres+Redis
  reais): token emitido sem corpo nenhum na requisição funciona num
  endpoint autenticado de verdade, login por senha antigo continua
  funcionando em paralelo, e o rate-limit de anti-abuso dispara
  corretamente na 21ª chamada consecutiva.
- **Fase 201** — rodada de teste geral (ambiente real: Postgres+Redis+
  Celery worker+uvicorn+frontend subidos de verdade). Cobriu, nesta
  ordem: (a) reconfirmação independente dos 2 achados críticos da Fase
  197/198 — desta vez indo mais fundo que a própria Fase 198; (b) a
  lacuna que a Fase 197 deixou documentada ("será que 188.2/190-194 têm
  o mesmo gap estrutural do 196?"); (c) primeira rodada de teste geral
  sobre as Fases 199-200 (nunca tinham passado por uma, só pelo teste do
  próprio build); (d) auditoria paralela adversarial (`Agent`, não
  `Workflow`) — a frente que a Fase 197 cortou por tempo.
  - **198.A reconfirmado, mais fundo**: em vez de só chamar
    `ensure_collections()` isolado (como o teste da 198 fez), este round
    exercitou o **caminho de boot real** (`_background_warmup()`,
    `app/core/events.py`) com `get_qdrant()` monkeypatchado pra um Qdrant
    real em memória — confirma que a integração completa (checagem de
    `QDRANT_URL` configurada → `get_qdrant()` → `ensure_collections()`)
    funciona de ponta a ponta, não só a função isolada.
  - **198.B reconfirmado com um agente diferente do testado na própria
    Fase 198** (`compliance_agent` em vez de `strategy_agent`, disparado
    via HTTP+Celery+Redis reais, `call_llm_stream` monkeypatchado pra não
    depender de credencial Anthropic real): 3 eventos `AGENT_RUN_DELTA`
    publicados na ordem certa + `AGENT_RUN_COMPLETED`, confirmando que a
    decisão de mover streaming pro nível de `call_llm()` (não
    `ask_llm()`) realmente generaliza pra qualquer agente que passe por
    `call_claude`/`call_llm`, não só o testado originalmente. Também
    testado o caso negativo pela primeira vez: uma chain de 2 passos
    (`full_contract_flow`) real, via HTTP+Celery, confirmando **zero**
    eventos `AGENT_RUN_DELTA` publicados (`ctx.stream_enabled = len(chain)
    == 1`, `app/agents/brain/orchestrator.py:103`, se comporta como
    documentado).
  - **Lacuna da Fase 197 fechada — todos os 6 itens auditados vieram
    limpos**: 188.2 (observabilidade de sync), 190 (S3 dos anexos), 191
    (expiração/escalonamento de aprovação), 192 (Clicksign automático),
    193 (snapshot de versão de agente customizado) e 194 (descoberta por
    OAB) foram todos rastreados ponta a ponta (writer↔reader, chamador
    real↔`beat_schedule`) e nenhum reproduz o padrão da Fase 196 (feature
    implementada mas nunca alcançada pelo fluxo real). Fechado — não
    precisa reabrir numa rodada futura a menos que algum desses itens
    mude.
  - **Primeira auditoria de teste geral sobre as Fases 199-200**:
    reconfirmado de forma independente (não reaproveitando os testes do
    próprio build) — login sem senha funcional via HTTP real e via
    Next.js dev real (proxy batendo no backend local, não produção,
    fechando a mesma classe de risco da 176.6), tentativa de bypass via
    parâmetros extra no corpo da requisição corretamente ignorada, os 3
    guards de I/O (e-mail/assinatura/pagamento) e o guard de teto de IA
    todos reconfirmados via HTTP real contra o próprio ADMIN demo, teto
    de `max_users=4` bloqueando um 5º convite (fecha a brecha de escapar
    do teto de IA por convite), e o reset do tenant demo reconfirmado
    **não tocando uma linha do tenant `afj`** rodando a função de serviço
    direto contra Postgres real (não só via teste automatizado
    pré-existente).
  - **2 achados novos, ambos confirmados empiricamente/pela inspeção
    direta do banco (não hipótese de leitura de código)**:
    - **ALTO — a garantia "estruturalmente impossível" de
      `POST /auth/demo-login` depende de uma constraint que não existe no
      banco real deste ambiente.** O comentário do endpoint
      (`app/api/v1/auth.py`) afirma que cruzar pra outro tenant é
      estruturalmente impossível porque a query filtra por
      `Tenant.slug=="demo"` + `User.email==DEMO_ADMIN_EMAIL` com
      `scalar_one_or_none()` — o que só é uma garantia real se essas
      colunas forem `UNIQUE` no banco. Confirmado via `\d tenants`/`\d
      users` direto no Postgres: **não existe nenhum índice único em
      `tenants.slug` nem em `users.email`** (só `tenants_subdomain_key`)
      — o `unique=True` do SQLAlchemy nunca virou constraint real porque
      o banco nasceu via `create_all()` num schema legado, sem
      `alembic_version` (confirmado: `to_regclass('alembic_version')`
      retorna vazio). `_seed_demo_tenant()` (`app/core/events.py`, roda
      em todo boot, sem lock) faz um `SELECT` seguido de `INSERT` sem
      nenhuma trava — dois processos do app subindo ao mesmo tempo (o
      caso normal de um rolling deploy no Railway, que a CLAUDE.md já
      documenta como disparado a cada push em `main`) poderiam ambos
      passar pelo `SELECT` antes de qualquer `INSERT` comitar, e sem
      constraint única nada impede a duplicata. Se isso acontecer, o
      efeito observável não é vazamento cross-tenant (a query do
      `demo-login` levantaria `MultipleResultsFound` → 500, falha
      fechada) — mas o próprio `resetar_tenant_demo` também usa
      `scalar_one_or_none()` pra achar o tenant demo, e quebraria do
      mesmo jeito, desligando o reset diário permanentemente até
      intervenção manual. Não reproduzido o race de boot concorrente em
      si (exigiria subir uma 2ª instância do app), mas a premissa que o
      torna possível — ausência da constraint única — foi confirmada
      direto no banco, não é hipótese.
    - **ALTO — reset do tenant demo nunca limpa Qdrant nem S3, só
      Postgres.** `resetar_tenant_demo` (`app/services/demo_reset.py`)
      apaga a linha `Document` do Postgres mas nunca chama
      `delete_document_chunks()` nem nada de
      `app/integrations/object_storage.py` — confirmado por grep: o
      próprio módulo `object_storage.py` **não tem nenhuma função de
      delete** (só `upload_bytes`/`get_bytes`/`generate_presigned_url`).
      Como `documents.py` auto-ingesta no RAG qualquer documento
      `APROVADO`/`PROTOCOLADO` sem nenhum guard de tenant demo
      (`app/api/v1/documents.py:358-366`), um visitante que aprova um
      documento deixa: (a) o blob no S3 órfão pra sempre (quando S3
      estiver configurado — Fase 141), e (b) os chunks vetoriais no
      Qdrant órfãos pra sempre, ainda marcados com o `tenant_id` do
      tenant demo (que nunca muda entre resets) — ou seja, buscas RAG de
      futuras sessões de visitante podem continuar trazendo conteúdo de
      documentos que o "reset diário" supostamente apagou. Mesma classe
      de risco já documentada nas Fases 186/188.1 (duplicação de chunks
      no Qdrant por reingestão sem limpeza prévia), só que aqui é vazamento
      permanente, não duplicação.
  - **2 observações menores, não confirmadas como defeito** (registradas
    pra não se perderem, não viram achado por falta de reprodução):
    anomalia real de log (`ws_publish_failed error="Event loop is
    closed"`) observada 1x durante a reconfirmação do 198.B — a mensagem
    `AGENT_RUN_COMPLETED` ainda assim chegou ao assinante Redis, e uma 3ª
    task no mesmo worker forkado não reproduziu o mesmo erro; a causa
    provável é o mesmo padrão de bug já documentado e parcialmente
    corrigido em `app/workers/async_utils.py` (conexão asyncpg presa a um
    event loop fechado entre tasks do Celery, por isso `engine.dispose()`
    é chamado no `finally`) — mas o `_redis_pool` singleton de
    `app/db/redis.py` **não** recebe o mesmo tratamento (`close_redis()`
    nunca é chamado em `run_worker_coro`), o que é a causa mais provável,
    ainda que não 100% confirmada nem reproduzida numa 2ª tentativa. E:
    o rate-limiter de `demo-login` (INCR seguido de EXPIRE condicional)
    é atomicamente seguro sob concorrência normal (confirmado: `INCR` é
    atômico, testado com >20 chamadas reais disparando 429 corretamente),
    mas tem uma janela teórica de fail-open→trava-permanente se o `INCR`
    suceder e o `EXPIRE` falhar por uma queda de conexão exatamente entre
    as duas chamadas — não induzido de propósito, fica como hipótese.
  - **Nota operacional**: o bloqueio de subagentes por um lembrete de
    "plan mode ativo" injetado (mesmo achado da Fase 178) **recorreu
    nesta rodada** — desta vez em 2 dos 3 agentes lançados (o de
    Playwright real e, parcialmente, o de auditoria de segurança, que
    corretamente se recusou a fazer qualquer escrita e caiu pra leitura
    read-only). Isso já não é mais "transitório desta sessão" como a
    178 supôs — recorreu numa sessão totalmente diferente. Confirma que é
    um problema de harness a reportar, não algo que se resolve sozinho.
    A verificação real do frontend (Playwright bloqueado) foi refeita
    manualmente pela sessão principal: `npm run dev` real com
    `API_URL` apontando pro backend local, confirmando via HTTP através
    do proxy do Next.js que `/auth/demo-login` bate no backend local (não
    produção — fecha a mesma classe de risco da 176.6) e captura de tela
    via Chromium headless direto (sem o pacote `playwright`, que não
    está instalado neste ambiente) confirmando o botão "Entrar como
    visitante" renderizado corretamente em `/login`.
  - Nenhuma correção feita nesta fase — decisão do usuário sobre quais
    achados viram fase nova. **Próxima rodada deve**: se os 2 achados
    ALTOS forem corrigidos, reconfirmar (a) que `_seed_demo_tenant()`
    ganhou proteção contra corrida de boot concorrente (lock consultivo
    ou constraint única de verdade aplicada via `ALTER TABLE ... ADD
    CONSTRAINT` idempotente, mesmo padrão do backfill de colunas em
    `events.py`) e (b) que o reset do tenant demo chama
    `delete_document_chunks()` e alguma forma de limpeza S3 (ou aceita
    documentar a limitação, se optar por não implementar delete de S3
    nesta fase). Também vale, numa rodada futura, terminar o item que o
    achado 5 da auditoria adversarial explicitamente deixou fora de
    escopo por falta de tempo: uma varredura completa dos 82 endpoints
    procurando falta de filtro por `tenant_id` — agora com um agravante
    novo, já que qualquer JWT de ADMIN sem senha nenhuma (o próprio
    `demo-login`) torna esse tipo de bug, se existir, um exploit público
    sem credencial, não mais um requisito de conta comprometida.
- **Fase 202** — implementação dos 2 achados ALTO da Fase 201, a pedido
  do usuário ("transforme os achados em novas fases e inicie as
  correções").
  - **202.A** — `backend/app/core/events.py` ganhou 2
    `CREATE UNIQUE INDEX IF NOT EXISTS` idempotentes (mesmo padrão
    fail-soft da lista de ALTERs) em `tenants.slug` e `users.email`,
    fechando a lacuna real confirmada na Fase 201 (nenhuma das duas
    colunas tinha constraint única de verdade no Postgres, apesar do
    `unique=True` do SQLAlchemy). `_seed_demo_tenant()` ganhou
    `pg_advisory_xact_lock` logo no início, serializando boots
    concorrentes (rolling deploy) sem mudar nada pro caso comum de 1
    instância só. Verificado: os 2 índices foram criados sem conflito
    no Postgres local (sem duplicata pré-existente); teste novo
    (`test_tenant_user_unique_constraints.py`) confirma `IntegrityError`
    real ao tentar duplicar slug/email; verificação empírica adicional
    (não virou teste permanente) — 2 chamadas **verdadeiramente
    concorrentes** de `_seed_demo_tenant()` (`asyncio.gather`, não
    sequencial) contra um banco Postgres descartável resultaram em
    exatamente 1 tenant `slug="demo"`, confirmando que o lock serializa
    a corrida de verdade.
  - **202.B** — `object_storage.py` ganhou `delete_bytes()` (mesmo
    padrão try/except + `ObjectStorageError` das outras 3 funções do
    módulo). `resetar_tenant_demo` agora lê os `Document` do tenant demo
    ANTES do DELETE genérico e chama `delete_document_chunks()` (Qdrant,
    reaproveitando `_collection_for` de `auto_ingest.py`) e
    `object_storage.delete_bytes()` (S3, só se configurado) pra cada um
    — fail-soft, uma falha de Qdrant/S3 nunca trava o reset do Postgres.
    Fecha o vazamento real confirmado na Fase 201: documentos aprovados
    no tenant demo não ficam mais órfãos no Qdrant/S3 a cada reset.
    Teste novo (`test_demo_reset_cleanup.py`, Qdrant real em memória)
    confirma que os chunks somem da collection e que `delete_bytes` é
    chamado com a `storage_key` certa; segundo teste confirma que um
    documento sem `storage_key` (caminho legado base64) não dispara
    nenhuma chamada de delete no S3.
  - Suíte de testes relacionada (unique constraints + demo reset +
    demo login + demo guard + object storage) rodada isolada e em
    conjunto — a mesma flakiness de pool asyncpg/pytest-asyncio já
    documentada (Fase 199) apareceu de novo em 3 dos testes quando
    rodados juntos, mas todos passam limpo quando isolados; nenhum é
    específico desta fase (reproduz em testes pré-existentes não
    tocados também).
- **Fase 203** — rodada de teste geral a pedido do usuário, desta vez
  também com propostas de evolução de produto (não só achados de bug).
  Ambiente real (Postgres+Redis+Celery+uvicorn) subido de verdade.
  - **Achado pré-existente confirmado nesta rodada** (via screenshot real
    do usuário do painel "Insights proativos" do Cérebro, antes mesmo da
    rodada formal começar): `backend/app/services/brain_insights.py::
    gerar_insights()` chama `call_llm(...)` diretamente, sem nunca entrar
    em `user_ai_creds(db, user_id)` (`app/integrations/byok.py`) — ao
    contrário de toda outra rota disparadora de IA do sistema, essa não
    tem NENHUM fallback pra BYOK (nem o do próprio SUPERADMIN que clicou
    no botão). Depende 100% de `ANTHROPIC_API_KEY` estar configurada no
    servidor; se ausente/perdida em produção, o erro é exatamente
    `Could not resolve authentication method` do SDK Anthropic, batendo
    com o screenshot do usuário. `db`/`current_user` já estão disponíveis
    no call site (`app/api/v1/system.py`, `POST /system/brain/insights`)
    — fix é threading-los através de `gerar_insights()`.
  - **202.A/202.B reconfirmados de forma independente e mais fundo** que
    a própria Fase 202: 202.A com 5 chamadas verdadeiramente concorrentes
    de `_seed_demo_tenant()` (`asyncio.gather`, banco descartável — até
    aqui só 2 tinham sido testadas) resultando em exatamente 1 tenant
    `slug="demo"`, e os 2 índices únicos confirmados presentes no
    Postgres local após um boot novo; 202.B reconfirmado via HTTP real de
    ponta a ponta (não chamando `resetar_tenant_demo()` direto em Python
    como a própria Fase 202 fez) — 2ª instância do backend com Qdrant
    real em memória, documento criado e aprovado via HTTP real,
    `POST /rag/search` confirma o chunk findável ANTES do reset,
    `POST /tenants/demo/reset` disparado via HTTP como SUPERADMIN real, e
    o mesmo `POST /rag/search` confirma `count=0` DEPOIS — o fluxo
    completo (não só a função de serviço isolada) funciona.
  - **Varredura completa dos ~82 endpoints por `tenant_id`** — lacuna que
    a Fase 201 deixou documentada e nenhuma rodada seguinte tinha
    fechado. 4 agentes paralelos, cada um auditando um subconjunto dos
    routers de `app/api/v1/`; 3 completaram (a 4ª falhou por limite
    semanal de uso da API do harness — refeita manualmente pela sessão
    principal lendo os 7 arquivos restantes: `reports_admin.py`,
    `system.py`, `tenant.py`, `tenants_admin.py`, `teses.py`, `users.py`,
    `ws.py` — todos limpos, sem achado novo). **3 achados reais
    confirmados**:
    - **ALTO — `POST /rag/ingest` permite envenenamento cross-tenant do
      RAG privado.** `app/api/v1/rag.py:154-183`. Gate é só
      `require_role("ADMIN")` (qualquer tenant, não SUPERADMIN); o
      payload aceita `metadata` livre do cliente e nunca sobrescreve
      `metadata["tenant_id"]` com o `tenant_id` real do chamador (ao
      contrário do caminho de auto-ingest confiável,
      `app/rag/auto_ingest.py:33`, que sempre carimba o valor derivado do
      servidor). `app/rag/retrieval.py:82` (`retrieve()`) confia
      cegamente no `tenant_id` do payload como único mecanismo de
      isolamento pras collections privadas
      (`peticoes_afj`/`memorias_afj`/`documentos_clientes`/
      `doutrina_privada`). Um ADMIN do tenant A pode plantar conteúdo
      malicioso que passa a aparecer nas buscas jurídicas privadas do
      tenant B como se fosse dado confiável do próprio escritório B —
      alcançável com zero credenciais reais via `POST /auth/demo-login`
      (Fase 200), já que o tenant demo também tem um ADMIN.
    - **MÉDIO — `integrity.py`: `responsavel_id` de `IntegrityRisk` não é
      validado contra o tenant do chamador**, ao contrário de todo outro
      FK do sistema (`client_id`/`process_id` sempre passam por um
      validador). `GET /integrity/risks` faz um outer join sem filtro de
      tenant no lado de `User` — um ADMIN pode setar `responsavel_id` pra
      um UUID de usuário de outro tenant (se souber/adivinhar) e ler de
      volta o `full_name` desse usuário. Severidade limitada por exigir
      um UUID válido em mãos primeiro (não é enumerável) — é um
      vazamento de nome via confirmação, não exposição de linha inteira.
    - **BAIXO — `GET /rag/coverage` devolve contagem agregada
      cross-tenant.** `qdrant.count()` roda sem filtro de tenant pras 4
      collections privadas — qualquer usuário staff vê o total de chunks
      armazenados na plataforma inteira (não só do próprio tenant) em
      cada collection. Nenhum conteúdo/PII vaza, só um sinal quantitativo.
    - Todos os outros ~75 endpoints auditados (grupos A/C/D completos:
      `agent_prompts`, `agents`, `ai_oauth`, `approvals`, `audit`,
      `auth`, `billing`, `clients`, `crm`, `custom_agents`, `documents`,
      `financial`, `google_integration`, `integrations_hub`, `invoices`,
      `lgpd`, `notifications`, `petition_templates`, `portal`,
      `processes`, `publications`, `push`, `rag` [`/search`,
      `/jurisprudencia/favorabilidade`], `reports_admin`, `system`,
      `tenant`, `tenants_admin`, `teses`, `users`, `ws`) vieram limpos.
  - **Auditoria adicional (sessão principal, sem novos agentes por causa
    do limite semanal já atingido)**: revisão LGPD/PII dos 5 modelos de
    Ética/Integridade (Fase 189) — nenhum guarda PII de cliente (só dados
    de colaborador/governança interna), fora do escopo de
    `erase_client_data`; não é um gap, é o design correto. Revisão de
    design (não confirmada empiricamente, registrada como observação pra
    não se perder): `resetar_tenant_demo()` apaga `Approval`/`AgentRun`
    do tenant demo incondicionalmente, sem checar se algum está
    `PENDENTE`/`RUNNING` no exato momento do reset — se um worker Celery
    estiver no meio de `resume_chain_after_approval` pra uma chain HITL
    do tenant demo quando o reset diário (4:45am) ou o botão manual
    disparar, o `UPDATE` subsequente do worker viraria um no-op silencioso
    (linha já apagada) em vez de erro — não reproduzido de propósito
    (exigiria orquestrar uma race real), fica como hipótese pra próxima
    rodada decidir se vale a pena investigar mais fundo.
  - **Walkthrough real do frontend via Playwright**: cortado nesta rodada
    por decisão de tempo/recursos (o limite semanal de uso já tinha sido
    atingido por um dos agentes da varredura de tenant_id) — não subiu o
    frontend de verdade desta vez. Fica como lacuna explícita pra próxima
    rodada, no mesmo padrão de transparência das rodadas anteriores.
  - **Evolução de produto** (novo nesta rodada, a pedido do usuário — não
    são achados de bug): 2 frentes paralelas (backend/IA e frontend/UX)
    levantaram propostas lendo `CLAUDE.md`, `/sobre` e os módulos
    existentes. 16 propostas no total (8 de cada frente) — ver o
    relatório apresentado ao usuário ao final desta fase para a lista
    completa com nome, módulo estendido, justificativa e estimativa de
    complexidade (S/M/L). Nenhuma decisão de priorização foi tomada nesta
    fase — cabe ao usuário escolher quais viram fase nova.
  - Nenhuma correção foi feita nesta fase (metodologia padrão) — decisão
    do usuário sobre quais achados/evoluções viram fase nova. **Próxima
    rodada deve**: se os 3 achados de `tenant_id` forem corrigidos,
    reconfirmar via HTTP real (não só teste unitário) que `POST
    /rag/ingest` carimba o `tenant_id` do servidor, ignorando qualquer
    valor no `metadata` do cliente; completar o walkthrough real do
    frontend via Playwright que ficou de fora aqui; e considerar
    investigar a hipótese não confirmada do reset-durante-chain-HITL
    acima com uma race real orquestrada (2 processos, não só leitura de
    código).
- **Fase 204** — implementação dos 4 achados de bug confirmados na Fase
  203 (o usuário optou por corrigir os achados agora, deixando as 16
  propostas de evolução de produto pra decidir depois).
  - **204.A** — `backend/app/services/brain_insights.py::gerar_insights()`
    passou a receber `db`/`user_id` e envolve a chamada a `call_llm(...)`
    em `user_ai_creds(db, user_id, "brain_insights")`
    (`app/integrations/byok.py`), o mesmo mecanismo de fallback BYOK usado
    por `generate_petition`/`review_document`/`manage_contract` — fecha o
    gap real que causava o erro do screenshot do usuário
    (`Could not resolve authentication method`) quando a
    `ANTHROPIC_API_KEY` do servidor está ausente. `POST /system/brain/
    insights` (`app/api/v1/system.py`) agora passa `db`/`current_user.id`.
    Verificado via HTTP real contra o backend local (Postgres+Redis reais,
    login SUPERADMIN real): o endpoint continua respondendo `200` com
    `ok: False` e a mesma mensagem de erro do SDK Anthropic (nem
    `ANTHROPIC_API_KEY` nem BYOK configurados neste sandbox) — confirma
    que o código agora passa pelo caminho de fallback correto antes de
    cair no erro, em vez de nunca ter tentado.
  - **204.B** — `POST /rag/ingest` (`app/api/v1/rag.py`) agora carimba
    `metadata["tenant_id"]` com o `current_user.tenant_id` real do servidor
    pras 4 collections privadas (`PRIVATE_COLLECTIONS`), ignorando
    qualquer `tenant_id` vindo no payload do cliente — mesmo padrão do
    caminho de auto-ingest confiável (`app/rag/auto_ingest.py`). Fecha o
    achado ALTO da Fase 203 (envenenamento cross-tenant do RAG privado).
    Teste novo (`test_rag_ingest_tenant_stamping.py`, Qdrant real em
    memória) reproduz o ataque de ponta a ponta: um ADMIN forja
    `tenant_id` de outro tenant no payload, confirma que a vítima não vê o
    conteúdo plantado em `retrieve()`, e que o conteúdo fica corretamente
    atribuído ao tenant real do atacante (não descartado, só não
    mal-atribuído).
  - **204.C** — `integrity.py` ganhou `_validar_responsavel_id()` (mesmo
    padrão de `_validar_client_id`/`_validar_process_id` de
    `documents.py`), chamado em `create_risk`/`update_risk`; `list_risks`
    também ganhou filtro de tenant direto no `outerjoin` com `User`
    (defesa em profundidade, cobre até uma linha legada pré-fix). Fecha o
    achado MÉDIO da Fase 203 (FK sem validação de tenant + vazamento de
    nome via `GET /integrity/risks`). Testes novos
    (`test_integrity_responsavel_tenant_scope.py`, Postgres real com 2
    tenants de verdade) reproduzem o ataque exato (setar `responsavel_id`
    pro usuário de outro tenant) em `create_risk`/`update_risk`
    (bloqueado com 422) e confirmam que `list_risks` não vaza o nome
    mesmo com uma linha inserida direto no banco simulando dado legado.
  - **204.D** — `GET /rag/coverage` (`app/api/v1/rag.py`) agora passa um
    `count_filter` por `tenant_id` pro `qdrant.count()` nas 4 collections
    privadas (público continua sem filtro, por design). Fecha o achado
    BAIXO da Fase 203 (contagem agregada cross-tenant). Teste novo
    confirma que só as collections privadas recebem o filtro.
  - Suíte completa rodada (`pytest tests/`): 812 passed — a mesma
    flutuação de ERROR/FAILED entre rodadas já documentada desde a Fase
    199 (pool asyncpg reutilizado entre event loops por-teste do
    pytest-asyncio) apareceu de novo, incluindo em arquivos nunca tocados
    nesta fase; confirmado que não é regressão desta fase isolando os 4
    testes novos (todos passam limpo sozinhos) e, por precaução extra,
    revertendo temporariamente os 4 fixes (`git stash`) pra confirmar que
    um teste de um módulo não tocado (`test_process_fonte.py`) já falhava
    exatamente igual antes desta fase — não é algo introduzido aqui.
  - Não implementadas nesta fase (fora do escopo pedido pelo usuário): as
    16 propostas de evolução de produto da Fase 203, e as 2 observações
    não confirmadas (reset-durante-chain-HITL, walkthrough Playwright).
- **Fase 205** — usuário escolheu, das 16 propostas de evolução da Fase
  203, começar pelas 5 de complexidade S ("construa as pequenas
  primeiro"). Nenhuma é achado de bug — são extensões de produto sobre
  módulos existentes.
  - **205.1 — Follow-up SLA em petições protocoladas**: `Document` ganha
    `protocolado_em`/`follow_up_dias`/`follow_up_alertado` (opt-in por
    documento). `update_document` carimba `protocolado_em` uma única vez
    na transição pra PROTOCOLADO (separado de `updated_at`, que mudaria a
    cada edição posterior) e reseta `follow_up_alertado=False` numa
    reprotocolação. Nova task Celery Beat diária (7h45, mesma janela dos
    outros alertas de prazo/publicação) `check_petition_followups` avisa
    o advogado quando uma petição fica protocolada sem retorno da corte
    além do prazo configurado — só avisa, nunca age sozinho. Frontend
    (`documentos/page.tsx`) ganha o campo de dias de follow-up no modal
    de edição, mostrado só quando o status é PROTOCOLADO. Testes novos
    (`test_petition_followup_sla.py`, Postgres+Redis reais) confirmam o
    carimbo único, o reset em reprotocolação, e que a task só alerta quem
    já venceu o prazo e é idempotente (não duplica no reprocessamento).
    **Achado colateral desta fase, corrigido de quebra**: `_to_response()`
    em `documents.py` quebrava (`pydantic.ValidationError`) contra o
    `_FakeDB` de `test_documents_storage_fase141.py` porque
    `follow_up_alertado=d.follow_up_alertado` chegava `None` — o
    `default=False` do SQLAlchemy só é aplicado num flush real contra
    Postgres, e o Fake daquele teste nunca simula isso. Mesma classe de
    bug já corrigida uma vez na Fase 199 (`bool(tenant.is_demo)`); mesmo
    fix aqui (`bool(d.follow_up_alertado)`).
  - **205.2 — Histórico de Aprovações**: `/aprovacoes` ganha abas
    Pendentes/Resolvidas. `ApprovalCard`/`ApprovalListItem` ganham
    `ExpiresBadge` (countdown de expiração, urgente se <24h, "vencida" se
    passou) reaproveitando `Approval.expires_at` (Fase 191, existia mas
    nunca aparecia na UI) e `ResolvedStatusBadge` (verde/vermelho) pra
    aba Resolvidas, que renderiza em modo `readOnly` (sem os botões
    Aprovar/Rejeitar).
  - **205.3 — Navegação contextual no Cliente 360**: `GET /documents` e
    a tela de Documentos ganham filtro `?client_id=`; Faturas já tinha
    suporte no backend, só faltava o filtro no frontend. Cliente 360
    ganha uma linha "Documentos deste cliente"/"Faturas deste cliente"
    logo abaixo do cabeçalho, e o link "Gerenciar" da aba Financeiro
    passa a levar o filtro junto.
  - **205.4 — Filtro de data + exportação CSV em Auditoria**:
    `GET /audit` ganha `date_from`/`date_to`; novo `GET /audit/export`
    (mesmo padrão `StreamingResponse` de `GET /financial/export`, teto de
    50k linhas). Frontend ganha os 2 campos de data e um botão Exportar.
    Teste novo usa o padrão "nunca commita, deixa o rollback do fechamento
    de sessão limpar" (não o padrão usual de DELETE explícito) porque
    `audit_logs` é imutável por trigger de banco (Fase 148).
  - **205.5 — Solicitar aumento de orçamento de IA**: novo endpoint
    `POST /system/ai-budget/request-increase` — quando um usuário bate no
    teto mensal de IA (429 de `enforce_budget`), pode pedir aumento direto
    da tela em vez de precisar contatar o ADMIN manualmente; notifica só
    ADMIN/SÓCIO/SUPERADMIN do MESMO tenant, com dedup de 1 pedido/dia por
    usuário. `agentes/page.tsx` chama esse endpoint automaticamente no
    429 (antes só mostrava a mensagem genérica de erro, descartando o
    detalhe real do limite).
  - Verificação: `ruff check` + `py_compile` limpos nos 8 arquivos
    backend tocados; `tsc --noEmit` + `eslint` limpos nos 7 arquivos
    frontend tocados (1 warning pré-existente de `exhaustive-deps` em
    `documentos/page.tsx`, não novo desta fase). Suíte completa
    (`pytest tests/`): 819 passed (subiu de 812 na Fase 204 — os 2 testes
    de `test_documents_storage_fase141.py` que quebravam antes do fix do
    achado colateral agora entram na contagem de sucesso todo run) — a
    mesma flutuação de ERROR/FAILED entre rodadas (pool asyncpg
    reutilizado entre event loops por-teste do pytest-asyncio, documentada
    desde a Fase 199) apareceu de novo, confirmada como não-regressão
    isolando cada teste novo (todos passam limpo sozinhos) e reproduzindo
    o mesmo padrão num arquivo pré-existente não tocado
    (`test_ai_budget_request_increase.py`, da própria 205.5).
  - Não implementadas nesta fase: as 11 propostas restantes (M/L) da
    Fase 203 — seguem aguardando decisão do usuário sobre priorização.
- **Fase 206** — usuário pediu pra seguir com as 11 propostas M/L
  restantes da Fase 203, mas deixou a ordem a critério da sessão ("eu
  escolho a ordem"). Primeiro sub-lote: as 3 mais independentes/de menor
  risco, guardando as 2 estruturalmente maiores (agentes customizados
  como passo de chain — toca o orchestrator; analytics comparativo entre
  filiais — precisa de design cuidadoso de isolamento cross-tenant) pro
  fim.
  - **206.1 — Perfil de relator/juiz**: a agregação por relator já
    existia desde a Fase 138.5 (`agregar_favorabilidade_por_relator`),
    só faltava o drill-down. Novo `detalhar_relator()` em
    `app/rag/aggregation.py` (mesmo scroll paginado + dedup por
    `document_id`, retendo os campos por documento em vez de só somar) e
    endpoint `GET /rag/jurisprudencia/favorabilidade/{relator}`. Frontend:
    linhas da tabela de favorabilidade em `busca-juridica/page.tsx`
    viram clicáveis, abrindo um modal com a lista de acórdãos
    (nº processo/data/órgão julgador/área/favorável) daquele relator.
    **Achado do próprio teste, corrigido de quebra**: a implementação
    inicial de `detalhar_relator()` não excluía acórdãos sem
    classificação (`favoravel` ausente), ao contrário da agregação —
    um teste com Qdrant real em memória pegou a divergência (agregado
    dizia "2 total", drill-down devolvia 3) antes de virar bug em
    produção; corrigido pra usar o mesmo critério de exclusão.
  - **206.2 — Preferências de notificação persistentes**: a tela
    Configurações → Notificações já tinha 5 checkboxes, mas
    `saveNotifs()` só gravava em `localStorage` — nada no backend lia
    essa preferência. `User.notification_prefs` (JSONB) + migração
    idempotente; novos `GET/PUT /users/me/notification-preferences`;
    novo `deve_notificar()` em `app/services/notification.py`, chamado
    dentro de `create_notification()`/`create_batch()` (retornam
    `None`/pulam o usuário quando desativado) e nos 2 call sites diretos
    que criam `Notification` fora do serviço pros tipos realmente
    gateados (`deadline_check.py` — PRAZO_VENCENDO/CONTRATO_VENCENDO;
    `approval.py::_notify_tenant_of_approval` — APROVACAO_PENDENTE, só
    o aviso de rotina, **não** o evento WS `NEW_APPROVAL_PENDING` que
    alimenta o contador da fila, nem o reaper de aprovação vencida em
    `approval_reaper.py` — escalação de SLA pra gestores não deve ficar
    silenciada por uma preferência pessoal). Decisão de escopo
    deliberada (mesmo espírito do alerta da Fase 196/197 — nunca fingir
    que uma preferência alcança um fluxo que não alcança): os
    checkboxes `publicacoes_dj` e `email_diario` continuam só no
    frontend por enquanto — o alerta de nova intimação do DJe usa
    `tipo="NOVO_ANDAMENTO"`, o MESMO tipo de 2 outros fluxos não
    relacionados (notificar equipe manual, captura automática por OAB);
    gatear o tipo inteiro sob esse toggle silenciaria os 2 fluxos
    errados. `email_diario` não tem nenhuma rotina de resumo diário
    ainda. Documentado no código pra próxima fase decidir se vale a
    pena um tipo dedicado.
  - **206.3 — Comparativo de período em Relatórios**: `date_from`/
    `date_to` opcionais em `GET /system/analytics/gestao`, cache key
    variando por período. Cada bloco de métrica filtra pelo campo de
    data mais natural: rentabilidade por `FinancialEntry.data_pagamento`,
    produtividade "processos novos"/"documentos" por `created_at`, taxa
    de êxito por `LegalProcess.updated_at` (proxy documentado — o model
    não tem um timestamp dedicado de "quando o desfecho foi registrado",
    mesma classe de aproximação já aceita em `protocolado_em`/
    `updated_at` na Fase 205.1). `processos_ativos`/`prazos_pendentes`
    (carga atual) e `prazos_cumpridos` (sem timestamp de conclusão no
    model) ficam de fora do filtro em qualquer período, por design.
    Frontend: date-range picker na aba Gestão de Relatórios + cálculo
    automático do "período anterior" de mesma duração + card de
    comparativo com deltas (▲/▼) em `GestaoCharts.tsx`.
  - Verificação: `ruff check` + `py_compile` limpos nos 9 arquivos
    backend tocados; `tsc --noEmit` + `eslint` limpos nos 4 arquivos
    frontend tocados (3 warnings pré-existentes de `exhaustive-deps`/
    `no-img-element`, confirmados via `git stash` como não-novos desta
    fase). 11 testes novos com Postgres/Qdrant reais, todos passando
    isolados; a mesma flutuação de ERROR/FAILED em rodada completa
    (pool asyncpg entre event loops do pytest-asyncio, documentada desde
    a Fase 199, mais rate-limit de login estourando quando a suíte
    inteira reusa a mesma credencial em sequência) reproduzida de forma
    idêntica isolando um teste pré-existente não tocado
    (`test_tenant_user_unique_constraints.py`) — não é regressão desta
    fase.
  - Não implementadas nesta fase: as 8 propostas M/L restantes (win-rate
    histórico no strategy_agent, CRM→previsão de caixa, agentes
    customizados como passo de chain, auto-população da Matriz de Riscos,
    analytics entre filiais, score de saúde do cliente, ações em lote em
    Processos, fila de aprovação mobile-first) — seguem pro próximo
    sub-lote.

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
