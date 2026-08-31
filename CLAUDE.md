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
- **Fase 207** — segundo sub-lote das evoluções M/L da Fase 203 ("eu
  escolho a ordem"). 3 das 8 propostas restantes; guardando as 2
  estruturalmente maiores (agentes customizados como passo de chain,
  analytics entre filiais) e as 3 que precisam de mais decisão de produto
  (win-rate/strategy_agent, CRM→previsão de caixa, auto-população da
  Matriz de Riscos) pro sub-lote seguinte.
  - **207.1 — Score de saúde do cliente**: novo `GET /clients/{id}/
    health-score` (`app/api/v1/clients.py`) — score 0-100 puramente
    derivado (nenhum campo novo persistido), combinando 3 sinais já
    existentes: financeiro (40 pts, penaliza receita PENDENTE já vencida),
    engajamento (30 pts, recência de `ClientInteraction`) e processual
    (30 pts, taxa de êxito/acordo dos processos com desfecho), bandado em
    saudável/atenção/risco. Gate `get_current_user` (não
    `require_role`) — sinal agregado/derivado, menos sensível que os
    dados financeiros brutos de `/financeiro`, qualquer advogado que
    trabalhe a relação com o cliente deve ver. Frontend: novo card no
    Cliente 360 (`clientes/[id]/page.tsx`) com badge geral + 3 linhas de
    componente.
  - **207.2 — Fila de aprovação mobile-first**: `/aprovacoes` (lista +
    detalhe lado a lado) forçava a mesma altura fixa da tela no mobile
    que no desktop, e o `useEffect` que auto-seleciona o 1º item da aba
    ao carregar fazia o painel de detalhe aparecer sempre "aberto" mesmo
    no mobile — sem forma de ver a lista primeiro. Novo estado
    `mobileDetailOpen`, desacoplado de `selected` e setado só por
    interação explícita do usuário (nunca pelo auto-select), habilita um
    fluxo lista→toque→detalhe só abaixo de `lg` (desktop continua lado a
    lado, inalterado); botão "Voltar pra lista" (`ArrowLeft`,
    `min-h-[44px]`) só visível no mobile. `ApprovalCard`: botões
    Aprovar/Rejeitar ganham `min-h-[44px]` + empilham em `flex-col` em
    telas muito estreitas (antes espremidos lado a lado). Mudança
    puramente frontend — sem endpoint novo, sem teste de backend
    aplicável.
  - **207.3 — Ações em lote em Processos**: novo `POST /processes/
    bulk-update` (`app/api/v1/processes.py`) — atualiza situação e/ou
    responsável de até 200 processos numa chamada só, mesmo padrão de
    `reatribuir_carteira` (bulk por ids explícitos) e mesmo gate
    (`ADMIN/SOCIO/GESTOR` — ação de gestão, não operação do dia a dia de
    um advogado); processos de outro tenant são silenciosamente
    excluídos da contagem (`atualizados` < `solicitados`), não um erro;
    `responsavel_id` passa por `_validar_advogados_do_tenant` (já
    existente). Frontend (`processos/page.tsx`): primeiro uso de
    checkbox multi-select nesta base de código (confirmado por pesquisa
    prévia — não havia padrão anterior a reaproveitar) — `Set<string>`
    de selecionados, checkbox "selecionar todos visíveis" no cabeçalho
    da tabela e por linha (tabela e grid), toolbar condicional
    (`canBulk && selecionados.size > 0`) com dropdown de situação +
    "Aplicar" + "Exportar CSV" (client-side, só das linhas já
    selecionadas/carregadas) + "Limpar seleção". Escopo deliberadamente
    cortado: reatribuição de responsável em lote não foi ligada na UI
    ainda (exigiria carregar uma lista de advogados não usada hoje nessa
    tela) — backend já suporta, fica pra quando fizer sentido adicionar.
  - Testes novos: `test_client_health_score_fase207.py` (5 testes —
    score neutro sem histórico, receita atrasada derruba o componente
    financeiro, interação recente vs. antiga muda o componente de
    engajamento, taxa de êxito processual, cliente de outro tenant não
    encontrado) e `test_bulk_update_processes_fase207.py` (7 testes —
    atualização em lote bem-sucedida, processo de outro tenant excluído
    da contagem sem erro, responsável válido aplica a todos, responsável
    de outro tenant rejeitado com 422, lista vazia/>200 ids/nem
    situação-nem-responsável todos rejeitados com 422), ambos Postgres
    real, mesmo padrão direto-por-função dos testes recentes (206.3).
    207.2 não gerou teste de backend (mudança puramente frontend).
  - Verificação: `ruff check` + `py_compile` limpos em `clients.py`/
    `processes.py` + os 2 arquivos de teste novos; `tsc --noEmit` limpo;
    `eslint` nos 4 arquivos frontend tocados — 2 warnings pré-existentes
    de `exhaustive-deps` (`clientes/[id]/page.tsx`, `processos/page.tsx`)
    confirmados via `git stash`/`eslint`/`git stash pop` como idênticos
    antes desta fase (só linha deslocada pelas inserções), não
    regressão. Os 12 testes novos passam limpos isolados; rodados junto
    da suíte completa (819 → 831 com os novos), a mesma flutuação de
    ERROR/FAILED entre rodadas (pool asyncpg entre event loops do
    pytest-asyncio + rate-limit de login estourando quando a suíte
    inteira reusa a mesma credencial em sequência, documentada desde a
    Fase 199) reapareceu em arquivos pré-existentes não tocados nesta
    fase (`test_auth.py`, `test_demo_login.py`, `test_clients.py`,
    `test_process_fonte.py`, `test_tenant_user_unique_constraints.py`,
    entre outros) — nenhuma falha nos 2 arquivos novos desta fase.
  - Não implementadas nesta fase: as 5 propostas M/L restantes (win-rate
    histórico no strategy_agent, CRM→previsão de caixa, auto-população
    da Matriz de Riscos, agentes customizados como passo de chain,
    analytics entre filiais) — seguem pro próximo sub-lote, com as 2
    estruturalmente maiores deixadas por último como já planejado.
- **Fase 208** — terceiro sub-lote das evoluções M/L da Fase 203, a pedido
  do usuário ("eu escolho a ordem" segue valendo). Pega as 3 propostas que
  precisavam de mais decisão de produto, guardando as 2 estruturalmente
  maiores (agentes customizados como passo de chain, analytics entre
  filiais) pro sub-lote seguinte.
  - **208.1 — Win-rate histórico no strategy_agent**: `StrategyAgent.
    execute()` (`app/agents/strategy/strategy_agent.py`) já recebia
    `area_direito` mas nunca consultava o histórico de êxito do próprio
    escritório — só jurisprudência via RAG. Novo helper privado
    `_historico_exito_area()` (consulta direta e isolada em
    `LegalProcess.desfecho` por tenant+área, mesmo critério EXITO+ACORDO
    de `analytics_gestao`) injeta uma seção nova no prompt ("HISTÓRICO DE
    ÊXITO DO ESCRITÓRIO NESTA ÁREA") antes do contexto RAG, e expõe
    `taxa_exito_area`/`total_processos_area` no retorno do agente pra
    auditoria/frontend. Amostra pequena (N<3) sinaliza cautela no texto
    em vez de apresentar o percentual como confiável. Escopo cortado
    deliberadamente: não adicionou `tribunal`/`tese_id` como inputs novos
    do agente — só `area_direito`, que já era recebido.
  - **208.2 — CRM → previsão de caixa**: `Opportunity` já tinha
    `valor_estimado`/`probabilidade`/`expected_close` e `/crm/funil`
    (Fase 161) já calculava o pipeline ponderado, só que como total único
    sem bucket de data — nenhum schema novo foi necessário. Novo `GET
    /crm/previsao-caixa` (mesmo gate de `/funil`) devolve os próximos 6
    meses com `pipeline_ponderado` (Opportunity aberta × probabilidade,
    por `expected_close`) e `receita_prevista` (FinancialEntry RECEITA/
    PENDENTE, por `data_vencimento`) **separados** — nunca fundidos num
    único "previsto", pra não confundir estimativa probabilística com
    receita já comprometida. Frontend: novo card em Relatórios → Gestão
    (`GestaoCharts.tsx`), self-fetching (independente do filtro de
    período da página, já que é sempre prospectivo).
  - **208.3 — Auto-população da Matriz de Riscos de Integridade**:
    `IntegrityRisk`/`IntegrityReport` já compartilhavam a mesma lista de
    categorias, mas sem nenhuma ligação automática — e `controles` é
    campo obrigatório no model, exigindo autoria humana por design. Por
    isso "auto-população" virou **sugestão pré-preenchida, nunca criação
    automática** (mesmo espírito do reaper da Fase 191 — nunca decide
    sozinho por quem tem que decidir): novo `GET /integrity/reports/
    {id}/suggest-risk` devolve um rascunho (`risco`/`categoria`/
    `probabilidade`/`impacto` derivados do relato, mais
    `risco_existente_id` se já houver um risco ATIVO da mesma categoria,
    pra evitar sugestão redundante) — o `POST /integrity/risks` de
    criação continua exatamente o mesmo endpoint manual de sempre.
    Frontend (`etica/page.tsx`): botão "Sugerir risco a partir desta
    denúncia" em cada relato, que pré-preenche e abre o formulário
    existente da Matriz (Fase 189.1). **Achado colateral corrigido de
    quebra** (mesmo arquivo já sendo tocado): `create_risk`/`update_risk`
    nunca validavam `categoria` contra a lista, ao contrário de
    `create_report` — mesma classe de inconsistência já corrigida antes
    (Fase 204.C).
  - Testes novos: `test_strategy_agent_win_rate_fase208.py` (3 testes —
    prompt+retorno com taxa de êxito calculada, ausência de histórico
    sinalizada, amostra pequena avisa cautela no prompt),
    `test_crm_previsao_caixa_fase208.py` (2 testes — combina pipeline
    ponderado só de oportunidades abertas com receita só PENDENTE dentro
    da janela de 6 meses, exclui GANHO/PERDIDO/PAGO/DESPESA/fora-da-
    janela; tenant sem dados devolve 6 meses zerados) e
    `test_integrity_suggest_risk_fase208.py` (5 testes — sugestão nunca
    cria linha na matriz, sinaliza risco ativo existente da mesma
    categoria, relato de outro tenant não encontrado, `create_risk`/
    `update_risk` rejeitam categoria inválida com 422), todos Postgres
    real, mesmo padrão direto-por-função das fases recentes.
  - Verificação: `ruff check`+`py_compile` limpos nos 3 arquivos backend
    tocados (`strategy_agent.py`, `crm.py`, `integrity.py`) + 3 arquivos
    de teste novos; `tsc --noEmit` limpo; `eslint` nos 3 arquivos
    frontend tocados (`GestaoCharts.tsx`, `etica/page.tsx`,
    `relatorios/page.tsx` só por import de tipo, sem edição — confirmado
    via `git diff --stat` vazio) — 1 warning pré-existente de
    `exhaustive-deps` em `relatorios/page.tsx`, não novo desta fase. Os
    10 testes novos passam limpos isolados; rodados junto da suíte
    completa, a mesma flutuação de ERROR/FAILED entre rodadas (pool
    asyncpg entre event loops do pytest-asyncio + rate-limit de login,
    documentada desde a Fase 199) reapareceu em arquivos pré-existentes
    não tocados (`test_auth.py`, `test_demo_login.py`, `test_clients.py`,
    `test_process_fonte.py`, `test_tenant_user_unique_constraints.py`,
    entre outros) e também bateu 1 dos testes novos
    (`test_amostra_pequena_sinaliza_cautela_no_prompt`) só na rodada
    completa — confirmado não-regressão isolando (passa limpo sozinho).
  - Não implementadas nesta fase: as 2 propostas M/L estruturalmente
    maiores (agentes customizados como passo de chain — toca o
    orchestrator; analytics entre filiais — precisa de design cuidadoso
    de isolamento cross-tenant), conforme já planejado desde a Fase 206.
- **Fase 209** — rodada de teste geral em larga escala, a pedido explícito
  do usuário ("simule um uso intenso do sistema... elabore fases de
  aplicação e inicie") — diferente de toda rodada anterior, autorização
  prévia pra já começar a implementar os achados confirmados, sem pausar
  pra perguntar quais valem a pena.
  - **Volume real inédito**: nenhuma rodada anterior tinha gerado dado em
    massa de verdade — script novo (scratchpad) gerou 2 tenants
    descartáveis com 150 clientes, 400 processos, 200 documentos, 300
    lançamentos financeiros, 100 oportunidades de CRM, 16 denúncias e 8
    riscos de integridade (total combinado). Simulação de concorrência em
    cima desse volume: leitura paralela em massa nos endpoints 205-208,
    10 disparos simultâneos de `strategy_agent`, múltiplos
    `resolve_approval` concorrentes na mesma Approval, chain HITL completa
    via Postgres+Redis+Celery+uvicorn reais.
  - **Reconfirmação dos 9 itens desde a Fase 203** (204.A-D, 205.1-205.5,
    206.1-206.3, 207.1-207.3, 208.1-208.3) via HTTP real contra o volume
    gerado — todos OK, nenhuma regressão de interação entre eles.
  - **Lacuna 1 fechada — race demo-reset×chain-HITL** (hipótese aberta
    desde a Fase 203, nunca reproduzida em 3 rodadas seguintes): 13
    tentativas reais de concorrência (timing variado + fault injection
    determinística com delays controlados via env var, incluindo bypass
    do gargalo de rede do Qdrant/S3 pra isolar a variável). Conclusão:
    a premissa de código da Fase 203 (DELETE incondicional +
    UPDATE tardio sem lock explícito) segue válida, mas o "silent no-op"
    hipotetizado **não é alcançável pelo caminho normal de
    `resolve_approval`** — achado novo não previsto: o `SELECT ... FOR
    UPDATE` na Approval (Fase 132) fica retido durante **toda** a
    duração da requisição (inclusive `resume_chain_after_approval`
    inteiro), porque só é liberado no commit final, que acontece dentro
    da própria função de retomada. Como `resetar_tenant_demo` deleta
    `Approval` antes de `AgentRun` na mesma transação, seu DELETE
    simplesmente bloqueia atrás desse lock até o resolve terminar — não
    existe janela pro reset intercalar um DELETE no meio da retomada.
    Confirmado empiricamente: um delay determinístico de 3s injetado no
    meio do resume produziu um stall medido de ~3.5s no loop de delete do
    reset, na hora exata em que ele tenta a linha de Approval. Proteção
    incidental (efeito colateral do lock da Fase 132), não desenhada de
    propósito — registrado aqui pra não se perder.
  - **Lacuna 2 fechada — walkthrough real via Playwright** (bloqueado ou
    pulado em quase toda rodada desde a Fase 178): script Node usando o
    Playwright global do sandbox (`/opt/node22/lib/node_modules/
    playwright`, sem tocar `package.json`) navegou de verdade por login →
    dashboard → `/aprovacoes` → `/relatorios` → `/etica` → `/processos` →
    Cliente 360 → `/auditoria` → `/integracoes`, com o tenant de volume
    logado (não o demo). **Achado real, corrigido na hora**:
    `GET /system/analytics/financeiro` (widget financeiro do dashboard)
    quebrava com 500 sempre que o tenant tinha algum `FinancialEntry` —
    `Row.t` é um atributo interno depreciado do SQLAlchemy (alias da
    própria tupla da linha), e a query rotulava a soma agregada como
    `.label("t")`, colidindo com ele: `r.t` devolvia a linha inteira, não
    o valor. Nunca pego antes porque nenhuma rodada tinha exercitado esse
    endpoint específico com um browser real. Corrigido (label renomeado
    pra `total_grupo`) e verificado via HTTP real antes mesmo da auditoria
    formal — commit separado (`a62e0a2`).
  - **Auditoria paralela adversarial** (4 agentes via `Agent` tool, cada
    um reproduzindo com HTTP real contra o volume gerado, não só leitura
    de código) — **3 achados confirmados**:
    - **LGPD (MÉDIO-ALTO)**: `erase_client_data` não alcançava
      `Opportunity` (CRM, Fase 208.2) — PII em `descricao`/`motivo_perda`
      sobrevivia ao "esquecimento" e continuava visível em
      `GET /crm/opportunities`. Mesma classe de gap já fechada uma vez
      pra `ClientContact`/`ClientInteraction` na Fase 176.3, reaberta por
      um modelo que só passou a existir depois daquele fix.
    - **Performance (ALTO)**: `POST /processes/bulk-update` (207.3)
      emitia um `UPDATE` por processo (SELECT + loop Python + flush) —
      confirmado via log de statements do Postgres: 200 round-trips
      separados num lote de 200. Invisível como lentidão em `localhost`
      (sub-ms), mas estrutural: em produção (Railway→Postgres com RTT
      real) vira 200ms-1s de latência pura de rede numa chamada que devia
      ser de dígito único.
    - **Performance (MÉDIO/BAIXO)**: `financial_entries.client_id` e
      `client_interactions.client_id` sem índice próprio — `EXPLAIN
      ANALYZE` confirmou Seq Scan em `/clients/{id}/health-score`
      (207.1); mesma lacuna em `/crm/previsao-caixa` (208.2) e
      `/system/analytics/gestao` (206.3) pros filtros de
      status/data. Inofensivo no volume testado (sub-ms), mas full-scan
      por chamada em escala maior.
    - **Achado funcional (BAIXO, não-segurança)**: `GET /financial
      ?client_id=` nunca declarava o parâmetro — FastAPI descartava
      silenciosamente e a navegação contextual do Cliente 360 (205.3)
      devolvia todos os lançamentos do tenant em vez de só os do
      cliente, contradizendo o próprio changelog da Fase 205.3
      ("já tinha suporte no backend"). Confirmado que não vazava dado
      cross-tenant — só não filtrava.
    - **Cross-tenant/segurança**: todos os 9 itens de 204-208 vieram
      limpos (nenhum IDOR, nenhum vazamento) — reconfirmação mais ampla
      já feita nesta mesma fase.
    - **8 propostas de evolução de produto** levantadas (não bugs) — ver
      Fase 211+ pra quais viraram implementação.
  - **Fase 210** (implementação imediata dos 4 achados confirmados,
    mesma sessão, conforme autorizado): erase_client_data estendido a
    Opportunity + GET /lgpd/clients/{id}/export passa a incluir
    `oportunidades_crm`; bulk-update reescrito pra `UPDATE ... WHERE id =
    ANY(...)` único; `GET /financial` ganha o parâmetro `client_id` que
    faltava; 4 índices novos (`financial_entries` × client_id/status+data,
    `client_interactions` × client_id) via `CREATE INDEX IF NOT EXISTS`
    idempotente em `events.py`. Verificado via HTTP real contra Postgres
    real (não só os 2 testes novos com Postgres real —
    `test_lgpd_erasure_reaches_crm_fase210`,
    `test_financial_client_id_filter_fase210` — porque a suíte automatizada
    apresentou a mesma flutuação de pool asyncpg/pytest-asyncio já
    documentada desde a Fase 199, desta vez reproduzida de forma
    consistente mesmo isolando teste a teste; confirmado não-regressão
    reproduzindo o mesmo padrão num arquivo de controle totalmente não
    tocado, `test_analytics_gestao_periodo.py`, que também falha isolado
    nesta sessão — sintoma de degradação do ambiente desta sessão
    específica, não do código). Índices confirmados criados via `\di`
    direto no Postgres.
  - **Próxima rodada deve**: investigar por que a flakiness de pool
    asyncpg/pytest-asyncio, historicamente intermitente ("passa isolado"),
    passou a ser consistente mesmo isolando teste a teste nesta sessão —
    pode ser drift de versão de dependência (pytest-asyncio/anyio) ou algo
    específico do ambiente desta sessão de longa duração; vale reproduzir
    numa sessão nova antes de investir tempo em diagnóstico profundo.
    Considerar também as 7 propostas de evolução restantes levantadas
    nesta fase (playbooks de agentes por área, dossiê em PDF, metas de
    captação no CRM, central de tarefas cross-módulo, score de qualidade
    de dado LGPD-aware, alerta de risco de prescrição por tese, simulação
    de honorários vs. histórico real).
- **Fase 211** (1ª das 8 propostas de evolução da Fase 209, escolhida por
  ser a mais simples/menor risco — puramente read-only, zero campo novo):
  timeline unificada no Cliente 360. Novo `GET /clients/{id}/timeline`
  junta interações (`ClientInteraction`), marcos processuais (abertura +
  desfecho de `LegalProcess`, mesma aproximação de `updated_at` já aceita
  em 205.1/206.3), pagamentos recebidos (`FinancialEntry` RECEITA/PAGO) e
  petições protocoladas (`Document.protocolado_em`, Fase 205.1) numa
  lista cronológica única, evitando que o advogado precise abrir 4 telas
  separadas pra reconstruir o histórico de um cliente. Frontend: novo
  card "Linha do tempo" no Cliente 360, logo abaixo do score de saúde
  (207.1). Verificado via HTTP real contra Postgres real com dado da
  volume gerada na Fase 209 (evento com os 4 tipos presentes, ordenação
  cronológica correta); teste novo com Postgres real
  (`test_client_timeline_fase211.py`) — mesma flakiness de pool já
  documentada impediu rodar via pytest nesta sessão, mas a verificação
  HTTP contra o backend real já confirma o comportamento.
- **Fase 212** (2ª das 8 propostas de evolução da Fase 209): score de
  qualidade de dado LGPD-aware. Novo `GET /system/analytics/
  lgpd-qualidade` (ADMIN/SOCIO — mesmo gate sensível de
  erase_client_data/export_client_data, já que lista clientes com lacuna
  de conformidade) sinaliza 3 lacunas acionáveis por cliente: (1) status
  ATIVO sem `lgpd_consent`, (2) `lgpd_consent=True` sem
  `lgpd_consent_at` (dado inconsistente — impossível provar QUANDO o
  consentimento foi obtido), (3) titular sem CPF/CNPJ cadastrado. Score
  0-100 = proporção de lacunas sobre o total possível (clientes × 3
  checagens). Frontend: card colapsável "Qualidade de dado LGPD" no
  topo de `/clientes`, visível só pra ADMIN/SOCIO/SUPERADMIN.
  **Achado operacional desta fase**: o ambiente rodava num container
  novo (Postgres/Redis/venv/node_modules zerados) — reproduzida a MESMA
  flakiness de pool asyncpg/pytest-asyncio ("attached to a different
  loop") mesmo num ambiente 100% fresco, o que descarta a hipótese
  anterior de "degradação específica desta sessão longa" (Fase 209/210)
  — é uma incompatibilidade real entre a versão pinada do
  pytest-asyncio (event loop função-scoped por padrão) e o engine
  assíncrono do SQLAlchemy sendo um singleton de módulo. Tentativa de
  fix via `asyncio_default_fixture_loop_scope`/
  `asyncio_default_test_loop_scope = session` no `pytest.ini` NÃO
  resolveu (mesmo erro, ponto de falha ligeiramente diferente) —
  revertida pra não arriscar efeito colateral na suíte sem entender a
  causa raiz por completo; próxima rodada deve investigar mais fundo
  (talvez recriar o engine por teste, ou pinar uma versão diferente do
  pytest-asyncio). Verificado via HTTP real contra Postgres real
  (contagens de lacunas corretas, score calculado certo, gate de role
  ADVOGADO→403 confirmado) — mesmo padrão das fases anteriores desde
  que a flakiness apareceu.
- **Fase 213** (3ª das 8 propostas de evolução da Fase 209): metas de
  captação no CRM. Novo model `CrmMeta` (`tenant_id`+`periodo` YYYY-MM+
  `tipo` RECEITA/NOVOS_CLIENTES, unique constraint pelos 3 — 1 meta ativa
  por período+tipo). `POST /crm/metas` (ADMIN/SOCIO/GESTOR — ação de
  gestão, mesmo espírito do gate de escrita de `teses.py`) faz upsert em
  vez de rejeitar com 409: revisar a meta no meio do mês é o caso comum.
  `GET /crm/metas?periodo=` (gate `_STAFF`, mesmo de `/funil`) devolve
  cada meta com `realizado`/`percentual` já calculados, reaproveitando
  `Opportunity.updated_at` como proxy de "quando foi fechado" (GANHO) —
  mesma aproximação já aceita em 205.1/206.3/207.1. Frontend: widget na
  página do funil (`/clientes/funil`) com barra de progresso + edição
  inline (lápis, só visível pro papel com gate de escrita). Verificado
  via HTTP real contra Postgres real: upsert (mesmo ID, valor atualizado),
  cálculo de realizado (só GANHO dentro do período conta — RECEITA soma
  valor_estimado, NOVOS_CLIENTES conta quantidade), isolamento cross-
  tenant (tenant demo não vê metas do tenant afj), gate 403 pra ADVOGADO
  no POST, tipo inválido rejeitado com 422, delete funcional. Teste novo
  (`test_crm_metas_fase213.py`) com a mesma flakiness de pool
  asyncpg/pytest-asyncio documentada desde a Fase 199 — reproduzida de
  novo mesmo neste ambiente, verificação principal via HTTP real como nas
  fases anteriores.
- **Fase 214** (4ª das 8 propostas de evolução da Fase 209): dossiê do
  cliente em PDF. Novo `GET /clients/{id}/dossie-pdf` (gate
  `ADMIN/SOCIO/GESTOR`, mesmo de `/financeiro` — o dossiê inclui dado
  financeiro via score de saúde) reaproveita `build_report_pdf`
  (`app/utils/pdf_builder.py`, ReportLab, já pinado, sem dependência
  nova — existia desde antes sem nenhum call site) e chama diretamente
  `client_health_score` (207.1) e `client_timeline` (211) em vez de
  duplicar a lógica de agregação, junto com dados básicos do cliente e a
  lista de processos, timbrado com o mesmo padrão de
  `invoices.py`/`resolve_logo_data_url`. Frontend: botão "Baixar Dossiê
  (PDF)" no Cliente 360, ao lado de "Exportar Dados" (LGPD), gated pela
  mesma variável `canFinance` já existente na página. Verificado via
  HTTP real contra Postgres real: PDF válido (`%PDF` no cabeçalho,
  >500 bytes, não só status 200) pro próprio tenant, 403 pra ADVOGADO,
  404 pra cliente de outro tenant (não vazamento). Teste novo
  (`test_client_dossie_pdf_fase214.py`) com a mesma flakiness de pool
  asyncpg/pytest-asyncio documentada desde a Fase 199 — reproduzida de
  novo mesmo neste ambiente (cross-checada contra um arquivo de controle
  não tocado, `test_crm_metas_fase213.py`, que falha de forma idêntica),
  verificação principal via HTTP real como nas fases anteriores.
- **Fase 215** (5ª das 8 propostas de evolução da Fase 209): simulação de
  honorários vs. histórico real. Novo `GET /financial/honorarios-
  historico` (`area_direito` obrigatório, `tipo_acao`/`desfecho`
  opcionais) agrega `FinancialEntry` (RECEITA/HONORARIOS/PAGO) ligado a
  `LegalProcess` via `process_id`, calculando média/mediana/mín/máx em
  Python (mesmo idioma de `_historico_exito_area`, Fase 208.1) — puramente
  read-only, nenhum valor proposto é enviado/persistido, a comparação
  "pretendido vs. média" é 100% client-side. Gate deliberadamente
  divergente do resto de `financial.py` (que usa só ADMIN/SOCIO/GESTOR):
  `ADMIN/SOCIO/ADVOGADO/GESTOR`, mesmo grupo `_STAFF` de `/crm/previsao-
  caixa` (208.2) — a intenção é o próprio advogado precificando um caso, e
  o payload é só estatística agregada, nunca um lançamento individual.
  Amostra pequena (`n<3`) sinalizada sem esconder os números, mesmo
  espírito do aviso de 208.1; área sem histórico devolve `n:0` +
  mensagem (nunca 404). Frontend: novo card "Simulação de honorários vs.
  histórico real" na aba Financeiro de `/relatorios`
  (`FinanceiroCharts.tsx`), select de área reaproveitando a mesma lista
  de `processos/novo/page.tsx`, busca disparada no `onChange` (não no
  mount, diferente do `PrevisaoCaixa` que não tem parâmetro). Verificado
  via HTTP real contra Postgres real: média/mediana/mín/máx corretos
  (DESPESA, status≠PAGO, categoria≠HONORARIOS e lançamento sem
  `process_id` corretamente excluídos da amostra), filtro por
  `desfecho` reduzindo a amostra, área sem dado devolvendo mensagem,
  ADVOGADO permitido, um usuário ASSISTENTE de teste bloqueado com 403,
  isolamento cross-tenant confirmado (tenant demo não vê dado do tenant
  afj). Teste novo (`test_honorarios_simulacao_fase215.py`) com a mesma
  flakiness de pool asyncpg/pytest-asyncio documentada desde a Fase 199 —
  reproduzida de novo mesmo neste ambiente (cross-checada contra
  `test_crm_previsao_caixa_fase208.py`, que falha de forma idêntica),
  verificação principal via HTTP real como nas fases anteriores.
- **Fase 217** — a pedido do usuário, fora da sequência de propostas de
  evolução da Fase 209: investigação completa das APIs governamentais do
  Conecta gov.br (catálogo oficial, `gov.br/conecta/catalogo`) cruzadas
  contra o sistema, seguida da implementação da única recomendação P1.
  **Achado operacional relevante desta rodada**: `WebFetch` está
  bloqueado neste sandbox pra QUALQUER domínio externo (confirmado
  diretamente contra gov.br e até wikipedia.org, e depois de novo contra
  `brasilapi.com.br` via `curl` direto — é política de rede da sessão,
  não específica de gov.br, e não é contornável) — toda a pesquisa do
  catálogo veio de snippets de `WebSearch`, nunca de leitura direta da
  documentação oficial completa. Publicado como artefato ("Integração
  Conecta gov.br") com metodologia, tabela de priorização P0-P3 e
  descartadas, e nota explícita de confiança por item.
  - **Achado crítico não relacionado a nova integração**: o Termo de Uso
    da API Pública do CNJ DataJud (já em produção desde antes desta
    sessão, `backend/app/integrations/tribunais/cnj.py`) parece vedar
    "explorar comercialmente a API" — o AFJ é um produto comercial. Não
    resolvido nesta fase (decisão jurídica, fora do alcance de código) —
    registrado como pendência abaixo, mesmo padrão da retenção de
    auditoria (Fase 148).
  - **GOV-001 verificado e fechado nesta mesma fase** (checagem barata,
    sem mudança de código): `integrations/dje/comunica.py` bate
    `https://comunicaapi.pje.jus.br/api/v1/comunicacao` — API REST/JSON
    real, não raspagem de HTML — confirma que essa integração já
    existente usa um canal mais legítimo do que o artefato havia
    hipotetizado como incerto.
  - **Implementado — SERPRO CPF/CNPJ (única P1 do relatório)**: novo
    `GET/POST` não, só `POST /clients/validar-documento` (gate
    `get_current_user`, mesmo nível do resto de `clients.py`) chama
    `integrations/serpro/consulta_cpf_cnpj.py` (REST puro via httpx, sem
    SDK, OAuth2 client_credentials com token cacheado — mesmo idioma de
    `_vertex_access_token`, Fase 195) e grava auditoria em
    `GovRegistryLookup` (tabela nova, `documento_consultado` criptografado
    com o mesmo mecanismo de `Client.cpf`/`cnpj`). Fail-soft via
    `CircuitBreaker(name="serpro")` — sem `SERPRO_API_CONSUMER_KEY`
    configurada (é o caso de todo ambiente até o usuário contratar a Loja
    SERPRO), a validação devolve `valido: None` + mensagem, HTTP 200,
    nunca bloqueia o cadastro do cliente. Base URLs (`config.py`) apontam
    pro modo trial/sandbox do SERPRO por padrão, não produção.
  - **Bônus — busca de mais APIs públicas** (pedido explícito do usuário,
    "sempre que possível"): `Client.endereco_json` nunca teve autofill por
    CEP em lugar nenhum do frontend (confirmado por grep, zero
    ocorrências) — novo `POST /clients/consultar-cep` via
    `integrations/publicas/cep_lookup.py`, usando BrasilAPI
    (`brasilapi.com.br`, gratuita, sem credencial, agrega Correios/ViaCEP/
    WideNet com fallback). Deliberadamente em pasta separada de
    `integrations/serpro/` e rotulada na UI ("via BrasilAPI, fonte pública
    não-governamental") — não é canal oficial de governo, só atende ao
    pedido de "API pública que melhore o sistema" com atrito zero (sem
    contrato, sem credencial). Sem linha de auditoria (não é consulta de
    identidade pessoal).
  - Frontend (`clientes/page.tsx`): primeiro `onBlur` do arquivo — CPF/CNPJ
    mostram sugestão (nome/situação cadastral) abaixo do campo sem nunca
    travar o submit; CEP autopreenche logradouro/bairro/cidade/UF sem
    sobrescrever o que o usuário já digitou manualmente.
  - Verificado via HTTP real contra Postgres real: tabela `gov_registry_
    lookups` criada corretamente no boot (`create_all`, sem `ALTER TABLE`
    necessário — tabela nova); fluxo de sucesso (SERPRO monkeypatchado)
    grava auditoria com documento criptografado (não plaintext) e resumo
    legível; indisponibilidade (sem credencial configurada) devolve
    sempre 200 com `valido: None`, nunca 500; isolamento cross-tenant do
    log de auditoria. **Achado do próprio ambiente de teste**: o proxy de
    rede deste sandbox bloqueia egress pra `brasilapi.com.br` também (não
    só gov.br/wikipedia) — confirmado com `curl` direto retornando `403`
    no túnel — então a consulta de CEP real não pôde ser validada fim-a-
    fim nesta sessão (só o caminho fail-soft, que funcionou corretamente);
    Railway (produção) tem egress irrestrito, deve funcionar normalmente,
    mas vale um smoke-test real assim que deployado. Teste novo
    (`test_client_document_validation_fase217.py`) com a mesma flakiness
    de pool asyncpg/pytest-asyncio documentada desde a Fase 199 —
    reproduzida de novo mesmo neste ambiente (cross-checada contra
    `test_crm_metas_fase213.py`, que falha de forma idêntica), verificação
    principal via HTTP real/chamada direta como nas fases anteriores.
  - **Pendências explícitas, não resolvidas nesta fase** (decisão
    jurídica/comercial, fora do alcance de código): (1) ler o Termo de Uso
    completo do DataJud e decidir se o uso comercial atual precisa
    mudar; (2) obter parecer de base legal LGPD (legítimo interesse +
    teste de balanceamento documentado) antes de ativar a validação de
    CPF/CNPJ com uma credencial SERPRO real em produção; (3) contratar a
    Loja SERPRO e confirmar preço/limites por leitura direta (ficam atrás
    de login, não confirmados nesta pesquisa). Os demais itens P2 do
    relatório Conecta (Login Único gov.br, benefícios previdenciários,
    CND, Registro de Referência de Municípios) seguem como propostas não
    implementadas.
- **Fase 216** (6ª das 8 propostas de evolução da Fase 209, retomada após
  a Fase 217): playbooks de agentes por área. `strategy_agent` já
  injetava um dado próprio do escritório no prompt — taxa de êxito
  interna por área (`_historico_exito_area`, Fase 208.1). Novo model
  `AgentAreaPlaybook` (`tenant_id`+`area_direito`, unique constraint —
  1 orientação ativa por área) + `GET/POST/DELETE /playbooks`
  (`_STAFF`/`_GESTAO`, mesmo padrão de `_STAFF`/`_GESTAO` de `crm.py`,
  Fase 213) permitem que ADMIN/SOCIO/GESTOR cadastrem uma
  orientação/checklist em texto livre por área, injetada
  automaticamente sob um novo cabeçalho "ORIENTAÇÃO INTERNA DO
  ESCRITÓRIO PARA ESTA ÁREA" no prompt do `strategy_agent`, imediatamente
  ao lado (não em substituição) do bloco de histórico de êxito já
  existente. Fail-soft: sem playbook cadastrado, o agente usa uma
  mensagem de fallback e nunca quebra (`_playbook_area()`, mesmo padrão
  de `_historico_exito_area()`). Escopo deliberadamente restrito ao
  `strategy_agent` — `petition_agent`/`jurisprudence_agent`/
  `review_agent` usam `area_direito` só pra montar query de busca RAG,
  sem ponto de injeção limpo de um bloco só de texto. Frontend
  (`agentes/page.tsx`): nova seção "Playbooks por Área" entre "Disparar
  Tarefa" e o grid de agentes — select de área + textarea + lista de
  áreas já cobertas; gate próprio (`podeEditarPlaybook`, ADMIN/SOCIO/
  GESTOR) deliberadamente separado de `podePropoAgente` (assunto
  diferente — propor agente customizado). Verificado via HTTP real
  contra Postgres real: upsert (mesmo id, texto atualizado), isolamento
  cross-tenant, ADVOGADO lê mas não escreve (403 no POST). Injeção no
  prompt verificada chamando `StrategyAgent.execute()` diretamente com
  `call_claude` monkeypatchado (nunca bateu a API real da Anthropic):
  playbook configurado aparece no prompt com o texto exato semeado;
  área sem playbook usa o fallback sem quebrar o agente; os blocos de
  208.1 e 216 coexistem no mesmo prompt (nenhum clobera o outro). Testes
  novos (`test_agent_playbooks_fase216.py`,
  `test_strategy_agent_playbook_fase216.py`) com a mesma flakiness de
  pool asyncpg/pytest-asyncio documentada desde a Fase 199 — reproduzida
  de novo mesmo neste ambiente (cross-checada contra
  `test_crm_metas_fase213.py` e `test_strategy_agent_win_rate_fase208.py`,
  que falham de forma idêntica), verificação principal via HTTP
  real/chamada direta como nas fases anteriores. Limitação herdada de
  208.1: `area_direito` é texto livre sem enum — o match do playbook é
  por igualdade exata de string, mesma inconsistência pré-existente
  (case/acentuação) já presente no histórico de êxito.
- **Fase 218** — central de tarefas cross-módulo, última das 8 propostas
  de evolução da auditoria adversarial da Fase 209 (fecha a lista
  aberta desde então — todas as 8 entregues: 211-218). Achado que mudou
  o formato da feature: `frontend/src/app/(dashboard)/minha-area/
  page.tsx` já fazia ~80% do que a proposta original pedia (une prazos,
  processos e intimações via `Promise.all` + cards separados, desde
  antes desta sessão) — em vez de criar uma rota `/tarefas` nova e
  concorrente, a fase estendeu essa página já existente com as 2 fontes
  que faltavam (aprovações, notificações), sem tocar backend algum — os
  3 endpoints necessários já existiam (`GET /processes/agenda?mine=true`,
  `GET /approvals?status=PENDENTE`, `GET /notifications`). Achado
  colateral relevante: `Approval.assignee_id` é uma coluna morta, nunca
  escrita em lugar nenhum do backend — aprovações são uma caixa de
  entrada broadcast do tenant inteiro, não atribuída por usuário; o novo
  card "Aprovações pendentes" mostra por isso o mesmo dado agregado de
  `/aprovacoes` (não um filtro "minhas"), decisão deliberada em vez de
  fingir uma atribuição que não existe. Card de notificações reaproveita
  o store global já mantido fresco por `useNotifications()`
  (`(dashboard)/layout.tsx`) — sem fetch próprio — e exclui os tipos
  `PRAZO_VENCENDO`/`APROVACAO_PENDENTE` (ecos automáticos dos 2 cards já
  existentes de prazo/aprovação — sem esse filtro a mesma coisa
  apareceria 2-3x na tela; risco confirmado, não hipotético: os dois
  fluxos de disparo automático de notificação — `deadline_check.py` e
  `approval.py` — já geram exatamente esses 2 tipos hoje). Verificado
  via HTTP real contra Postgres real: `GET /approvals`/`GET
  /notifications` retornam o shape esperado; uma `Approval` e 2
  `Notification` (uma `NOVO_ANDAMENTO`, uma `PRAZO_VENCENDO`) semeadas
  diretamente no banco confirmaram que a segunda é corretamente
  excluída pelo filtro. `tsc --noEmit`/`eslint` limpos (0 warnings antes
  e depois — arquivo não tinha nenhum warning pré-existente pra
  cross-checar).
- **Fase 219** — rodada de teste geral (ambiente real: Postgres+Redis+
  Celery worker+uvicorn+frontend `npm run dev` com `API_URL` local,
  confirmado batendo no backend local via log em tempo real — não
  produção). Primeira rodada desde a Fase 209 a cobrir as Fases 210-218
  (a 209 só tinha coberto até a 208) — cada uma delas tinha sido
  verificada isoladamente no momento da implementação, nunca em
  conjunto. Reconfirmação independente: os 4 fixes da Fase 210 (índices,
  filtro `client_id` em `/financial`, `bulk-update` reescrito,
  `erase_client_data` alcançando `Opportunity`) — todos OK. Interação
  entre fases nunca testada antes: um `generate_strategy` disparado via
  HTTP real → Celery real → orquestrador real → `StrategyAgent.execute()`
  (não a chamada direta em Python que os próprios testes da Fase 216
  usavam) — confirmado que o caminho de produção completo chega até a
  injeção do playbook sem exceção, falhando só no limite esperado (401
  da Anthropic, sem chave real neste sandbox) — nunca verificado por
  esse caminho antes.
  - **Achado confirmado empiricamente (não hipótese)**: `erase_client_data`/
    `export_client_data` (`lgpd.py`) nunca alcançam `GovRegistryLookup`
    (Fase 217) — mesma classe de lacuna já fechada 2 vezes antes (Fase
    176.3 pra `ClientContact`/`ClientInteraction`, Fase 210 pra
    `Opportunity`). Reproduzido de ponta a ponta: criou cliente com CPF
    real, gerou uma consulta real (`gov_registry_lookups`), "esqueceu" o
    cliente via `DELETE /lgpd/clients/{id}/data`, e o CPF **continuou
    decifrável** (`decrypt_or_raw`) na tabela de auditoria depois do
    esquecimento. Achado mais fundo do que a hipótese original:
    `GovRegistryLookup.client_id` é uma **coluna morta** — o único
    caminho que cria linhas (`POST /clients/validar-documento`) nunca a
    preenche — então nem um filtro `WHERE client_id=` funcionaria sem
    reescrever a busca pelo padrão decifra-e-compara já usado em
    `GET /clients/match` (Fase 181). Terceira ocorrência da mesma classe
    de lacuna (176.3 → 210 → esta) e segunda ocorrência de "coluna FK
    morta, nunca escrita" nesta sessão (a primeira foi `Approval.
    assignee_id`, achada durante o planejamento da Fase 218) — padrão
    recorrente que vale a pena vigiar em toda tabela nova com `client_id`.
  - **Achado real, confirmado empiricamente**: `POST /clients/
    validar-documento` devolve 500 de forma reprodutível quando `valor`
    passa de ~100-125 caracteres — `GovRegistryLookup.documento_
    consultado` é `String(255)`, mas o valor bruto (não normalizado)
    é cifrado (Fernet, ~57 bytes + inflação base64) *antes* de qualquer
    validação de tamanho, e só depois disso o número de dígitos é
    checado (`len(numero) != 11` já teria descartado, mas tarde demais
    — o INSERT já falhou). Confirmado por busca binária ao vivo: 100
    chars → 200 OK, 130 chars → 500. Backend se recupera limpo depois
    (rollback funciona), não é um bug de sessão travada, só um 500
    garantido em qualquer input razoavelmente longo colado no campo.
  - **Achado de design, confirmado por grep**: o mesmo endpoint usa
    `encrypt(body.valor) or body.valor` — único call site de `encrypt()`
    em todo o código com fallback pra texto puro (todos os outros —
    `clients.py` linhas 116/118/281, `integration_hub.py`, `ai_oauth.py`,
    `users.py` — deixam `encrypt()` falhar como `None`, nunca caem pra
    plaintext). Não disparável nos testes feitos (a criptografia nunca
    falhou), mas é uma regressão silenciosa esperando uma condição rara
    (ex. `ENCRYPTION_KEY` ausente) pra vazar CPF/CNPJ em texto puro numa
    tabela pensada pra ser sempre cifrada.
  - **Achado de design (não urgente)**: `/clients/validar-documento` cai
    no rate-limit genérico (200 req/min por IP), não no tratamento
    especial de custo por chamada que `agents_trigger`/
    `brain_assistant`/`documents_generate` já têm — inerte hoje (SERPRO
    não configurado em lugar nenhum), mas vira ao mesmo tempo um vetor de
    abuso de custo E um oráculo de validade de CPF/CNPJ em escala assim
    que uma credencial real for configurada.
  - **Achado real, não relacionado às fases desta rodada** (pego durante
    o walkthrough Playwright da aba Gestão de `/relatorios`):
    `GestaoCharts.tsx` usa `key={a.advogado}` (nome de exibição) na
    tabela de "Produtividade por advogado" — React acusou chave
    duplicada porque o tenant `afj` deste ambiente tem 2 usuários de
    teste chamados "Administrador" e 2 chamados "Advogado" (resíduo de
    seeds antigos). O bug é real independente do resíduo: dois
    colaboradores reais com o mesmo nome completo colidiriam do mesmo
    jeito em produção — a chave deveria ser `User.id`, não `full_name`.
  - **Varredura cross-tenant dedicada nos 7 endpoints novos desde a Fase
    213** (nunca feita antes, cada endpoint só tinha sido testado
    isoladamente): `/crm/metas`, `/clients/{id}/dossie-pdf`,
    `/financial/honorarios-historico`, `/playbooks`, `/clients/
    validar-documento` (+ tabela `gov_registry_lookups`), `/clients/
    consultar-cep`, e o reuso de `/approvals`/`/notifications` em
    `/minha-area` — **todos confirmados isolados**, sem vazamento,
    testado com dois tenants reais (`afj`/`demo`) e IDs reais, não só
    leitura de código.
  - **Walkthrough real do frontend via Playwright** (bloqueio de plan
    mode em subagentes que recorreu em rodadas passadas — Fases 178/201
    — não ocorreu desta vez) cobrindo as 6 telas novas desde a Fase 211
    que nunca tinham sido percorridas visualmente: `/agentes`
    (playbooks — salva e persiste após reload), `/minha-area` (6 stat
    cards, empty states corretos), `/clientes` (CPF/CNPJ e CEP falham
    de forma graciosa sem SERPRO/egress externo configurados),
    `/clientes/funil` (widget de metas), `/relatorios` (simulação de
    honorários com dado real), `/clientes/{id}` (dossiê PDF baixa de
    verdade, PDF válido). Todas as 6 vieram limpas.
  - Segurança da integração externa nova (SERPRO/BrasilAPI, Fase 217):
    SSRF limpo, vazamento de credencial em log limpo, circuit breaker
    global consistente com o padrão já estabelecido pras outras fontes
    (não é bug novo) — os 2 achados reais (500 por tamanho de input,
    fallback plaintext) já estão registrados acima.
  - **Fora do foco desta rodada, deixado pra trás de propósito**: a
    investigação mais profunda da flakiness pytest-asyncio/asyncpg
    (causa raiz já identificada na Fase 212, fix tentado e revertido) —
    não haveria tempo pra fazer isso com o cuidado que merece nesta
    mesma rodada.
  - Nenhuma correção feita nesta fase (metodologia padrão) — decisão do
    usuário sobre quais achados viram fase nova. **Próxima rodada deve**:
    se os achados do `GovRegistryLookup`/`validar-documento` forem
    corrigidos, reconfirmar com o mesmo teste de ponta a ponta usado
    aqui (criar→consultar→esquecer→tentar decifrar); considerar se vale
    a pena um "linter" ou checklist formal pra pegar o padrão "tabela
    nova com `client_id` esquecida pelo LGPD erasure" antes de virar
    achado pela 4ª vez.
- **Fase 220** — implementação dos 4 achados confirmados na Fase 219, a
  pedido explícito do usuário ("Fase de correção").
  - **220.1 — LGPD, `GovRegistryLookup` alcançado pelo esquecimento**:
    novo helper `_lookups_do_titular()` (`lgpd.py`) decifra
    `documento_consultado` de cada linha do tenant e compara os dígitos
    normalizados contra o CPF/CNPJ do titular — mesmo caminho de
    `GET /clients/match` (Fase 181), já que `GovRegistryLookup.
    client_id` nunca é preenchido (não dá pra filtrar por FK).
    `erase_client_data` sobrescreve `documento_consultado`/
    `resultado_resumo` das linhas encontradas (mesmo espírito de
    sobrescrita in loco das Fases 176.3/210, não deleta a linha).
    `export_client_data` ganha a chave `"consultas_documentais"`. **Bug
    do próprio fix pego durante a verificação empírica**: a primeira
    versão comparava `client.cpf`/`client.cnpj` diretamente sem
    decifrar (esses campos são gravados cifrados desde a Fase 149) —
    corrigido pra `decrypt_or_raw(client.cpf)` antes de normalizar,
    achado e corrigido antes de virar bug em produção porque o teste de
    ponta a ponta (criar cliente com CPF real → consultar → esquecer →
    export) não encontrava a consulta nem antes do esquecimento.
  - **220.2/220.3 — 500 em `validar-documento` + fallback plaintext**:
    `POST /clients/validar-documento` agora normaliza e valida o
    formato (11/14 dígitos) **antes** de bater SERPRO ou gravar
    qualquer coisa — reproduzido o 500 exato achado pela Fase 219 (input
    de 200 caracteres) e confirmado que virou `200 {"valido": false,
    ...}` sem nenhuma linha nova em `gov_registry_lookups`. `encrypt()`
    agora cifra o número já normalizado (nunca mais estoura
    `String(255)`); se `encrypt()` falhar de verdade, a linha de
    auditoria é pulada (log de erro) em vez de cair pra texto puro —
    fecha o único call site do código que tinha esse fallback.
  - **220.4 — `GestaoCharts.tsx` key duplicado**: `GET /system/
    analytics/gestao` (`system.py`) passa a incluir `id` (UUID do
    usuário) em cada item de `produtividade_advogados`; a tabela de
    produtividade agora usa `key={a.id}` em vez de `key={a.advogado}`.
    Confirmado via HTTP real que o tenant de teste (2 usuários
    "Administrador") devolve `id`s únicos mesmo com nomes duplicados.
  - Verificado via HTTP real contra Postgres real (mesmo ambiente da
    própria Fase 219, reiniciado só pra carregar o código novo): os 4
    fixes reproduzidos de ponta a ponta, replicando exatamente os
    cenários que a Fase 219 usou pra confirmar cada achado. `ruff`/
    `py_compile`/`tsc --noEmit`/`eslint` limpos em todos os arquivos
    tocados. Teste novo
    (`test_lgpd_erasure_reaches_gov_registry_fase220.py`, mesmo idioma
    HTTP real de `test_lgpd_erasure_reaches_crm_fase210.py`) e um caso
    novo em `test_client_document_validation_fase217.py` — ambos batem
    na mesma flakiness de pool asyncpg/pytest-asyncio documentada desde
    a Fase 199; o teste LGPD especificamente reproduz o mesmo
    comportamento de `SKIPPED` do arquivo de controle não tocado
    (`test_lgpd_erasure_reaches_crm_fase210.py`, que usa a mesma
    fixture `client`/`auth_headers`) — confirma que não é regressão
    desta fase, é uma característica pré-existente dessa fixture neste
    ambiente. Verificação principal via HTTP real, como em toda fase
    recente.
- **Fase 221** — reformulação da tela de cadastro de cliente
  (`/clientes`), a pedido do usuário ("reformule, teste e corrija"),
  escopo confirmado explicitamente como estrutura+bugs, sem mudar a
  identidade visual.
  - **Achado mais grave, encontrado numa leitura completa do arquivo
    antes de planejar**: o modal de exclusão da lista prometia
    "anonimização conforme a LGPD", mas `excluirCliente()` chamava
    `DELETE /clients/{id}` — que só limpa `cpf`/`cnpj`/`email`/
    `telefone`/`whatsapp` e marca `INATIVO`, deixando `nome_completo`
    (o nome real da pessoa), `observacoes`, `ClientContact`,
    `ClientInteraction`, `Opportunity` e a auditoria SERPRO
    (`GovRegistryLookup`, Fase 217) intactos — desalinhado com o texto
    do próprio modal e com a página de detalhe do cliente
    (`clientes/[id]/page.tsx::apagarDados()`), que já chamava o
    endpoint certo (`DELETE /lgpd/clients/{id}/data`, corrigido a fundo
    na Fase 220) desde antes. Corrigido: a lista agora aciona o mesmo
    endpoint da página de detalhe. Botão de excluir ganhou gate
    `ADMIN`-only no frontend (antes não tinha gate nenhum, e um
    não-ADMIN clicando batia num 403 silencioso — o endpoint real exige
    `require_role("ADMIN")` puro).
  - Mesma classe de bug (falha silenciosa) em `salvarCliente()` (criar)
    e `excluirCliente()`: nenhum dos dois tratava erro — agora os dois
    seguem o padrão já certo de `salvarEdicao()` (`try/catch` +
    `toast.error`). Os 3 fluxos ganharam proteção contra duplo clique
    (`salvando`, desabilita o botão + texto "Salvando.../Removendo...").
  - `validarDocumento()` desistia antes de perguntar ao backend quando
    o CPF/CNPJ tinha menos de 11 dígitos — a mensagem "Formato de
    CPF/CNPJ inválido." que o backend já devolve desde a Fase 220 nunca
    chegava a aparecer. Corrigido pra sempre consultar (exceto campo
    vazio) e mostrar `data.mensagem` em qualquer caso não-`válido`.
  - Novo `frontend/src/components/clientes/ClienteFormFields.tsx` —
    componente compartilhado que elimina ~150 linhas de JSX quase
    idêntico entre os modais "Novo Cliente" e "Editar Cliente"
    (tipo/razão social/CPF-CNPJ com validação SERPRO, endereço com
    autofill de CEP, status, consentimento LGPD). Campo "Origem", que
    só existia no modal de criar sem motivo aparente, passou a existir
    também no de editar (ganho natural de unificar, não exigiu lógica
    nova). Modal de editar passou a usar `<form onSubmit>` (antes era
    só um botão com `onClick`) — Enter agora funciona igual ao de criar.
  - Verificado via navegador real (Playwright, Chromium do sandbox,
    `npm run dev` com `API_URL` local já confirmado batendo no backend
    local): criar cliente com sucesso fecha o modal; CPF de 3 dígitos no
    blur mostra "Formato de CPF/CNPJ inválido."; campo Origem presente
    no modal de editar; ADMIN vê e consegue clicar "Remover", a
    requisição capturada via `page.on("request")` confirma que bate em
    `/lgpd/clients/{id}/data` (não mais `/clients/{id}`), e consulta
    direta ao Postgres depois confirma `nome_completo` virou
    `[ANONIMIZADO-...]` — a mesma prova de esquecimento completo já
    usada na Fase 220; ADVOGADO (não-ADMIN) não vê nenhum botão de
    remover na lista, mas continua vendo o de editar. `tsc --noEmit`/
    `eslint` limpos no arquivo principal e no componente novo (1
    warning pré-existente de `exhaustive-deps`, já documentado desde
    fases anteriores, não novo desta fase).
- **Fase 222** — usuário reportou com 2 screenshots que a Cliente 360 de
  um cliente real ("Marcelo Augusto Alves Freire") mostrava "Processos
  Vinculados (0)", apesar de um processo real
  (`5008963-31.2025.8.01.0001`) já listar esse mesmo cliente como parte
  vinculada em "Partes". Investigado (Explore agent + leitura direta de
  código) e confirmado como bug real de sincronização, não erro visual:
  `LegalProcess.client_id` (usado por `GET /processes?client_id=`, que
  alimenta o card da Cliente 360, o score de saúde — 207.1 —, a
  timeline — 211 — e o dossiê PDF — 214) e `ProcessParty.client_id`
  (Fase 179, setado ao vincular manualmente uma parte a um cliente já
  cadastrado) são 2 FKs independentes que nada no código sincroniza.
  `LegalProcess.client_id` nunca é populado pela importação automática
  por OAB (`oab_capture.py`, o caminho mais comum de entrada de
  processo no sistema) nem por nenhuma tela depois que o processo já
  existe — então qualquer processo importado por OAB cujo único vínculo
  a um cliente seja uma parte manual nunca aparecia como "vinculado" em
  lugar nenhum. Grep de todo `LegalProcess.client_id ==` no backend
  achou mais 3 call sites com o mesmo filtro estreito além do já
  descrito (`clients.py`: health-score, timeline, dossiê) e mais 3 no
  portal do cliente externo (`portal.py`: resumo, lista de processos,
  detalhe de 1 processo) — mesma causa raiz, não bugs separados (mesma
  classe de "dado alcançável por um caminho mas invisível pelo caminho
  que a tela consulta" já vista 3x nesta sessão pra LGPD erasure, Fase
  176.3→210→220). Fix: novo `client_linked_processes_filter()`
  (`backend/app/models/process.py`) — condição SQLAlchemy única
  (`LegalProcess.client_id == X OR EXISTS(ProcessParty vinculada a X)`,
  via `exists()` correlacionado, não `join`, pra nunca duplicar a linha
  do processo quando 2+ partes apontam pro mesmo cliente) — reaproveitada
  nos 7 call sites (`processes.py`, `clients.py` × 3, `portal.py` × 3)
  em vez de 7 patches inline independentes. Nenhuma mudança de
  frontend — os 7 endpoints já devolviam pro frontend o formato certo,
  só não encontravam a linha. Verificado via HTTP real contra Postgres
  real, reproduzindo o cenário exato do usuário (processo `fonte`
  implícita OAB, `client_id=NULL`, parte REU vinculada manualmente
  depois): antes do fix `GET /processes?client_id=` devolvia `[]`,
  depois devolve o processo; regressão confirmada (processo com
  `client_id` direto, sem parte, continua aparecendo); sem duplicata
  confirmada (2 partes vinculadas ao mesmo cliente → processo aparece
  1x só); health-score/timeline/dossiê-pdf confirmados refletindo o
  processo agora alcançável. Teste novo
  (`test_client_linked_processes_fase222.py`) reproduz os mesmos 4
  cenários via `AsyncClient` HTTP real — bate na mesma flakiness de
  pool asyncpg/pytest-asyncio documentada desde a Fase 199 quando
  rodada em lote; **achado adicional, pré-existente e fora do escopo
  desta fase**: `tests/conftest.py::test_user` usa o e-mail
  `admin@afjadvogados.com.br` (com `.br`), mas o seed real
  (`app/core/events.py`) só cria `admin@afj.com.br` e
  `admin@afjadvogados.com` (sem `.br`) — todo teste que dependa da
  fixture `auth_headers` pula com "Login failed" neste ambiente,
  independente da fase; não corrigido aqui (fora do escopo do bug
  reportado), registrado pra a próxima rodada de teste geral decidir se
  vale a pena corrigir o e-mail do fixture. Verificação principal desta
  fase foi HTTP real (curl) contra o backend local, como em toda fase
  recente desta sessão.
- **Fase 223** — usuário pediu "elabore uma nova versão do saúde do
  sistema e analise, valide e corrija cada módulo presente. No modo
  cérebro, valide e corrija cada módulo presente." Investigação
  (Explore + leitura direta) confirmou que as 2 telas já existiam e
  eram maduras — não era construir do zero.
  - **Parte A — `/admin/health` ("Saúde do Sistema")**: dos 13 cards de
    módulo, 5 já eram reais (postgresql/redis/qdrant/anthropic/
    datajud) mas **6 eram hardcoded pra sempre dizer "funcionando"**
    sem checar nada — `publicacoes`, `auth`, `auditoria`,
    `notificacoes`, `storage` e `backup`. `backup` já era honesto
    (`"planejado"`, confirmado por grep que não existe NENHUM
    mecanismo de backup no código — não mexido). Os outros 5 ganharam
    checagem real em `health_detailed()`
    (`backend/app/api/v1/system.py`): `auth` — round-trip de JWT
    (`create_access_token`/`decode_access_token`) usando o
    `SECRET_KEY` ativo; `storage` — reaproveita
    `object_storage.is_configured()` (Fase 141) direto; `notificacoes`
    — mesmo gate que `webpush.py` já usa (`PUSH_ENABLED` + VAPID
    keys); `publicacoes` — última linha real de `SyncRun` com
    `fonte="comunica"`; `auditoria` — última linha real de
    `AuditLog.timestamp`. Frontend (`admin/health/page.tsx`) trocou os
    5 `getStatus` hardcoded por leitura real dos campos novos, mesmo
    padrão dos 5 já reais. Também corrigido o "Progresso do Projeto"
    (`PHASES`), que estava congelado ~80 Fases atrás e marcava
    "Integrações externas" como pendente — confirmado por grep que
    gateway de pagamento (Stripe/Mercado Pago), assinatura digital
    (Clicksign) e WhatsApp (Meta Cloud API, 3 call sites reais em
    produção: `dje_monitor.py`, `invoices.py`,
    `deadline_check.py`) já estão implementados (só a ativação depende
    de credencial do escritório) — linha corrigida pra `done: true`, e
    3 linhas novas na mesma granularidade grossa das existentes
    resumindo o que foi entregue desde então (Ética & Integridade —
    Fase 189; ambiente de demonstração — Fases 199-200; integrações
    governamentais SERPRO/PDPJ/BrasilAPI — Fase 217).
    `COMPLETION_PERCENT` (lista mantida à mão, sem fonte de dado
    dinâmica barata e óbvia pra substituir) passou a refletir 100% com
    o dado corrigido — mantido como está, não construído um mecanismo
    dinâmico novo.
  - **Parte B — "Modo Cérebro" (`/admin/cerebro`)**: a aba Mapa já era
    um grafo real introspectado (não hardcoded) — "cada módulo
    presente" aqui foi interpretado como os nós reais do Mapa
    (agentes/providers/fontes/infra), não as outras 7 abas (que são
    visualizações do mesmo dado). Validação roteirizada contra o
    sistema rodando de verdade: as 20 entradas de
    `resolve_agent_class` importam sem erro; `integration_hub.
    list_status()` roda limpo pra um tenant real cobrindo os 10
    providers registrados; as 2 fontes de captura (`comunica`,
    `datajud`) têm `nome`/`capabilities` válidos. **Nenhum bug
    encontrado** — os 3 pontos vieram limpos, nenhuma correção
    necessária nesta parte. `POST /system/brain/insights`
    (auto-análise por IA) testado contra o sistema real — falha
    graciosamente (200, `ok:false`) por falta de credencial Anthropic
    neste sandbox, comportamento fail-soft esperado (mesmo padrão da
    Fase 204.A), não um bug.
  - Verificado via HTTP real + Postgres real (Postgres/Redis/uvicorn
    reiniciados neste container, que tinha sido reciclado): os 5
    módulos corrigidos testados com o padrão antes/depois — `auth`
    forçado a falhar de verdade com `JWT_ALGORITHM` inválido
    (confirmado via chamada direta às primitivas, já que um
    `SECRET_KEY` vazio mas autoconsistente não quebra o round-trip —
    limitação inerente ao desenho, não um bug); `storage`/
    `notificacoes` alternando entre não configurado/configurado via
    env vars reais; `publicacoes` alternando ERRO/OK via `SyncRun`
    inserido direto no Postgres. Walkthrough real via Playwright
    (Chromium do sandbox) em `/admin/health` (13 cards com status
    reais, roadmap com as 4 linhas corrigidas/novas, 100%) e
    `/admin/cerebro` → Mapa (grafo carregando sem erro de console,
    42 nós/42 arestas, nenhuma aresta órfã) como ADMIN e SUPERADMIN
    reais. `ruff check`/`py_compile` no backend tocado; `tsc --noEmit`/
    `eslint` no frontend tocado (precisou de uma anotação de tipo
    explícita em `PHASES` depois de remover o único `active: true` da
    lista, senão o TS inferia um tipo sem o campo `active` e quebrava
    a renderização do roadmap — pego pelo próprio `tsc`, corrigido
    antes do commit).
- **Fase 224** — usuário pediu pra verificar se era viável juntar
  "Config. Jurídica" e "Personalização" dentro de "Configurações", de
  forma remodelada. Investigação (3 Explore agents, cada um lendo uma
  página inteira) confirmou viabilidade — mudança 100% de frontend,
  todo endpoint que a página fundida chama já existia e já estava
  corretamente gateado no backend. O problema real era de information
  architecture, não técnico: `/configuracoes` era aberta a todo papel
  (`roles: null`) enquanto `/admin/personalizacao` e `/admin/juridico`
  eram só ADMIN/SUPERADMIN — fundir exigia 2 zonas internas, não uma
  simples concatenação de abas. **Achado real confirmado durante a
  investigação**: a aba "Aparência" de `/configuracoes` já era
  visível a todo papel mas gravava em `PUT /tenant/branding`
  (`require_role("ADMIN")` no backend) — um usuário sem esse papel
  preenchia o formulário e o save dava 403 silencioso; também era uma
  versão capenga (3 campos) do que a Personalização já fazia melhor
  (8 campos, preview ao vivo). Implementação: `/configuracoes` agora
  tem 2 zonas selecionáveis por pill — "Pessoal" (Perfil/Notificações/
  Segurança, todo mundo, aba Aparência antiga removida — bug fechado)
  e "Escritório & Jurídico" (só ADMIN/SUPERADMIN, mesmo cálculo de
  `admin/layout.tsx`) com as 8 abas de Personalização inalteradas +
  1 aba nova "Jurídico" com os 3 cards de Config. Jurídica como
  estavam. Padrão de estado de aba (URL `?zona=`/`?aba=` → localStorage
  → default) espelha `admin/cerebro/page.tsx`, aplicado numa camada a
  mais (zona + aba dentro da zona). Novo
  `frontend/src/components/configuracoes/` (`PersonalZone.tsx`,
  `EscritorioZone.tsx`, `JuridicoTab.tsx`) — conteúdo/lógica das abas
  extraído sem mudança das 2 páginas antigas, que foram apagadas.
  `nav.ts` perde as 2 entradas antigas; `next.config.js` ganha
  `redirects()` (307, mecanismo novo pro projeto — não havia nenhum
  antes) de `/admin/personalizacao`/`/admin/juridico` pra
  `/configuracoes?zona=admin&aba=...`, só pra bookmark/histórico do
  navegador (grep confirmou zero links internos apontando pras rotas
  antigas). Verificado via Playwright real contra backend real: ADMIN
  vê as 2 zonas, clica nas 9 abas sem erro de console, aba Jurídico
  com os 3 cards presentes, preview ao vivo funcionando; não-admin só
  vê a zona Pessoal e, forçando `?zona=admin` na URL, cai de volta pra
  Pessoal sem vazar UI administrativa; os 2 redirects testados de
  ponta a ponta (URL antiga → zona+aba certas); sidebar/busca
  confirmadas sem "Personalização"/"Config. Jurídica". **Achado
  colateral, não corrigido nesta fase**: um teste de round-trip
  (salvar nome do sistema na aba Aparência → recarregar a página)
  mostrou o campo voltando com um valor desatualizado — reproduzido
  também contra a página `admin/personalizacao` ORIGINAL (antes desta
  fase, via `git stash`), confirmando que é uma race pré-existente
  entre a hidratação assíncrona do tema (`fetchAndApplyTheme()` no
  layout) e o `useState(theme.appName)` local de cada aba, não uma
  regressão desta fusão — o backend persiste corretamente (confirmado
  via `GET /tenant/theme` direto), só a UI de uma aba específica não
  se resincroniza sozinha após o fetch assíncrono resolver. Registrado
  aqui pra não se perder; não investigado a fundo por estar fora do
  escopo do pedido (fusão de páginas, não correção de bug de tema).
- **Fase 225** — última das 16 propostas de evolução da Fase 203 ainda
  não implementada (guardada por último desde a Fase 206 por "tocar o
  orchestrator"): agente customizado como passo de chain. Antes, um
  agente customizado só rodava sozinho (`run_custom_agent`, chain de 1
  passo). Investigação (leitura direta de `router.py`/`chain_resume.py`/
  `agent_tasks.py`/`chain_projectors.py`) achou o fato que decidiu todo
  o design: nenhum dos 3 pontos que retomam uma chain (aprovação HITL,
  crash/retry de worker) guarda "a forma da chain" em lugar nenhum —
  todos recalculam `get_chain(task_type, input_data)` do zero a partir
  do payload ORIGINAL do disparo (`agent_run.input_data` persistido, ou
  os argumentos originais da task Celery). Ou seja, qualquer campo no
  payload original sobrevive intacto a qualquer resume, sem precisar
  mexer em `execute_chain_step`/`resolve_agent_class`/persistência de
  `AgentStep`. Escopo definido a partir disso: **anexar 1 agente
  customizado já aprovado ao FINAL** de uma das 3 chains existentes
  (`new_process_intake`, `generate_and_review_petition`,
  `full_contract_flow`) via `custom_agent_id` no payload do disparo —
  não um chain-builder genérico (não existe UI de composição de chain
  nenhuma hoje, e `CustomAgent` já é platform-wide, não por tenant).
  - `router.py::get_chain()` ganhou `CUSTOM_AGENT_APPENDABLE_CHAINS`
    (allowlist explícito) e anexa `"custom_agent"` no final SE
    `custom_agent_id` estiver no payload E o `task_type` estiver na
    allowlist — as 3 chains sem esse campo ficam byte-idênticas.
  - `chain_projectors.py` ganhou `_any_to_custom_agent()` — 1 fallback
    genérico (não pontes por par, já que o passo customizado pode vir
    de qualquer uma das 3 chains) que tenta as chaves de texto mais
    prováveis da saída do passo anterior; o `descricao` explícito do
    usuário no disparo original sempre vence por cima (invariante já
    existente do projeto).
  - `CustomAgent`/`CustomAgentVersion` ganharam
    `requires_human_approval: bool` (migração pelo padrão já
    estabelecido — `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
    idempotente em `events.py`, não Alembic). `CustomAgentExecutor`
    seta `self.requires_human_approval` como atributo de instância
    dentro de `execute()` — `BaseAgent.run()` já lê isso DEPOIS de
    `execute()` retornar, então o gate HITL genérico (o mesmo dos 19
    agentes nativos) passa a funcionar pro passo customizado sem
    nenhuma mudança em `agent.py`. `POST /custom-agents/{id}/resolve`
    e `PATCH /custom-agents/{id}` (SUPERADMIN-only) controlam o campo.
  - Frontend: `/agentes` ganha um `<select>` ("Anexar agente
    customizado ao final") quando o `task_type` escolhido é uma chain,
    reaproveitando a lista de customAgents já buscada pra
    `CustomAgentCard`; `BrainCustomAgents.tsx` ganha um checkbox no
    form de edição já existente pro campo `requires_human_approval`.
  - Verificado com um script real (não só pytest — Postgres real,
    orquestrador real, `call_claude` monkeypatchado nos módulos
    relevantes, `review_agent.execute()` inteiro substituído por um
    mock simples já que sua lógica interna de 4 sub-chamadas paralelas
    é ortogonal a esta fase): (a) regressão — `full_contract_flow` sem
    `custom_agent_id` continua exatamente igual (2 passos, mesmo
    comportamento de sempre); (b) com `custom_agent_id`, a chain vira 3
    passos e completa em SUCCESS, com o passo customizado recebendo
    `descricao` via o fallback genérico do projector; (c) com
    `requires_human_approval=True` no agente customizado, a chain para
    de novo APÓS o passo customizado (2º gate HITL na mesma chain,
    `Approval` real com `tipo=CUSTOM_AGENT_REVIEW`), e aprovar essa
    2ª Approval finaliza a run em SUCCESS; (d) **o teste mais
    importante** — chamando `_resume_chain_from_steps` diretamente com
    2 `AgentStep`s já persistidos (simulando um worker que morreu
    depois de terminar os 2 primeiros passos), confirmado que NÃO
    reexecuta os passos já feitos, só roda o passo customizado que
    faltava, com `custom_agent_id` ainda resolvendo corretamente — a
    premissa central do design (payload original sobrevive a qualquer
    resume) se confirmou empiricamente, não só por leitura de código.
    Frontend verificado via Playwright real: o `<select>` novo aparece
    só pra `task_type` de chain e o POST real de `/agents/trigger`
    inclui `custom_agent_id`; o checkbox novo faz round-trip real via
    `PATCH /custom-agents/{id}`.
  - Fora de escopo, documentado como P2 no código: forma de passo
    parametrizada (pra 2+ agentes customizados ou posição não-final na
    mesma chain), chain-builder genérico (precisaria de uma tabela de
    definição de chain de verdade, já que `TASK_ROUTE_MAP` sendo só
    código é incompatível com chain autorada pelo usuário), e nós por
    `CustomAgent` individual no Mapa do Cérebro (cosmético).
- **Fase 226** — usuário reportou "o assistente do Cérebro não está
  funcionando" e pediu pra verificar se ele usa a IA configurada no
  sistema. Confirmado: `brain_assistant.py::responder_stream()`
  chamava `call_llm_stream()` **direto**, sem nunca entrar em
  `user_ai_creds()` — a mesma classe exata de bug já corrigida uma vez
  na Fase 204.A para `brain_insights.py` (achado então: "ao contrário
  de toda outra rota disparadora de IA do sistema, esta não tinha
  fallback pra IA própria do usuário"), agora reaberta num ponto
  diferente do código. Confirmado via leitura direta que
  `call_llm_stream()` já lê `ai_creds_ctx.get()` pra resolver
  BYOK — só que esse contextvar nunca era setado, porque só
  `user_ai_creds()` o seta e o Assistente nunca chamava essa função.
  Na prática: mesmo um SUPERADMIN com IA própria configurada em
  "Minha IA" nunca conseguia usá-la no Assistente — dependia 100% da
  `ANTHROPIC_API_KEY`/`GEMINI_API_KEY` central do servidor.
  - Fix: `responder_stream()` ganhou parâmetro `user_id` (passado pelo
    endpoint, `current_user.id`) e a chamada a `call_llm_stream()`
    agora roda dentro de `async with user_ai_creds(creds_db, user_id,
    "brain_assistant")`, mesmo mecanismo usado por
    generate_petition/review_document/manage_contract/gerar_insights.
  - **Achado adicional do próprio fix, corrigido antes de virar bug em
    produção**: `user_ai_creds()` precisa consultar `AIProviderConfig`
    no banco — mas a `db` que o endpoint (`system.py::brain_assistant`)
    passa pra `responder_stream()` vem de `Depends(get_db)`, e como a
    resposta é um `StreamingResponse`, o FastAPI fecha essa sessão
    assim que a função do endpoint retorna, ANTES do generator
    (`responder_stream`) começar a ser consumido de fato — mesma
    armadilha que o próprio arquivo já documentava pra persistir a
    resposta do assistente ("sessão nova — o generator roda após o
    request"). Até este fix isso nunca tinha se manifestado porque
    nenhum código dentro do generator de fato consultava `db`
    (`_infra_resumo`/`_rag_docs` recebem `db` mas nunca fazem query
    com ela). Corrigido abrindo uma sessão própria
    (`AsyncSessionLocal()`) só pra resolver as credenciais, em vez de
    reaproveitar a `db` potencialmente já fechada.
  - Verificado: (a) script direto (Postgres real, `call_llm_stream`
    monkeypatchado só pra reportar o que `ai_creds_ctx.get()` resolveu)
    confirma que um SUPERADMIN de teste com BYOK cadastrado agora tem
    sua própria chave usada dentro do Assistente — antes do fix isso
    era estruturalmente impossível; (b) HTTP real contra o endpoint SSE
    (`POST /system/brain/assistant`) como SUPERADMIN real: sem crash de
    sessão fechada, resposta streamada corretamente, erro real da API
    Anthropic (401, chave central deste sandbox é placeholder — mesma
    limitação de ambiente já documentada em toda fase anterior) chega
    de volta ao cliente via SSE em vez de travar; persistência de
    conversa/mensagens em `assistant_conversations`/`assistant_messages`
    confirmada intacta (sem regressão).
  - **Varredura extra** (motivada pela nota acima, feita na mesma
    fase): grep de todo `call_llm`/`call_llm_stream`/`call_claude`
    chamado direto no backend. Os 19 agentes nativos já estão cobertos
    (todo `agent.run()` já roda dentro de `user_ai_creds()` no
    orquestrador, `execute_chain_step`); `documents.py` (3 call sites)
    já estava correto; `users.py` (teste de conexão de uma config
    específica) usa `ai_creds_ctx.set()` direto de propósito, correto
    por desenho; `jurisprudencia_sync.py` é uma task Celery Beat
    genuinamente sem usuário pra atribuir BYOK (fonte pública, sem
    tenant) — chave central é o design certo, não um bug. **Achou uma
    3ª ocorrência real**: `services/prazo_sugestao.py::sugerir_prazo()`
    (usado por `POST /publicacoes/{id}/sugestao-prazo`, o botão de
    sugestão de IA no modal de triagem) também chamava `call_llm`
    direto — `db`/`current_user` já estavam disponíveis no endpoint
    (usados ali mesmo pra `enforce_budget`), só nunca eram repassados
    pra dentro da função. Corrigido com o mesmo padrão (`db`/`user_id`
    novos parâmetros, chamada envolvida em `user_ai_creds(db, user_id,
    "sugestao_prazo")`) — aqui sem precisar de sessão própria como o
    Assistente, já que `/sugestao-prazo` é uma resposta JSON normal,
    não um `StreamingResponse` (a `db` de `Depends(get_db)` continua
    válida durante toda a função). 3 testes existentes
    (`test_prazo_sugestao.py`) atualizados pra nova assinatura — os 10
    testes do arquivo passam limpos isolados. Verificado com o mesmo
    script direto (Postgres real, `call_llm` monkeypatchado só pra
    reportar `ai_creds_ctx.get()`): um usuário de teste com BYOK
    cadastrado tem a própria chave usada dentro de `sugerir_prazo()`.
    Nenhuma 4ª ocorrência encontrada na varredura.
- **Fase 227** — usuário reportou "o Celery não funciona" e pediu pra
  investigar, validar e corrigir. Investigação (código do Celery em si +
  boot de produção, sem acesso a log/dashboard do Railway nesta sessão):
  **o app Celery está correto** — confirmado importando
  `app.workers.worker` e forçando o carregamento de todos os 13 módulos
  de `include=[...]` via `celery_app.loader.import_default_modules()`,
  zero erro, as 14 tasks (12 do `beat_schedule` + `agent_tasks.run_agent`
  + `ocr_tasks.ocr_document`) registram normalmente. **A causa raiz real
  está em `backend/start.sh` + `railway.toml`** (deploy Railway de
  serviço único, web+worker no mesmo container, débito já reconhecido no
  próprio comentário do script): o Celery subia em background (`&`) sem
  PID guardado/monitorado, e o script terminava com `exec uvicorn ...`
  — o `exec` troca o processo do shell pelo do uvicorn, então nada mais
  observava o Celery depois disso. `railway.toml` só tem
  `healthcheckPath = "/ping"` (endpoint HTTP do uvicorn) +
  `restartPolicyType = "ON_FAILURE"` — o Railway só reinicia o container
  se o healthcheck HTTP falhar ou o processo principal (uvicorn) morrer;
  **zero visibilidade sobre o Celery**. Se o Celery caísse por qualquer
  motivo depois do boot (blip de reconexão do Redis, OOM por
  concorrência com o uvicorn no mesmo container, exceção não tratada no
  bootstrap), o site continuava respondendo normalmente e o Railway
  nunca percebia nada errado — as 12 tarefas agendadas (agentes de IA,
  OCR, alertas de prazo, capturas periódicas) ficavam mortas
  silenciosamente até o próximo deploy manual. Bate exatamente com o
  sintoma relatado, sem nenhum erro visível na aplicação web.
  **Nota explícita**: esta causa raiz é uma hipótese bem fundamentada a
  partir da leitura do código/config de deploy, não uma confirmação
  direta via log/dashboard do Railway (esta sessão não tem esse acesso).
  - **Fix**: `backend/start.sh` ganhou um watchdog POSIX `sh` (sem
    bashismos — produção roda em `dash`, confirmado via `/bin/sh`).
    Celery e uvicorn agora sobem os dois em background com PID guardado
    (`CELERY_PID`/`UVICORN_PID`); um `trap` em `TERM`/`INT` propaga o
    sinal pros 2 filhos e espera (preserva o graceful shutdown que o
    `exec` garantia de graça antes — sem isso um redeploy do Railway
    mataria os filhos sem aviso); um loop de watchdog (`kill -0` a cada
    10s) religa só o Celery se ele morrer (zero downtime do site) e
    encerra o script inteiro com `exit 1` se o uvicorn morrer, deixando
    o `restartPolicyType=ON_FAILURE` já configurado reiniciar o
    container inteiro — mesmo comportamento de hoje pro caso do uvicorn.
    Estado ideal de longo prazo (serviços `worker`/`scheduler` dedicados
    no Railway, separando web de background de vez) segue fora do
    alcance desta sessão (exige acesso ao dashboard do Railway) —
    documentado no próprio script.
  - Verificado com Postgres+Redis reais, `sh start.sh` rodando de
    verdade (não só leitura de código): (1) os 2 processos sobem
    normalmente, Celery registra as 12 tasks periódicas + conecta no
    Redis, uvicorn sobe e fica pronto; (2) `kill -9` só no processo
    principal do Celery — watchdog detecta a queda (log
    `[AFJ][WARN] Processo Celery (pid ...) morreu — religando…`) e
    relança um Celery novo em ~4s, sem tocar uvicorn nem o script; (3)
    `kill -9` só no uvicorn — script detecta em ~7s
    (`[AFJ][FATAL] ...— encerrando pra forçar restart do container.`) e
    sai com código 1 (confirmado explicitamente capturando `$?` do
    processo), deixando o restart pro Railway; (4) `SIGTERM` no processo
    do script — trap dispara na hora (`[AFJ] Sinal de encerramento
    recebido — propagando…`), Celery faz "Warm shutdown", uvicorn
    "Shutting down"/"Application shutdown complete", e todo o processo
    termina de forma limpa em ~7-8s (nenhum órfão, nenhum travamento —
    uma suspeita inicial de que o SIGTERM não estava propagando se
    mostrou, ao reexaminar com uma janela de espera maior, apenas um
    teste anterior que checou cedo demais, não um bug real).
    `shellcheck` não disponível neste sandbox — revisão manual cuidadosa
    do script POSIX aplicada no lugar. **Limitação conhecida, não
    corrigida nesta fase** (fora do escopo do sintoma reportado): um
    `kill -9` no processo principal do Celery pode deixar processos
    filhos já forkados (pool de workers) órfãos, sem serem religados
    nem sinalizados pelo trap (que só conhece o PID principal capturado
    em `$!`) — observado incidentalmente durante o teste (2), não
    investigado a fundo por ser um modo de crash atípico (o caso comum
    é OOM-killer, que mata o cgroup inteiro, ou exceção não tratada, que
    tipicamente encerra o pool de forma mais limpa).
- **Fase 228** — rodada de teste geral, escolhida pelo usuário como "próxima
  fase" depois do fix do Celery (Fase 227). Ambiente real (Postgres+Redis+
  Celery worker+uvicorn+frontend `npm run dev` com `API_URL` local)
  subido de verdade. Cobriu, pela primeira vez numa única rodada, as Fases
  220-227 inteiras (nenhuma tinha passado por teste geral desde a própria
  implementação) — reconfirmação independente via HTTP real de 220
  (LGPD→GovRegistryLookup, 500 de input longo, fallback plaintext, key
  duplicado), 221 (rota LGPD no delete da lista de clientes — Playwright
  confirmou a requisição real batendo em `/lgpd/clients/{id}/data`, com
  anonimização confirmada direto no Postgres), 222
  (`client_linked_processes_filter`, os 7 call sites, sem regressão/
  duplicata), 223 (os 6 módulos antes hardcoded do `/admin/health`, todos
  dinâmicos de verdade), 224 (fusão de Configurações, zonas/redirects
  corretos por papel), 226 (BYOK do Assistente do Cérebro e da sugestão de
  prazo — desta vez provado com uma resposta 401 REAL da Anthropic,
  confirmando que a chave BYOK plantada foi genuinamente usada ponta a
  ponta, não só um mock). 227 já tinha sido verificado na própria fase.
  `tests/conftest.py::test_user` (achado pré-existente da Fase 222,
  nunca corrigido) também foi corrigido nesta rodada — tooling de teste,
  não achado de produto, por isso resolvido inline em vez de virar fase:
  o e-mail não batia com nenhum usuário ADMIN real do seed, fazendo todo
  teste dependente de `auth_headers` pular silenciosamente; confirmado
  que `POST /auth/login` agora retorna 200 em vez de skip.
  - **Frente mais funda que a Fase 225 conseguiu**: uma chain real com 3
    gates HITL em sequência (2 nativos forçados via monkeypatch de
    `requires_human_approval` + 1 `custom_agent`, a primeira vez que essa
    combinação foi exercitada) — rodada com Postgres real, cada resolução
    de Approval chamando as MESMAS funções de serviço que o endpoint HTTP
    usa (`execute_approved_action`/`resume_chain_after_approval`).
    Confirmado que a chain completa corretamente os 3 gates até SUCCESS,
    5 `AgentStep` na ordem certa, sem duplicata — a classe de bug da Fase
    183 (2º+ gate não criado) não reapareceu. **Mas achou um bug novo,
    real, no processo**: quando o gate aprovado é o ÚLTIMO passo da
    chain, o branch de retorno antecipado em
    `resume_chain_after_approval` (`app/services/chain_resume.py:65-73`)
    seta `agent_run.status = "SUCCESS"` mas NUNCA `agent_run.
    requires_approval = False` — ao contrário dos outros 2 branches de
    finalização (`_run_remaining_steps`, corrigidos desde a Fase 174.7),
    que sempre zeram os dois juntos. Resultado: o run fica com status
    SUCCESS mas `requires_approval` travado em `True` pra sempre — em
    qualquer UI/consulta que filtre "precisa de atenção" por esse campo,
    o run nunca some da lista mesmo já tendo terminado com sucesso. Bug
    pré-existente desde a Fase 171 (não introduzido pela 225), mas a Fase
    225 é o que tornou comum a combinação "chain onde o ÚLTIMO passo é o
    que exige aprovação" (custom_agent anexado ao final + `requires_
    human_approval=True`) — antes disso a situação era rara/inexistente
    nas 3 chains nativas.
  - **Auditoria paralela adversarial** (3 `Agent`, não `Workflow`, sem
    bloqueio de plan mode desta vez):
    - **Varredura cross-tenant em 7 superfícies novas desde a Fase 219**
      (`/integrity/risks`, `/playbooks`, SERPRO/`gov_registry_lookups`
      via export LGPD, `/clients/consultar-cep`, timeline+dossiê-PDF,
      custom-agent-como-passo-de-chain + `PATCH /custom-agents/{id}`,
      `/tenant/theme`+`/tenant/branding`) — **todas as 7 vieram limpas**,
      cada tentativa de acesso cross-tenant bloqueada com 404/403/422
      reais, testado com HTTP real contra os tenants `afj`/`demo`.
    - **LGPD/PII — 4ª ocorrência confirmada da mesma classe de bug já
      fechada 3x antes** (Fase 176.3→`ClientContact`/`ClientInteraction`,
      Fase 210→`Opportunity`, Fase 220→`GovRegistryLookup`): reproduzido
      de ponta a ponta (criar cliente com CPF real → embutir o
      nome/CPF numa tabela nova → `DELETE /lgpd/clients/{id}/data` →
      confirmar que a tabela nova ainda mostra o dado original) em 3
      lugares que `erase_client_data`/`export_client_data` nunca tocam:
      - **`ProcessParty.nome`/`.cpf_cnpj`** (`app/models/process.py`,
        populado por `POST /processes/{id}/partes`) — o mais grave dos
        3: são campos **em texto puro, nunca cifrados** (ao contrário de
        `Client.cpf`), então isso não é só "sobrevive ao esquecimento",
        é PII em claro guardada permanentemente numa tabela que já tinha
        um `client_id` (o mesmo FK que a Fase 222, nesta mesma sessão,
        acabou de tornar central pro vínculo cliente↔processo). O join
        (`cliente_nome`) já mostra `[ANONIMIZADO-...]` corretamente — só
        os campos próprios da parte ficaram de fora.
      - **`FinancialEntry.descricao`** — texto livre que sobrevive
        intacto (nome+CPF originais) depois do esquecimento.
      - **`BillingInvoice.descricao`/`.itens`** — mesmo padrão; o campo
        `cliente` (join) já é anonimizado, os campos de texto livre da
        própria fatura não.
      Confirmado como NÃO regressão: `Opportunity.descricao`/
      `motivo_perda` (fix da Fase 209/210) e `AgentAreaPlaybook`
      (nunca teve PII por desenho, sem `client_id`) seguem limpos.
    - **Walkthrough real via Playwright** (Chromium do sandbox, sem
      bloqueio de plan mode desta vez) nas 4 telas mudadas desde a Fase
      219 — todas limpas, sem console error atribuível a elas (só um
      warning de key duplicada pré-existente em `/dashboard`, não
      relacionado). Confirmou ao vivo, via `page.on("request")` +
      Postgres depois, que o botão de remover cliente da LISTA bate em
      `/lgpd/clients/{id}/data` (não mais `/clients/{id}`) e produz
      `[ANONIMIZADO-...]` de verdade — mesma prova de ponta a ponta já
      usada nas Fases 220/221/222 pra outros endpoints. **Achado
      incidental, visto 2x de fontes independentes na mesma sessão**: o
      card "Celery" de `/admin/health` mostrou "timeout" ao vivo, e
      `/minha-area` mostrou uma notificação real não lida "Infra
      indisponível: Celery (workers)" — bate exatamente com o achado
      técnico abaixo (probe de saúde do Celery quebrado), não com o
      Celery em si (que a própria Fase 227, mais cedo nesta sessão,
      confirmou funcionando de verdade).
  - **Achado técnico adicional, fora do escopo original de reconfirmação,
    encontrado ao investigar por que `/admin/health` mostrava "Celery:
    timeout" mesmo com o Celery real funcionando** (Fase 227 confirmado
    minutos antes na mesma sessão): `_celery()` em
    `app/services/brain_infra.py` chama `celery_app.control.
    inspect(timeout=2.0).ping()` via `asyncio.to_thread(...)` — essa
    chamada **sempre expira** (o wrapper `_com_timeout` de 4s estoura)
    quando executada de dentro do event loop já rodando da aplicação
    real, mesmo que a MESMA chamada síncrona, fora desse contexto (um
    processo Python novo, sem asyncio), retorne um pong real em menos de
    1s. Reproduzido isoladamente 2x (chamada direta síncrona → funciona;
    `await _celery()` num script asyncio → timeout idêntico ao da app
    real). Efeito prático: o card "Celery" da tela de saúde e qualquer
    lógica que dependa dele reportam Celery como fora do ar mesmo quando
    está saudável — o tipo de falso-negativo que pode levar alguém a
    achar que o fix da própria Fase 227 não funcionou. Causa raiz exata
    (por que `asyncio.to_thread` + `control.inspect()` interagem mal)
    não investigada a fundo — fica pra quem for corrigir decidir entre
    trocar o probe por outro mecanismo (ex.: checar liveness via Redis
    diretamente, como `_redis()` já faz) ou investigar a interação
    thread-pool+kombu mais a fundo.
  - Nenhuma correção de achado de produto foi feita nesta fase (metodologia
    padrão) — decisão do usuário sobre quais achados viram fase nova.
    **Próxima rodada deve**: se os 3 achados de LGPD (ProcessParty/
    FinancialEntry/BillingInvoice) forem corrigidos, reconfirmar com o
    mesmo padrão criar→embutir→esquecer→verificar usado aqui, e
    considerar se vale a pena um mecanismo estrutural (não mais um fix
    pontual pela 4ª vez) pra pegar "tabela nova com `client_id` esquecida
    pelo LGPD erasure" antes de virar achado de novo — a mesma pergunta
    que a Fase 219 já tinha deixado em aberto; se o bug do
    `requires_approval` travado for corrigido, reconfirmar especificamente
    o cenário "gate HITL é o último passo da chain" (nativo E
    custom_agent); se o probe do Celery for corrigido, reconfirmar que
    `/admin/health` reflete o estado real (não mais "timeout" com Celery
    saudável).
- **Fase 229** — usuário pediu pra corrigir os 3 achados confirmados da
  Fase 228, sem selecionar um subconjunto ("corrigir os 3").
  - **229.1 — LGPD, 4ª ocorrência fechada** (`backend/app/api/v1/
    lgpd.py`): `erase_client_data`/`export_client_data` ganham
    `ProcessParty` (nome/CPF **em texto puro**, nunca cifrados —
    escopo por join em `LegalProcess` já que a tabela não tem
    `tenant_id` próprio, mesmo padrão de `_get_parte_do_tenant`),
    `FinancialEntry.descricao` e `BillingInvoice.descricao`/`.itens`
    (valor de cada item preservado — não é PII, apagar quebraria o
    total de uma fatura já emitida; reatribuição da lista inteira em
    vez de mutação in-place, já que SQLAlchemy não detecta mutação de
    JSONB sem `MutableList`/`flag_modified`). Decisões de escopo
    deliberadas, documentadas no código: não expandido pra pegar
    `ProcessParty` com `client_id NULL` mas `cpf_cnpj` batendo com o
    titular (ao contrário de `GovRegistryLookup`, aqui `client_id` É
    preenchido pelo fluxo normal — comparação por texto puro entre
    fontes de importação heterogêneas tem risco real de
    falso-positivo/negativo, não é um fix trivial); não criptografado
    `ProcessParty.nome`/`cpf_cnpj` at rest nesta fase (mudança maior,
    própria — migração/backfill, mesma classe de esforço que a
    criptografia de `Client.cpf`/`cnpj` foi no passado). Novo teste
    `test_lgpd_erasure_reaches_process_financial_fase228.py` (3 casos,
    um por tabela) — bate na mesma flakiness de pool asyncpg/
    pytest-asyncio documentada desde a Fase 199 (confirmado que
    NENHUMA diferença: até um teste pré-existente e não tocado,
    `test_lgpd_erasure_reaches_crm_fase210.py`, falha de forma
    idêntica rodando sozinho neste ambiente agora — não é regressão).
    Verificação real via HTTP direto (Postgres real): as 3 tabelas
    scrubadas corretamente após `DELETE /lgpd/clients/{id}/data`,
    `valor`/`itens[].valor` preservados, export não vaza o dado
    original em nenhuma das 3 seções novas (`partes_processo`,
    `lancamentos_financeiros`, `faturas`).
  - **229.2 — HITL, `requires_approval` travado** (`backend/app/
    services/chain_resume.py:65-73`): o branch de retorno antecipado
    (gate era o último passo da chain) ganhou `agent_run.
    requires_approval = False` dentro do guard já existente, mesmo
    padrão de comentário da Fase 174.7 que já cobria os outros 2
    branches de finalização. Teste unitário estendido
    (`test_resume_noop_when_gate_was_last_step`,
    `test_chain_resume.py`) — setando `requires_approval = True` antes
    da chamada (senão o teste passava mesmo com o bug) e afirmando
    `False` depois. Reconfirmado também com o cenário mais realista já
    usado na própria Fase 228 (chain de 3 gates, 2 nativos forçados +
    1 `custom_agent`, script do scratchpad reexecutado): `requires_
    approval` agora vira `False` corretamente no final. **Fora de
    escopo, documentado como observação separada**: o mesmo branch (e
    o branch FAILED de `_run_remaining_steps`) não chama
    `_publish_completion` (push via websocket) — gap pré-existente,
    mais amplo que este bug específico; misturar aqui arriscaria
    consertar só pela metade. Fica pra decisão futura.
  - **229.3 — probe de saúde do Celery, causa raiz REDIAGNOSTICADA**
    (`backend/app/services/brain_infra.py`): a hipótese da Fase 228
    (contenção de thread pool sob `asyncio.to_thread`) foi testada
    primeiro (executor dedicado só pro probe) e **não resolveu** —
    confirmado empiricamente que `celery.ok` continuava `false` mesmo
    com o executor isolado. Instrumentação de tempo direto no código
    real revelou a causa verdadeira: `_inspect_celery_sync` faz 4
    round-trips SEQUENCIAIS (`ping`/`active`/`scheduled`/`stats`, cada
    um um broadcast+collect via kombu/Redis com seu próprio timeout) —
    medido em ~2.1s CADA UM mesmo com o worker respondendo rápido
    (confirmado: com timeout menor o pong chega em 0.4-1.3s: o tempo
    perto do timeout configurado é o próprio loop de coleta do kombu,
    não lentidão real do worker). 4 × ~2.1s soma ~8.5s medido
    diretamente, sempre estourando o orçamento de 4s compartilhado com
    as outras sondas — não depende de thread vs. loop, é aritmética.
    Fix: timeout por chamada reduzido de 2.0 pra 1.0 (folga generosa
    sobre o 0.4-1.3s observado) + orçamento externo PRÓPRIO pro probe
    do Celery (`_CELERY_PROBE_TIMEOUT = 8.0`, não o `_PROBE_TIMEOUT`
    genérico de 4s usado pelas sondas async-nativas de round-trip
    único). O executor dedicado (`ThreadPoolExecutor(max_workers=1)`)
    foi mantido mesmo não sendo a causa raiz — inofensivo, isola o
    probe de qualquer contenção futura no executor padrão. Sem teste
    automatizado (bug de latência/ambiente real, não testável com
    fake) — verificado com 5 chamadas HTTP reais consecutivas contra
    `GET /system/brain/infra` e `GET /system/health/detailed`
    (`celery.ok: true` consistente, workers corretamente listados) E
    contra o caminho da task periódica do Celery Beat
    (`checar_infra_periodico`, que roda `coletar_infra()` DE DENTRO de
    um worker Celery, não do uvicorn — confirma que o fix não introduz
    nenhum problema de fork/thread aninhado nesse contexto também):
    `succeeded in 4.1s: {'checks': 4, 'alertas': 0, ...}`, sem alerta
    falso de infra indisponível.
  - `ruff check`/`py_compile` limpos nos 5 arquivos tocados (3 backend
    + 2 de teste). Verificação principal via HTTP real contra
    Postgres+Redis+Celery+uvicorn reais (mesmo padrão de toda fase
    recente) — a suíte pytest bateu na mesma flakiness de pool
    asyncpg/pytest-asyncio já documentada desde a Fase 199, confirmada
    como não-regressão (teste pré-existente não tocado falha de forma
    idêntica no mesmo ambiente).
- **Fase 230** — usuário pediu 3 coisas na mesma mensagem: (1) integrar o
  sistema à página pública www.afjadvogados.com, que em breve terá um
  link de acesso; (2) capturar referências geográficas ao cadastrar o
  endereço do escritório (groundwork pro mapa com marcadores de
  escritório+clientes, "em breve"); (3) avaliar o sistema e preparar
  uma área de geração de relatórios. Escopo desta fase confirmado com o
  usuário via perguntas: geocodificação via BrasilAPI (já integrada,
  sem credencial nova), só a base agora (sem mapa visual ainda), do
  lado do site só confirmar a URL de login (sem UTM/domínio próprio), e
  relatórios só avaliação escrita (sem construir nada).
  - **Achado de investigação, confirmado de novo nesta fase**: este
    sandbox bloqueia egress pra `www.afjadvogados.com` (confirmado via
    tentativa de acesso direto) e pra `brasilapi.com.br` (já
    documentado desde a Fase 217) — não deu pra navegar o site real nem
    validar a chamada de geocodificação contra uma resposta real da
    BrasilAPI nesta sessão. Tentativa de confirmar a URL de produção
    via MCP do Vercel também retornou 403 (sem acesso à conta desta
    sessão).
  - **Geocodificação — `backend/app/integrations/publicas/
    cep_lookup.py`**: `consultar_cep()` passou a extrair `latitude`/
    `longitude` do bloco `location.coordinates` que a BrasilAPI v2 já
    devolve (quando a fonte subjacente — viacep/correios/widenet — tem
    a coordenada) — precisão de CEP/quadra, não do número exato.
    Fail-soft: `_extrair_coordenadas()` nunca lança exceção,
    `(None, None)` quando ausente/inválido. Verificado com dado
    sintético no formato real documentado da BrasilAPI (já que o
    egress real está bloqueado neste sandbox): extração correta de
    coordenadas válidas, e degrada graciosamente pra `(None, None)` em
    4 cenários (`location` ausente, `location` vazio, `coordinates`
    vazio, valor não-numérico).
  - **`Client.endereco_json`**: sem migração de schema (já era JSONB)
    — `POST/PUT /clients` (`backend/app/api/v1/clients.py`) ganharam um
    novo helper `_geocodificar_endereco()`, chamado automaticamente ao
    salvar um cliente com CEP no endereço; nunca bloqueia o save se a
    geocodificação falhar, e não rechama a API se o endereço já tiver
    coordenadas (evita round-trip desnecessário numa edição que não
    mexeu no endereço). Verificado via HTTP real (criar cliente com
    endereço real) e via mock da chamada externa (4 cenários: sucesso
    mescla lat/lng, coordenadas existentes são preservadas sem
    rechamar, endereço sem CEP passa intacto, `None` passa intacto).
  - **`Tenant.endereco_json` — campo novo** (`backend/app/models/
    tenant.py`, `Tenant` não tinha NENHUM campo de endereço antes desta
    fase): mesmo formato de `Client.endereco_json`. Migração idempotente
    (`ALTER TABLE tenants ADD COLUMN IF NOT EXISTS endereco_json JSONB`)
    em `app/core/events.py`, mesmo padrão de toda coluna nova deste
    projeto. Novo par `GET/PUT /tenant/endereco`
    (`backend/app/api/v1/tenant.py`), seguindo exatamente o padrão já
    estabelecido nesse arquivo (`/feriados`, `/confidencial` —
    `require_role("ADMIN")` no PUT, mesmo helper de geocodificação do
    Client). Frontend: nova seção "Endereço do Escritório" na aba
    Escritório de `/configuracoes`
    (`frontend/src/components/configuracoes/EscritorioZone.tsx`, Fase
    224) — CEP com autofill (mesmo padrão de `ClienteFormFields.tsx`/
    `clientes/page.tsx::autofillCep`), indicador visual quando a
    localização foi capturada. Verificado via HTTP real (GET vazio
    inicialmente, PUT salva e degrada sem coordenadas neste sandbox,
    GET reflete o salvo), 403 pra ADVOGADO no PUT, isolamento
    cross-tenant confirmado (tenant demo não vê o endereço do tenant
    afj) — e via Playwright real (Chromium do sandbox, `npm run dev`
    com `API_URL` local): seção renderiza, CEP/Logradouro presentes,
    save funciona ("Salvo!"), zero console error atribuível à mudança
    (só o warning de key duplicada pré-existente em `/dashboard`, já
    documentado em fases anteriores, não relacionado).
  - **Avaliação escrita — URL de login pro site público** (sem mudança
    de código, conforme escopo confirmado): o sistema já tem uma página
    pública em `/` (`frontend/src/app/page.tsx`) com botão "Entrar no
    Sistema" → `/login` — destino natural pro link do site. Não há
    domínio próprio configurado hoje (roda em `*.vercel.app`, alias
    exato só visível no dashboard do Vercel, fora do alcance desta
    sessão — tentativa via MCP retornou 403). CORS
    (`backend/app/main.py:58`) só importa se o site tentar EMBUTIR algo
    chamando a API diretamente (iframe/widget) — pra um link simples,
    irrelevante. Ação recomendada fora do alcance de código: usuário
    confirma a URL de produção no dashboard Vercel e repassa pro time
    do site; se quiser domínio com a marca (`app.afjadvogados.com`), é
    mudança de DNS+Vercel fora daqui — só a parte de CORS em
    `main.py:58` fica pra código, quando/se o domínio for definido.
  - **Avaliação escrita — área de geração de relatórios** (sem mudança
    de código): `/relatorios` (`frontend/src/app/(dashboard)/
    relatorios/page.tsx`) hoje é só 4 abas de gráficos
    (Gestão/Financeiro/Processos/Agentes IA) — nenhum botão de
    exportar, nenhum PDF/CSV/XLSX. `/admin/relatorios-banca` já tem
    exatamente o padrão que falta ali — escolha de formato via `GET
    /reports/consolidated/export?format=`, incluindo XLSX
    (`backend/app/api/v1/reports_admin.py:253-310`).
    `backend/app/utils/pdf_builder.py::build_report_pdf` (linha 428) é
    o único builder genérico (`{heading, body}` → PDF); os outros 3 são
    específicos de um documento (petição, matriz de banca, fatura). Não
    existe hoje nenhum conceito de "relatório customizável" — cada
    exportação é um endpoint dedicado a um dataset fixo; uma área de
    geração de relatórios de verdade seria essa abstração pela primeira
    vez, não uma extensão de algo existente. Recomendação pra quando o
    usuário quiser avançar: estender `/relatorios` com exportar por aba
    (reaproveitando o padrão PDF/CSV/XLSX de `reports_admin.py`) e
    reservar uma aba "Geográfico" pra quando o mapa existir — decisão
    de nav (`frontend/src/lib/nav.ts`) e escopo de dado ficam pra essa
    fase futura.
  - `ruff check`/`py_compile` limpos nos 5 arquivos backend tocados;
    `tsc --noEmit`/`eslint` limpos no arquivo frontend tocado (1
    warning pré-existente de `exhaustive-deps`, confirmado via `git
    stash` como não-novo desta fase).
- **Fase 231** — usuário pediu pra continuar com a peça que a Fase 230
  deixou como "em breve": o mapa visual com marcadores de
  escritório+clientes, agora que a geocodificação (lat/lng) já está em
  produção. Primeira integração de biblioteca de mapa neste projeto —
  investigação (Explore) confirmou que nenhuma lib de mapa existia
  antes, e que `GET /tenant/endereco`/`GET /clients` já trazem tudo
  que o mapa precisa (sem endpoint novo).
  - **`leaflet` + `react-leaflet@4` + `@types/leaflet`** — OpenStreetMap
    (tiles gratuitos, sem chave de API), mesmo espírito
    "grátis/sem credencial" já usado pra BrasilAPI (Fase 217/230).
  - **`frontend/src/components/mapa/EscritorioClientesMap.tsx`** (novo,
    `"use client"`) — `MapContainer`/`TileLayer`/`Marker`/`Popup` do
    react-leaflet. Ícones de marcador custom via `L.divIcon` (SVG
    inline) em vez do ícone padrão do Leaflet — evita o bug clássico
    de paths de imagem quebrados sob bundler (webpack/Next), sem
    precisar copiar assets pra `/public`. Cor lida em runtime via
    `getComputedStyle(...).getPropertyValue('--brand-primary'/
    '--brand-secondary')` — ouro pro escritório, navy pros clientes,
    theme-aware (tenant pode ter cor própria, Fase 224). Enquadramento
    automático via `map.fitBounds()` — nunca um centro fixo hardcoded
    do Brasil, já que o escritório pode ficar em qualquer lugar.
  - **`frontend/src/app/(dashboard)/mapa/page.tsx`** (novo) — mesmo
    padrão estrutural de `relatorios/page.tsx`: `Breadcrumb` +
    `.afj-page-header`, busca `GET /tenant/endereco` + `GET /clients`
    em paralelo, filtra client-side por `endereco_json.latitude !=
    null`, carrega o mapa via `dynamic(..., { ssr: false })` (Leaflet
    acessa `window`/`document` no import — quebra em SSR sem isso,
    mesmo padrão já usado pra `GestaoCharts`/`ProcessosCharts`).
    Estado vazio explícito ("Nenhum endereço geocodificado ainda")
    quando nem o escritório nem nenhum cliente tem coordenadas — não
    tenta renderizar um mapa sem marcador nenhum.
  - **Nav** (`frontend/src/lib/nav.ts`): novo item "Mapa" (ícone
    `MapPin`) na seção GESTÃO, logo após "Relatórios" — mesmo gate de
    papel (`GESTAO` = ADMIN/SUPERADMIN/SOCIO/GESTOR) que `/relatorios`/
    `/financeiro`, sem proteção adicional server-side (sem precedente
    disso neste projeto — gate real é o backend, que já filtra por
    tenant/papel nos 2 endpoints reaproveitados).
  - **Achado incidental corrigido durante a verificação**: o primeiro
    teste via Playwright do link "Mapa" no menu deu falso-negativo —
    não era bug (confirmado num 2º teste, com mais tempo de espera
    após o login, que achou o link normalmente); o teste original
    checava o DOM cedo demais, antes do sidebar acabar de hidratar.
  - Verificado via HTTP real (Postgres real): `GET /tenant/endereco`/
    `GET /clients` respondem no formato esperado. Como este sandbox
    bloqueia egress pra `brasilapi.com.br` (Fase 217/230) e também pra
    `tile.openstreetmap.org` (achado novo desta fase — mesma classe de
    restrição, domínio diferente), nenhum endereço real tinha lat/lng
    neste ambiente — populado manualmente via script (simulando o que
    a geocodificação real preencheria em produção: 1 escritório + 3
    clientes) pra testar o mapa de fato. Playwright real (Chromium do
    sandbox) confirmou: container do Leaflet renderiza, 4 marcadores
    aparecem (1 ouro pro escritório + 3 navy pros clientes), popup
    abre ao clicar com o texto certo, zero console error atribuível à
    mudança (só os `ERR_TUNNEL_CONNECTION_FAILED` esperados das
    imagens de tile bloqueadas pelo proxy deste sandbox — as próprias
    tiles não carregam aqui, mas a estrutura/marcadores/popups do mapa
    funcionam perfeitamente; produção com egress real deve mostrar o
    mapa de fundo normalmente). Screenshot confirma visualmente o
    resultado (marcador ouro do escritório com popup aberto, marcadores
    navy dos clientes, atribuição do OpenStreetMap, controles de
    zoom — tudo com a paleta certa da marca).
  - `tsc --noEmit`/`eslint` limpos nos arquivos novos/tocados (1
    warning pré-existente de `exhaustive-deps` na nova página, mesmo
    padrão já aceito em `relatorios/page.tsx` e toda página que busca
    dado só no mount).
  - Fora de escopo desta fase (não pedido): filtro/busca de cliente no
    mapa, cluster de marcadores pra volumes grandes, e a "extração de
    relatórios" a partir do mapa mencionada no pedido original da Fase
    230 — essa última seguirá aguardando a área de geração de
    relatórios já avaliada (e não construída) naquela fase.
- **Fase 232** — usuário apontou, com 2 screenshots, 2 cadastros
  duplicados: (1) "Endereço do Escritório" (Fase 230) e "Timbrado dos
  Documentos → Endereço" (pré-existente) pedindo o mesmo endereço duas
  vezes; (2) a aba "Contatos" do Cliente 360 aparecendo vazia mesmo
  pra um cliente PF (pessoa física), redundante com o telefone/whatsapp
  já mostrado em "Dados Cadastrais". Investigação (2 Explore) confirmou
  os 2 pontos e um 3º achado incidental: "Nome do Escritório" (aba
  Escritório) e "Nome no cabeçalho" (Timbrado) são o MESMO conceito
  duplicado — mas "Nome do Sistema" (aba Aparência, branding do
  software) é um conceito DIFERENTE, confirmado lendo os labels exatos
  no código, e não deve ser unificado (corrigindo o que a primeira
  leitura do Explore agent tinha contado solto como "3 lugares").
  Usuário confirmou (via perguntas): padrão automático + personalização
  opcional pro endereço/nome do timbrado, esconder a aba Contatos pra
  clientes PF, e incluir a unificação de nome do escritório (não do
  nome do sistema) nesta mesma fase.
  - **Backend — `backend/app/api/v1/tenant.py`**: mecanismo de
    "sincronização por escrita + fallback de leitura". Novo
    `_endereco_para_texto()` formata o endereço estruturado numa linha
    (mesmo formato já usado em `/mapa`). `LetterheadUpdate` ganha
    `office_name_custom`/`address_custom` (bool). `update_endereco`
    (`PUT /tenant/endereco`) e `update_branding` (`PUT /tenant/branding`,
    quando `office_name` está no body) passam a escrever o valor
    derivado dentro de `document_templates.letterhead` — mas só quando
    o campo correspondente não estiver marcado `_custom=True` — mantendo
    o dict bruto correto pros 7 call sites de PDF existentes
    (`documents.py`/`portal.py`/`google_integration.py`/
    `reports_admin.py`/`invoices.py`/`clients.py`/`esign.py`) **sem
    tocar nenhum deles**. `get_letterhead` (`GET /tenant/letterhead`)
    ADICIONALMENTE recalcula o valor efetivo na leitura (cobre tenant
    com dado histórico, sem precisar de backfill). `update_letterhead`
    grava os 2 flags e recalcula a partir do cadastro de origem quando
    um flag volta a `False` (nunca confia cegamente no texto antigo que
    o frontend mandar).
  - **Frontend — `frontend/src/components/configuracoes/
    EscritorioZone.tsx`**: os campos "Nome no cabeçalho" e "Endereço"
    (card Timbrado) ganham o padrão automático/personalizar — modo
    automático mostra o valor derivado como texto read-only + link
    "Personalizar..."; modo personalizado mostra o input editável (como
    antes) + link "Usar...automaticamente" pra reverter. `saveLetterhead()`
    envia os 2 flags no PUT.
  - **Frontend — `frontend/src/app/(dashboard)/clientes/[id]/page.tsx`**:
    a aba "Contatos" (botão + conteúdo + gatilho do modal "Novo
    Contato") só aparece quando `cliente.tipo === "PJ"` — `ClientContact`
    é conceitualmente pra representantes de empresa, não pro próprio
    titular PF. Novo `useEffect` cai de volta pra "interacoes" se o
    estado ficar em "contatos" com um cliente PF (navegação anterior).
  - Verificado via HTTP real contra Postgres real (login ADMIN real):
    `PUT /tenant/endereco` → `GET /tenant/letterhead` reflete o endereço
    formatado com `address_custom: false`; `PUT /tenant/branding` com
    `office_name` → nome refletido automaticamente; `PUT
    /tenant/letterhead` com `address_custom: true` e texto próprio →
    sobrevive intacto a um `PUT /tenant/endereco` subsequente com CEP
    diferente; voltar `address_custom: false` → recalcula pro endereço
    atual, não repete o texto antigo. Playwright real (Chromium do
    sandbox, `npm run dev` com `API_URL` local): os 2 campos do Timbrado
    aparecem em modo automático por padrão, "Personalizar" revela o
    input editável de forma independente por campo; cliente PF criado
    via API mostra só as abas "Interações"/"Financeiro" (Contatos
    ausente); cliente PJ criado via API mostra "Contatos (0)" +
    botão "+ Contato" normalmente. `ruff check`/`py_compile` limpos no
    backend; `tsc --noEmit`/`eslint` limpos no frontend (1 warning
    pré-existente de `exhaustive-deps` em `clientes/[id]/page.tsx`,
    confirmado via `git stash` como não-novo desta fase).
- **Fase 233** — usuário pediu 2 coisas na mesma mensagem: (1) "todos os
  cadastros que possuam área CEP devem capturar as coordenadas e o
  endereço, o cadastro de clientes não está capturando"; (2) "o portal
  do cliente deve conter somente um dashboard com toda a sua situação
  processual".
  - **Geocodificação de clientes — sem bug de backend confirmado**.
    Auditoria completa (`backend/app/models/`) confirmou que só
    `Tenant` e `Client` têm campo de endereço/CEP no sistema inteiro —
    nada mais a estender. Leitura direta de `clients.py` mostrou que
    `_geocodificar_endereco()` já é chamado em `create_client`/
    `update_client` (mesmo padrão do `Tenant`, Fase 230). Em vez de
    presumir que o código estava correto, um script standalone (fora do
    pytest, mesmo workaround já usado nas Fases 202/209 pra fugir da
    flakiness de pool asyncpg/pytest-asyncio) rodou `create_client`/
    `update_client` reais contra Postgres real com `_consultar_cep_
    externa` monkeypatchada — confirmou que o backend geocodifica
    corretamente em ambos os fluxos, persiste no Postgres (não só na
    resposta em memória), e não quebra nem chama a API externa quando o
    endereço não tem CEP. **Causa real do "não está capturando"**: puramente
    de UI — `EscritorioZone.tsx` (endereço do escritório) já tinha uma
    confirmação visual explícita desde a Fase 230 ("✓ Localização
    geográfica capturada"), mas `ClienteFormFields.tsx` nunca teve
    equivalente (o tipo `Endereco` nem declarava `latitude`/`longitude`)
    — o cadastro de cliente podia estar geocodificando certo por trás e
    mesmo assim parecer quebrado. Corrigido: `ClienteFormFields.tsx`
    ganha a mesma confirmação visual (mesmo texto/ícone do escritório,
    condicionada a um novo prop `temCoordenadas`); `clientes/page.tsx`
    passa a popular esse estado a partir da RESPOSTA do POST/PUT
    `/clients` (não do preview de autofill de CEP, que nunca teve
    coordenada — mesma decisão de design já usada no escritório) e
    exibe um toast diferenciado ("... — localização geográfica
    capturada.") no save; ao reabrir editar um cliente já geocodificado,
    a confirmação aparece imediatamente a partir do `endereco_json` já
    salvo. Decisão de escopo confirmada com o usuário: sem backfill de
    clientes cadastrados antes desta fase (mesmo padrão já aceito no
    projeto pra outros dados legados, ex. storage de documentos da Fase
    141) — só daqui pra frente.
  - **Portal do Cliente — consolidado numa tela só**. Antes eram 5
    páginas com nav própria (`/portal/dashboard`, `/portal/processos[/
    id]`, `/portal/documentos`, `/portal/financeiro`, `/portal/
    mensagens`). Usuário confirmou (via pergunta) que queria manter as
    4 funcionalidades, só reorganizadas — não removidas. Novos
    componentes em `frontend/src/components/portal/`:
    `ProcessosSection.tsx` (seção principal, sempre visível — lista de
    processos que expande **inline** ao clicar, sem navegar, buscando
    `GET /portal/processes/{id}` sob demanda e cacheando no estado;
    junta o que antes eram 2 rotas separadas — lista + detalhe — numa
    só), `DocumentosSection.tsx`/`FinanceiroSection.tsx`/
    `MensagensSection.tsx` (cartões colapsáveis, fechados por padrão,
    cada um só busca dado na primeira vez que é aberto). `portal/
    dashboard/page.tsx` reescrita pra montar as 4 seções + os 3 stat
    cards (agora só resumo visual, sem link — não há mais rota separada
    pra linkar) + o bloco "Seus Dados" já existente. `(portal)/
    layout.tsx` perde o array `NAV`/barra de navegação (desktop +
    dropdown mobile) — só 1 página agora. As 5 rotas antigas foram
    removidas (`git rm`, confirmado por grep que nada mais no repo
    referenciava essas URLs — nenhum e-mail/notificação/link externo).
    Backend `portal.py`: nenhuma mudança — os mesmos endpoints seguem
    sendo consumidos, só que por componentes na mesma página.
  - Verificado via HTTP real (login ADMIN real, `POST /clients` com CEP
    degradando graciosamente sem coordenada neste sandbox — mesma
    limitação de egress à BrasilAPI já documentada desde a Fase 217,
    coordenada seedada manualmente no Postgres pra testar a UI de
    confirmação, mesmo workaround já usado no `/mapa` da Fase 231) e
    Playwright real (Chromium do sandbox, `npm run dev` com `API_URL`
    local): confirmação "✓ Localização geográfica capturada." aparece
    ao reabrir editar um cliente já geocodificado; portal logado como
    cliente real (`invite-portal` + processo de teste vinculado) mostra
    a nav antiga ausente do header, a seção "Situação Processual"
    sempre visível com o processo, expandir o processo mostra
    "Movimentações" inline sem navegar (URL continua em `/portal/
    dashboard`), as 3 seções colapsáveis presentes e a de Mensagens
    abrindo com o campo de envio funcional. `tsc --noEmit` limpo;
    `eslint` limpo nos arquivos tocados (nos componentes novos do
    portal, os 2 warnings de `exhaustive-deps` em `useEffect(() => {
    load...() }, [])` são o MESMO padrão já presente nos arquivos
    originais antes de serem apagados, confirmado lendo o conteúdo
    deletado via `git show HEAD:...` — não é regressão). Teste backend
    novo (`test_client_geocoding_fase233.py`, Postgres real) bate na
    mesma flakiness de pool asyncpg/pytest-asyncio documentada desde a
    Fase 199 mesmo isolado — confirmado não-regressão reproduzindo o
    mesmo erro num teste pré-existente e não tocado
    (`test_client_document_validation_fase217.py::
    test_validacao_bem_sucedida_grava_auditoria`, mesmo padrão de
    fixture `cenario`/`AsyncSessionLocal`); por isso a prova real
    definitiva desta fase veio do script standalone descrito acima, não
    do pytest.
- **Fase 234** — usuário pediu pra separar o acesso do cliente ao Portal
  do resto do cadastro de usuários internos, substituindo por link
  temporário/seguro com validade configurável, revogação e regeneração,
  numa nova área administrativa "Controle de Clientes". Pediu
  explicitamente pra investigar a arquitetura atual antes de
  implementar. Investigação (leitura direta — o Explore agent falhou
  por limite de sessão da API; um 2º Explore, sobre padrões de token,
  completou) confirmou: o mecanismo antigo (`POST /users/{client_id}/
  invite-portal`) criava um `User` real permanente (`role="CLIENT"`,
  senha temporária, sem expiração/revogação); `get_current_user`
  (`app/dependencies.py`, usado por TODOS os ~82 endpoints) resolve o
  JWT direto contra `SELECT * FROM users WHERE id=sub` — reescrever essa
  dependência compartilhada era desnecessário e de alto risco pro que
  foi pedido. Decisão de design: manter um `User` técnico oculto por
  trás do link (nunca exposto ao admin, já consistente com o comentário
  pré-existente em `users.py:52`, *"CLIENT nasce apenas pelo fluxo do
  portal — nunca por convite/edição"*) — a separação que importa é de
  produto/UX (admin nunca cria/gerencia um "usuário", só gera/revoga um
  link), não a eliminação total do `User` como implementação.
  - **Backend**: novo model `ClientPortalAccess`
    (`app/models/client.py`, tabela nova via `create_all()`, sem ALTER)
    — 1 registro por cliente (`client_id` UNIQUE), `token_hash` (SHA-256
    via `hash_token()`, mesmo padrão de `Session.token_hash`),
    `expires_at`/`revoked_at`. Três endpoints novos em `clients.py`:
    `GET /clients/portal-access` (lista todo cliente do tenant + status
    computado na leitura: SEM_ACESSO/ATIVO/EXPIRADO/REVOGADO — precisou
    ser declarado ANTES de `GET /{client_id}` no arquivo, senão o
    roteamento por ordem de declaração do FastAPI casava `/portal-
    access` como `client_id="portal-access"`), `POST /{id}/portal-
    access` (gera/regenera — reaproveita o `User` técnico existente ou
    cria um com e-mail sintético `portal-{client_id}@clients.internal`,
    nunca exige e-mail do cliente ao contrário do fluxo antigo; token
    bruto devolvido uma única vez, nunca recuperável depois), `DELETE
    /{id}/portal-access` (revoga — `revoked_at` + `is_active=False` no
    User técnico, bloqueio imediato reaproveitando o filtro que
    `get_current_user`/`/auth/refresh` já fazem). Removido `POST /users/
    {client_id}/invite-portal` (`users.py`) — único call site era o
    botão antigo do Cliente 360, também substituído.
  - **Backend — novo endpoint de troca de token**: `POST /auth/portal-
    redeem` (`auth.py`, não `portal.py`) — **achado real de arquitetura
    descoberto durante a implementação, corrigido na hora**: a 1ª
    tentativa colocou esse endpoint em `portal.py`, mas
    `api_router.include_router(portal.router, dependencies=_BLOCK)`
    (`app/api/v1/router.py:48`) aplica `require_active_tenant` (que por
    sua vez exige `get_current_user`) a QUALQUER rota daquele router —
    inclusive uma pensada pra ser pública, fazendo o redeem sempre
    devolver 401 "Token de autenticação não fornecido" antes mesmo do
    handler rodar. `auth.router` é o único router sem dependência
    global (mesmo motivo de `/login`/`/demo-login` estarem lá) — mesmo
    mecanismo exato de emissão (JWT+refresh+`Session`), sem duplicar
    lógica; rate-limit por IP (20/5min, mesmo padrão de `/demo-login`);
    mensagem de erro sempre genérica (token inexistente/revogado/
    expirado tratados igual, evita virar oráculo). `get_portal_client()`
    (`portal.py`) ganhou uma checagem viva de `ClientPortalAccess.
    expires_at` além do `is_active` do User — cobre "expirou agora mesmo,
    reaper ainda não rodou", bloqueio no instante exato da expiração.
    Novo reaper diário (`app/workers/tasks/client_portal_access_reaper.py`,
    mesmo padrão de `session_cleanup.py`) desativa o User técnico de
    acessos vencidos-não-revogados — higiene, não a garantia de
    segurança em si (essa já é a checagem viva).
  - **Frontend — Controle de Clientes**: novo
    `frontend/src/components/clientes/ClientPortalAccessPanel.tsx` —
    tabela Cliente/Status/Criado em/Expira em/Ações, seletor de validade
    (1/3/7/15/30 dias) por linha, Gerar/Regerar, Revogar (com
    confirmação), modal de link copiável (mesmo padrão do antigo modal
    de senha temporária do Cliente 360, que foi removido).
    `clientes/page.tsx` ganha pills "Clientes"/"Controle de Clientes"
    (`?aba=`, mesmo padrão de estado de aba já usado em Configurações/
    Cérebro), visível só pra ADMIN (mesmo gate do backend). Cliente 360
    (`clientes/[id]/page.tsx`): removidos `convidarPortal`/
    `showPortalModal`/`portalCredentials`/`copyPassword`/estado
    associado — o botão "Portal" agora é um link pra `/clientes?aba=
    controle-portal`.
  - **Frontend — Portal do Cliente**: nova página `/portal/acesso/
    [token]/page.tsx` — troca o token da URL por sessão real via `POST
    /auth/portal-redeem`, salva tokens (incl. `afj_portal_refresh_
    token`, nunca usado antes) e redireciona pro dashboard; erro mostra
    "Link inválido ou expirado" na própria página, sem navegação.
    `/portal/login/page.tsx` reescrita — perde o formulário de e-mail/
    senha (nenhum caminho do sistema dá mais senha usável a um cliente),
    vira página informativa; mantida na mesma rota porque `(portal)/
    layout.tsx` (logout) e `portalApi.ts` (sessão expirada) já
    redirecionam pra cá. **Achado real, corrigido na hora**:
    `frontend/src/middleware.ts` protege toda rota `/portal/*` atrás do
    cookie `afj_portal_session`, com only `/portal/login`/`/portal` na
    allowlist — a nova rota `/portal/acesso/[token]` (que é justamente o
    que CRIA esse cookie) caía nesse guard e nunca chegava a rodar,
    redirecionando pra `/portal/login` antes de qualquer fetch —
    confirmado ao vivo via Playwright com captura de rede (zero
    requisições disparadas) antes do fix; `/portal/acesso/` adicionado à
    allowlist do middleware resolveu. `portalApi.ts` ganha renovação via
    `/auth/refresh` no primeiro 401 (usando o refresh token agora salvo)
    antes de desistir — sem isso a remoção da senha viraria regressão
    real (sessão de 30 min sem forma de renovar, hoje sem uso desse
    endpoint no portal). Logout (`(portal)/layout.tsx`) passou a chamar
    `POST /auth/logout` de verdade (achado colateral: nunca chamava,
    só limpava local) — invalida a `Session`/refresh no backend.
  - Verificado via HTTP real contra Postgres real: fluxo completo
    gerar→redeem→`GET /portal/me` funciona; token inexistente → 401;
    revogar bloqueia IMEDIATAMENTE mesmo com o JWT ainda "válido" por
    data (via `is_active`); regenerar após revogar reativa o acesso com
    um token NOVO — o antigo (mesmo sem ter expirado por data) para de
    funcionar porque o hash mudou; forçar `expires_at` no passado direto
    no Postgres bloqueia via a checagem viva (403), mesmo sem revogação
    explícita, e um novo redeem com o mesmo token também falha (401);
    reaper roda limpo e idempotente numa 2ª rodada; isolamento
    cross-tenant confirmado — ADMIN do tenant demo recebe 404 ao tentar
    gerar/revogar acesso de um cliente do tenant afj, e a listagem nunca
    inclui esse cliente; rate-limit do redeem dispara na 14ª chamada
    consecutiva; endpoint antigo `invite-portal` confirmado removido
    (404). Playwright real (Chromium do sandbox, `npm run dev` com
    `API_URL` local): ADMIN gera link na aba Controle de Clientes,
    abre o link numa sessão de navegador totalmente limpa (novo
    `BrowserContext`) → cai direto no dashboard do portal com dado
    real; ADMIN revoga → o MESMO link, reaberto, mostra "Link inválido
    ou expirado" em vez do dashboard. `tsc --noEmit`/`eslint`
    limpos em todos os arquivos novos/tocados (backend e frontend).
  - **Decisão de escopo deliberada, não corrigida nesta fase**:
    `erase_client_data` (LGPD) não revoga automaticamente o
    `ClientPortalAccess` de um cliente esquecido — os 2 são conceitos
    ortogonais (esquecimento apaga PII, acesso ao portal é controle de
    autorização) e o admin já tem a ação de Revogar manual disponível
    na mesma tela; registrado aqui como observação, não achado, caso o
    usuário decida numa fase futura que "esquecer" deveria também
    revogar automaticamente.
- **Fase 235** — usuário pediu explicitamente "faça o teste geral do
  sistema e suas devidas correções", desta vez COM correção na mesma
  rodada (diferente do padrão histórico do projeto, precedente já usado
  uma vez, Fase 209). Releitura do histórico: a última rodada de teste
  geral de verdade foi a Fase 228 (achou 3 bugs, corrigidos na 229) —
  desde então, **5 fases inteiras (230-234) nunca passaram por nenhuma
  rodada de teste geral**, incluindo a mais nova e mais sensível: acesso
  ao Portal via link temporário (Fase 234, autenticação sem senha).
  - **Auditoria (2 Explore agents, código — prova empírica na
    implementação)**: (A) mapeamento completo de todo model com
    `client_id` cruzado contra `erase_client_data`/`export_client_data`
    — finalmente responde de vez uma pergunta repetida desde a Fase 219
    e reaberta na 228 ("vale um mecanismo estrutural pra não achar
    tabela esquecida pela Nª vez?"); (B) revisão de segurança dedicada
    ao ponto mais novo (Fase 234).
  - **A. LGPD — 5 lacunas reais, todas corrigidas e verificadas
    empiricamente** (criar cliente com PII real → embutir nas 5
    tabelas → export confirma real → esquecer → export confirma
    scrubado, via HTTP real contra Postgres real):
    1. **`User.full_name`** — o `User` técnico oculto por trás do link
       de acesso ao portal (Fase 234) copia `client.nome_completo` na
       criação e nunca era tocado pelo esquecimento — nome original
       sobrevivia indefinidamente nesse `User`.
    2. **`Document.conteudo_texto`/`.conteudo_html`** — corpo inteiro de
       petições/documentos, nunca alcançado (`titulo`/`status`
       preservados, são histórico do escritório, não PII do titular).
    3. **`Contract.assinaturas`** (JSONB, pode ter nome/CPF do
       signatário) — nunca alcançado.
    4. **`AgentRun.input_data`/`.output_data`/`.error_message`** —
       prompts/resultados de IA pro cliente, texto livre (`tokens_used`/
       `cost_usd`/`status` preservados — auditoria de custo, não PII).
    5. **`LegalProcess.descricao`** — só era alcançado indiretamente via
       `ProcessParty`; o processo em si nunca. Fix reaproveita
       `client_linked_processes_filter()` (Fase 222) pra cobrir os 2
       caminhos de vínculo (client_id direto E via ProcessParty), mais
       completo que um filtro ingênuo por client_id sozinho.
    `LGPDConsentRecord` (tem `client_id`, mas nenhum endpoint grava
    linha nela hoje) e `ClientPortalAccess` (só token_hash/expiração,
    sem PII) auditados e confirmados como não-achado — registrado, não
    ligado, pra não virar susto numa rodada futura.
  - **B. Segurança do Portal via link — 3 achados reais, todos
    corrigidos e verificados empiricamente**:
    1. **CRÍTICO — papel CLIENT alcançava endpoints internos do
       escritório inteiro.** `tenant.router` e `system.router`
       (`app/api/v1/router.py`) eram os ÚNICOS 2 routers de negócio
       montados sem NENHUMA dependência de role — contrariando o
       próprio comentário do arquivo ("CLIENT só acessa /portal/* e
       /auth/*"). Achado pré-existente, mas a Fase 234 tornou "CLIENT"
       um crachá fácil de obter (só um link, sem senha) em vez de um
       papel raro (convite manual) — mesmo bug antigo, exploração muito
       mais fácil. Concretamente: `GET /system/analytics/financeiro`
       devolvia os números do escritório INTEIRO pra qualquer cliente
       com link de portal válido. Fix: `dependencies=_BLOCK_STAFF` nos
       2 routers (mesmo padrão de `clients.router`/`processes.router`/
       etc.). Confirmado via HTTP real: cliente com JWT de portal
       recebe 403 em `/system/analytics/financeiro`/`/tenant/theme`/
       `/system/health/detailed`/`/tenant/billing` (antes 200); ADMIN
       continua acessando tudo normalmente (sem regressão); `/portal/me`
       do mesmo cliente continua 200 (portal em si intacto); Playwright
       real confirma que o dashboard interno do staff carrega sem
       quebrar nada depois do fix.
    2. **ALTO — revogar não matava sessões de refresh já emitidas.**
       `gerar_portal_access`/`revogar_portal_access` nunca tocavam a
       tabela `sessions`. Sequência real: cliente resgata o link →
       ganha uma `Session` de refresh (até 7 dias) → admin revoga
       (`is_active=False`, bloqueia certo) → admin REGENERA um link
       novo (`is_active=True` de novo) → a `Session` antiga, que devia
       ter morrido na revogação, voltava a funcionar em `POST
       /auth/refresh` — alguém com o refresh token antigo conseguia
       token novo mesmo depois de "revogado". Fix: `revogar_portal_
       access` agora deleta todas as `Session` do `User` técnico no
       momento da revogação. Confirmado via HTTP real: refresh token
       capturado antes da revogação → revoga → refresh falha (401) →
       regenera um link novo → o refresh ANTIGO continua morto (401),
       mesmo depois da regeneração — fecha o cenário completo do
       achado, não só a revogação isolada.
    3. **BAIXO — corrida no 1º `POST /.../portal-access` virava 500
       cru.** Reproduzido uma vez com 2 chamadas concorrentes reais
       pro mesmo cliente pela 1ª vez: a 2ª batia na constraint única de
       `users.email` (e-mail sintético igual pras 2, já que o `User`
       técnico só existe no `else` de "não existe access ainda") ANTES
       de chegar na constraint de `client_id` do `ClientPortalAccess` —
       o `try/except` original só cobria o commit final, não essa
       falha mais cedo. Fix: `try/except IntegrityError` agora envolve
       a sequência inteira (criação do `User` + do `ClientPortalAccess`),
       devolvendo 409 limpo em vez de 500. Não foi possível forçar a
       mesma corrida de novo depois do fix (~18 tentativas concorrentes,
       incluindo chamada direta de função via `asyncio.gather` sem
       round-trip HTTP, todas OK sem conflito — janela de corrida
       estreita e nao-determinística) — confiança vem da leitura de
       código confirmando que o `try/except` agora envolve exatamente o
       ponto que quebrou antes, não de uma reprodução ao vivo do "antes
       vs. depois" idêntica.
  - **Reconfirmação independente** (nunca feita numa rodada de teste
    geral seguinte até agora): Fase 229 — probe de saúde do Celery
    reflete estado real (`celery.ok: true`, 1 worker, com Celery+Redis
    reais rodando de verdade, não fallback in-process) e o teste
    unitário do HITL (`requires_approval` zera quando o gate é o último
    passo) passa limpo. Fases 230-234 — Playwright real confirma que
    `/mapa`, o Timbrado auto/personalizado (Fase 232) e a aba Controle
    de Clientes (Fase 234) continuam funcionando sem erro de console
    depois de todas as correções acima.
  - Suíte `pytest` bateu na mesma flakiness de pool asyncpg/pytest-
    asyncio documentada desde a Fase 199 — reproduzida de novo mesmo
    isolando teste a teste, e cross-checada contra um arquivo de
    controle não tocado nesta fase (`test_crm_metas_fase213.py`, falha
    de forma idêntica) — não é regressão desta fase; verificação
    principal foi HTTP real contra Postgres/Redis/Celery reais, como em
    toda fase recente desta sessão.
- **Fase 236** — usuário reportou: clicar em "Gerenciar acesso ao
  Portal do Cliente" (botão "Portal" no Cliente 360) não abria o
  gerenciador — voltava pra tela de Clientes. Reproduzido ao vivo via
  Playwright logado como SUPERADMIN ANTES de mexer no código (mesma
  disciplina da sessão inteira — nunca assumir a causa só por leitura):
  confirmado que clicar no botão navega corretamente pra `/clientes?
  aba=controle-portal`, mas nem a aba nem o painel aparecem.
  **Causa raiz**: `frontend/src/app/(dashboard)/clientes/page.tsx`
  definia `const isAdmin = userRole === "ADMIN"` — comparação estrita,
  sem incluir `SUPERADMIN`. Essa variável gateia 4 pontos no mesmo
  arquivo, inclusive um `useEffect` de "defesa" que reverte
  `aba="controle-portal"` de volta pra `"clientes"` sempre que
  `!isAdmin` — é exatamente isso que descartava a navegação pro
  SUPERADMIN. Achado confirmado como inconsistência isolada, não
  intencional: o BACKEND (`require_role("ADMIN")`, usado pelos 3
  endpoints de portal-access e por `erase_client_data`) já trata
  SUPERADMIN como superconjunto de ADMIN (`app/dependencies.py`,
  comentário explícito: *"SUPERADMIN sempre passa"*), e TODO outro
  gate "ADMIN" do frontend já inclui SUPERADMIN — inclusive
  `canSeeLgpd`, 4 linhas acima no MESMO arquivo. `isAdmin` era a única
  exceção, introduzida na Fase 234 sem seguir o padrão já estabelecido.
  Fix: `isAdmin = userRole === "ADMIN" || userRole === "SUPERADMIN"`.
  Reconfirmado via Playwright real que a aba/painel aparecem agora pro
  SUPERADMIN, e que ADMIN comum continua funcionando sem regressão.
  `tsc --noEmit`/`eslint` limpos (1 warning pré-existente de
  `exhaustive-deps`, já documentado desde fases anteriores).
- **Fase 237** — rodada de teste geral (ambiente real: Postgres+Redis+
  Celery+uvicorn+frontend `npm run dev` com `API_URL` local, subidos de
  verdade). A última rodada de teste geral de verdade foi a Fase 235
  (achou/corrigiu na mesma rodada); a Fase 236 (fix pontual) nunca tinha
  passado por nenhuma rodada de teste geral. Reconfirmação conjunta,
  nunca feita numa única passada antes: os 5 fixes de LGPD da Fase 235
  (`User.full_name`/`Document`/`Contract`/`AgentRun`/
  `LegalProcess.descricao`, além dos 4 já reconfirmados em rodadas
  anteriores), `tenant.router`/`system.router` bloqueando CLIENT
  (`GET /system/analytics/financeiro`/`GET /tenant/theme` → 403),
  sessão de refresh morta na revogação de portal-access (revoga →
  `POST /auth/refresh` com o token antigo → 401; regenerar não
  ressuscita o token antigo), e o fix da Fase 236 (SUPERADMIN abre
  Controle de Clientes) — todos OK via HTTP real.
  - **Lacuna 1 fechada — a corrida em `gerar_portal_access` (Fase 235)
    finalmente provada ao vivo.** A própria Fase 235 nunca conseguiu
    reproduzir a corrida DEPOIS do fix (~18 tentativas, janela
    estreita) — a confiança vinha só de leitura de código. Desta vez,
    uma instrumentação TEMPORÁRIA (`asyncio.sleep(0.5)` logo após o
    `SELECT` de `ClientPortalAccess`, atrás de uma env var, revertida
    com `git checkout` antes de qualquer commit — nunca chegou a ficar
    no histórico do git) alargou a janela de corrida o suficiente pra
    20 chamadas HTTP verdadeiramente concorrentes (`asyncio.gather`)
    pro mesmo cliente pela 1ª vez confirmarem o mecanismo exato: como
    `pool_size=5`+`max_overflow=10` limita a 15 conexões simultâneas, 15
    requisições entram na corrida real (todas leem `access=None`) — 1
    vence o `INSERT` (`200`), 14 perdem com **409 limpo** (nunca 500) —
    e as 5 restantes, que ficaram na fila esperando uma conexão do pool
    livre, só chegam ao `SELECT` DEPOIS do vencedor já ter commitado,
    então corretamente veem a linha já existente e seguem pelo caminho
    de atualização (`200` também). Resultado: `{200: 6, 409: 14}`, zero
    500 — o fix da Fase 235 se sustenta sob concorrência real, não só
    por leitura de código.
  - **Lacuna 2 fechada — achado novo, real, confirmado empiricamente**:
    `erase_client_data` (LGPD, `lgpd.py`) sobrescreve `User.full_name`
    do usuário técnico oculto por trás do link de portal (fix da Fase
    235), mas **nunca toca `ClientPortalAccess` em si** — nem revoga,
    nem expira antecipadamente. Reproduzido de ponta a ponta: gerar
    link → capturar o token bruto → `DELETE /lgpd/clients/{id}/data`
    (esquecimento) → `POST /auth/portal-redeem` com o MESMO token
    capturado antes → **200, sessão nova emitida**, `GET /portal/me`
    funcional (mostrando o nome já anonimizado, mas o CANAL de acesso
    continua 100% vivo). Ou seja: um titular que exerceu o direito ao
    esquecimento, mas cujo link de portal vazou/foi salvo em algum
    lugar (e-mail, histórico do navegador, um bookmark), continua
    conseguindo logar no portal depois de "esquecido" — os dados
    mostrados já vêm anonimizados, mas a superfície de acesso em si não
    foi revogada. Já tinha sido registrado como "observação, decisão de
    escopo deliberada" na própria Fase 234 — nunca reavaliado numa
    rodada de teste geral desde então; reproduzido agora ao vivo confirma
    que é um achado real, não só uma decisão de design ainda válida.
  - **Isolamento cross-tenant do timbrado (Fase 232) — nunca testado
    explicitamente antes, veio limpo.** 2 tenants reais (`afj`/`demo`):
    mudar nome/endereço do timbrado de `afj` (incluindo o mecanismo de
    sincronização automática endereço↔timbrado) nunca vazou pro
    `GET /tenant/letterhead` do `demo`, e os 2 flags `_custom`
    (personalização manual) respeitados corretamente por tenant — um
    `PUT /tenant/endereco` subsequente no `demo` não sobrescreveu um
    campo do timbrado já marcado como personalizado, como esperado.
  - **Auditoria paralela adversarial** (2 `Agent`, sem bloqueio de plan
    mode desta vez):
    - **Segurança do Portal, 2ª leitura independente** — 2 achados reais
      confirmados via HTTP real, ambos a MESMA classe de violação do
      invariante "CLIENT só acessa `/portal/*` e `/auth/*`" já corrigida
      uma vez pra `tenant.router`/`system.router` na Fase 235, agora
      achada em mais 2 routers esquecidos:
      - **MÉDIO — `notifications.router`** montado só com `_BLOCK`
        (bloqueio de tenant suspenso), sem `_STAFF` — CLIENT recebe
        `200` em `GET /notifications` (confirmado com um token de
        portal real, via `portal-redeem`). Sem vazamento de dado ativo
        hoje (a query já é escopada por `current_user.id`, e nada no
        sistema cria `Notification` visando o `User` técnico do
        portal), mas viola o invariante documentado — mesmo padrão de
        risco que já foi crítico uma vez.
      - **BAIXO — `push.router`** no mesmo padrão (`_BLOCK` só). CLIENT
        recebe `201` em `POST /push/subscribe`. Self-scoped por
        `user_id`, sem exposição cross-tenant/cross-client hoje.
      - Confirmado limpo: os ~13 routers restantes (`_BLOCK_STAFF`
        correto), `tenants_admin`/`billing`/`reports_admin` (gate
        per-endpoint, CLIENT bloqueado), `ws.router`/`ai_oauth.router`/
        `integrations_hub` callback/webhook (públicos por desenho,
        motivo documentado), `portal.py` inteiro (isolamento por
        `client_id`+`tenant_id` em todos os 9 endpoints, testado
        cross-client dentro do mesmo tenant), e os endpoints novos desde
        a Fase 228 (`clients.py` portal-access ×3, `auth.py::portal-
        redeem`, `tenant.py::/endereco`) — isolamento cross-tenant
        confirmado limpo em todos.
    - **Walkthrough Playwright conjunto das telas 230-236** (nunca
      testadas todas juntas na mesma sessão de navegador antes) — as 7
      telas percorridas (login → `/mapa` → Timbrado auto/personalizado
      com F5 → criar/editar cliente PF → Controle de Clientes
      gerar/revogar → Cliente 360 sem aba Contatos → SUPERADMIN
      revendo Controle de Clientes) vieram **todas limpas, nenhuma
      regressão de interação** entre as fases.
  - Nenhuma correção foi feita nesta fase (metodologia padrão) —
    decisão do usuário sobre quais achados viram fase nova. **Próxima
    rodada deve**: se o achado 2 (`ClientPortalAccess` sobrevive ao
    esquecimento) for corrigido, reconfirmar com o mesmo teste de ponta
    a ponta usado aqui (gerar→capturar token→esquecer→tentar redeem de
    novo); se `notifications.router`/`push.router` ganharem `_STAFF`,
    reconfirmar que CLIENT passa a receber 403 nos dois, sem quebrar o
    fluxo de push/notificação do papel STAFF normal.
- **Fase 238** — implementação do achado LGPD×`ClientPortalAccess` da
  Fase 237, escolhido pelo usuário (o outro achado da mesma rodada,
  `notifications.router`/`push.router` sem `_STAFF`, ficou pra decidir
  depois). `erase_client_data` (`backend/app/api/v1/lgpd.py`) ganhou um
  bloco novo logo ao lado do já existente que sobrescrevia `User.
  full_name` (Fase 235) — reaproveita a MESMA lógica já usada em
  `revogar_portal_access` (`clients.py`): revoga o `ClientPortalAccess`
  (`revoked_at`), desativa o `User` técnico oculto (`is_active=False`)
  e mata toda `Session` de refresh já emitida pra ele. Fecha o canal de
  acesso por completo, não só o nome exibido — antes, o dado mostrado já
  vinha anonimizado, mas o link de portal capturado antes do
  esquecimento continuava resgatável depois. Verificado via HTTP real
  contra Postgres real, reproduzindo o cenário exato já confirmado pela
  Fase 237 (gerar link → capturar token bruto → redeem, guardando o
  refresh token → esquecer → tentar redeem de novo com o MESMO token →
  agora **401** (antes 200); a sessão já ativa antes do esquecimento
  também não sobrevive — `POST /auth/refresh` com o refresh token
  capturado antes → **401**; `GET /clients/portal-access` reflete
  `REVOGADO` depois do esquecimento (antes ficava `ATIVO` pra sempre).
  Confirmado sem regressão: cliente sem nenhum acesso ao portal
  continua sendo esquecido normalmente (bloco novo é no-op quando não
  há `ClientPortalAccess`), e `export_client_data` continua mostrando
  `acessos_portal` normalmente quando chamado antes do esquecimento
  (não tocado por esta fase — o achado era sobre o canal de acesso
  sobreviver, não sobre o que o export exibe). Teste automatizado novo
  (`test_lgpd_erasure_revokes_portal_access_fase238.py`, mesmo padrão
  HTTP real de `test_lgpd_erasure_reaches_crm_fase210.py`) bate na mesma
  flakiness de pool asyncpg/pytest-asyncio documentada desde a Fase 199
  — reproduzida de novo mesmo isolado, cross-checada contra o próprio
  `test_lgpd_erasure_reaches_crm_fase210.py` (arquivo de controle não
  tocado, falha de forma idêntica) — não é regressão desta fase;
  verificação principal via HTTP real contra o backend rodando, como em
  toda fase recente desta sessão. `ruff check`/`py_compile` limpos no
  único arquivo backend tocado.
- **Fase 239** — fecha o 2º achado da Fase 237, deixado em aberto na
  Fase 238 ("fica pra decidir depois"): `notifications.router`/
  `push.router` (`backend/app/api/v1/router.py`) eram os últimos 2
  routers de negócio ainda montados sem `_STAFF`, mesma classe do
  achado crítico já corrigido pra `tenant.router`/`system.router` na
  Fase 235 — CLIENT recebia `200`/`201` em `GET /notifications`/`POST
  /push/subscribe` em vez de ser bloqueado pelo invariante já
  documentado no topo do arquivo ("CLIENT só acessa `/portal/*` e
  `/auth/*`"). Fix de 2 linhas: os 2 routers passam de `dependencies=
  _BLOCK` pra `dependencies=_BLOCK_STAFF`. Verificado via HTTP real
  reproduzindo exatamente o cenário confirmado na Fase 237: CLIENT
  (gerado via link de portal real) agora recebe `403` nos dois; ADMIN
  continua acessando ambos normalmente (`GET /notifications` → `200`;
  `POST /push/subscribe` chega até a validação do corpo — `422` num
  payload de teste propositalmente malformado, confirmando que o
  bloqueio de papel não é mais o obstáculo); `/portal/me` do mesmo
  CLIENT continua `200` (sem bloqueio em excesso). Sem teste
  automatizado novo — mesmo precedente já usado pelo fix idêntico da
  Fase 235 (`tenant.router`/`system.router`), que também não ganhou um
  teste dedicado na época; verificação HTTP real é a prova principal,
  como em toda fase recente. `ruff check`/`py_compile` limpos no único
  arquivo tocado.
- **Diagnóstico de cadastros** — usuário pediu avaliação completa do
  sistema comparando com o Astrea (concorrente jurídico), buscando
  inovações/correções/aprimoramentos, com foco em revisar todas as
  telas de cadastro. Bloqueio técnico confirmado: este sandbox bloqueia
  egress pra `astrea.net.br` (CONNECT 403 "policy denial", mesma
  restrição já documentada nesta sessão pra gov.br/BrasilAPI/
  OpenStreetMap/www.afjadvogados.com) — sem acesso ao vivo ao
  concorrente. Usuário escolheu (via pergunta) seguir com avaliação por
  conhecimento geral de mercado (Astrea, Projuris, Legal One, SAJADV) +
  auditoria completa do próprio AFJ. 4 Explore agents levantaram
  factualmente as ~18 telas de cadastro do sistema (CRM/Cliente,
  Administrativo/Governança, Processos/Documentos/Financeiro,
  Publicações — esta última comparada ponto a ponto com um screenshot
  real do Astrea que o usuário enviou). 31 achados publicados como
  Artifact ("Diagnóstico de Cadastros AFJ") — cada um rotulado "achado
  de código" (fato, com arquivo:linha) ou "sugestão de mercado" (opinião
  informada, sem verificação ao vivo). Nenhuma correção nesta fase — só
  o relatório. Nota de segurança registrada: usuário colou a senha do
  Astrea em texto puro no chat; nunca foi usada (bloqueio de rede), mas
  registrado o aviso de trocá-la. Usuário pediu, na sequência, pra
  transformar TODOS os 31 achados em fase de correção — dividido em 6
  sub-fases (240-245) pelo mesmo padrão já usado nesta sessão pra lotes
  grandes (Fase 205-208): 240 (achados ALTA + quick wins), 241
  (window.confirm/prompt + cadastros incompletos), 242 (vínculos e
  uploads faltando), 243 (máscaras + calculadora de prazo unificada +
  senha temporária), 244 (features maiores com design próprio), 245
  (importação em lote + faturamento do escritório + feriados
  nacionais).
- **Fase 240** (batch 1 dos 31 achados do diagnóstico de cadastros —
  achados ALTA + quick wins de baixo risco):
  - **Área do Direito incompleta** — a lista de Área do Direito estava
    duplicada e divergente em 5 lugares do frontend (`processos/novo`,
    `processos/page.tsx` ×2 — um deles com "EMPRESARIAL", que nem
    existe no backend e quebraria o save com 422 —, `agentes/page.tsx`,
    `FinanceiroCharts.tsx`), a maioria com só 6 das 10 áreas que o
    backend aceita. Nova fonte única
    (`frontend/src/lib/constants.ts::AREAS_DIREITO`), os 5 lugares
    passaram a importar dela. `processos/[id]/page.tsx`: "Área do
    Direito" no modal de edição virou `<select>` controlado (era
    `<input>` de texto livre, permitindo dado sujo tipo "Cível" vs.
    "CIVIL"). Decisão deliberada: "Tribunal" NÃO virou select nesse
    mesmo modal — a lista de tribunais do frontend é comprovadamente
    incompleta (só 41 dos ~92 tribunais brasileiros) e, ao contrário de
    Área do Direito, não é um enum fechado no backend; forçar um select
    ali quebraria a edição de qualquer processo com tribunal fora da
    lista.
  - **CPF/CNPJ duplicado** — `create_client`/`update_client`
    (`backend/app/api/v1/clients.py`) ganharam
    `_documento_ja_cadastrado()` (mesmo caminho decifra-e-compara já
    usado em `GET /clients/match`, Fase 181 — os campos são cifrados
    com IV aleatório, `UNIQUE` no banco nunca pegaria a duplicata) —
    bloqueia com 409 antes de criar/editar um cliente com CPF/CNPJ já
    cadastrado no tenant, exceto o próprio registro sendo editado.
    Frontend: `salvarCliente`/`salvarEdicao` passam a mostrar o
    `detail` real do erro em vez da mensagem genérica.
  - **`Client.observacoes` sem UI** — campo já existia no banco/schema
    e até era carregado no estado de edição, mas nenhum input o
    exibia. `ClienteFormFields.tsx` ganhou o textarea; `FORM_VAZIO`/
    `editValues` (`clientes/page.tsx`) passam o campo adiante.
  - **`Client.segmento` write-only** — classificado por um agente de IA
    (crm_agent, Fase 151) mas nunca aparecia em tela nenhuma. Cliente
    360 ganhou uma linha "Segmento" nos Dados Cadastrais (já vinha na
    resposta da API, só faltava exibir).
  - **Prazo fatal sem destaque visual** — `data_fatal` era gravada mas
    a Agenda calculava cor/urgência só por `data_prazo`; um prazo fatal
    amanhã e um prazo comum amanhã apareciam idênticos. Agora a Agenda
    usa a data mais urgente entre as duas pra colorir o card
    (`diasGovernante`) e mostra um selo "FATAL · DD/MM/AAAA" quando
    `data_fatal` existe.
  - **Ações em lote: reatribuir responsável** — o backend
    (`POST /processes/bulk-update`) já aceitava `responsavel_id` desde
    a Fase 207.3 ("fica pra quando fizer sentido adicionar"), só nunca
    tinha sido ligado na UI. `processos/page.tsx` ganhou um select de
    colega (`GET /users/colegas`, mesmo endpoint já usado em
    `processos/novo`) na barra de ações em lote, ao lado do já
    existente select de situação — qualquer um dos dois (ou os dois
    juntos) habilita o botão "Aplicar".
  - Verificado via HTTP real contra Postgres real: CPF duplicado (com
    formatação diferente, "529.982.247-25" vs "52998224725") bloqueado
    com 409 e mensagem certa; editar o próprio registro com o mesmo CPF
    continua funcionando (exclusão do próprio id da checagem);
    `AMBIENTAL` aceito na criação de processo (já era aceito pelo
    backend, confirma que o fix é puramente de UI); bulk-update sem
    regressão. Playwright real (Chromium do sandbox, `npm run dev` com
    `API_URL` local): select de Área do Direito com as 10 opções
    corretas; campo Observações presente no modal Novo Cliente; select
    "Reatribuir responsável" aparece na barra de lote ao selecionar
    processos; um prazo de teste com `data_fatal` amanhã e `data_prazo`
    daqui a 20 dias renderizou com borda vermelha (urgência do fatal, não
    do prazo comum) e o selo "FATAL · 29/08/2026" — confirma que
    `diasGovernante` funciona como projetado, não só por leitura de
    código. `tsc --noEmit` limpo; `eslint` nos 10 arquivos tocados — 4
    warnings pré-existentes de `exhaustive-deps`, confirmados via `git
    stash` como idênticos antes desta fase (só linha deslocada). `ruff
    check`/`py_compile` limpos no backend.
  - Não implementados nesta fase: os 24 achados restantes do
    diagnóstico — seguem pras Fases 241-245, já planejadas acima.
- **Fase 241** (batch 2 dos 31 achados do diagnóstico de cadastros —
  `window.confirm`/`window.prompt` nativos + 3 cadastros incompletos):
  - **`window.confirm`/`window.prompt` nativos** — o levantamento original
    citou 4-5 exemplos, mas um grep completo achou **11 pontos** no total
    (mais que o diagnóstico documentou, mesmo padrão sendo a mesma classe
    de achado). Novo hook único baseado em Promise
    (`frontend/src/hooks/useConfirmDialog.tsx`, `ask()` → `Promise<string
    | null>`, `null` = cancelado) substitui todos os 11: revogar acesso ao
    portal (`ClientPortalAccessPanel.tsx`), rejeitar agente de IA
    (`BrainCustomAgents.tsx`), desconectar integração
    (`integracoes/page.tsx`), restaurar versão/arquivar documento
    (`documentos/page.tsx` ×2), excluir parte de processo
    (`processos/[id]/page.tsx`), excluir processo permanentemente
    (`processos/page.tsx`), ativar modo produção do tenant
    (`admin/escritorios/page.tsx`), excluir usuário permanentemente
    (`admin/usuarios/page.tsx`), e motivo de oportunidade perdida
    (`clientes/funil/page.tsx` — fecha também o achado específico "motivo
    de perda via `prompt()`, sem estrutura"). Achado colateral corrigido
    de propósito: o `window.prompt` de rejeição de agente de IA ignorava
    cancelamento (clicar "Cancelar" no prompt nativo ainda rejeitava o
    agente, só sem motivo) — o modal novo torna "Cancelar" cancelar a
    rejeição inteira, mais alinhado com o que um admin esperaria.
  - **Campo `resolucao` da denúncia sem UI** — já existia no backend
    (`ReportResolve.resolucao`, endpoint já aceitava), só faltava o
    input. `etica/page.tsx` ganhou um textarea por relato com botão
    "Salvar resolução" (só aparece quando o texto diverge do já salvo).
  - **Membros do Comitê como texto livre** — viravam string separada por
    vírgula, sem checagem contra colaboradores reais. Agora é uma lista
    de checkboxes (`GET /users/colegas`, mesmo endpoint já usado em
    Processos), armazenando os mesmos nomes de sempre (sem migração de
    schema — `membros` continua `list[str]` no backend), só que
    escolhidos de uma lista real em vez de digitados.
  - **`ClientContact` sem WhatsApp próprio** — o comentário do próprio
    código admitia: "stored in telefone if no dedicated column". Novo
    campo `ClientContact.whatsapp` (migração idempotente em
    `events.py`), `create_contact`/`update_contact` gravam os 2 campos
    separadamente. Achado colateral descoberto ao investigar: `_contact_
    to_dict()` já devolvia `"whatsapp": c.whatsapp` numa fase anterior,
    o que teria quebrado com `AttributeError` toda listagem de contato
    até este fix adicionar a coluna que faltava no model — confirma que
    a coluna estava mesmo faltando, não só um problema cosmético de UI.
    Cliente 360 ganhou a exibição do WhatsApp na lista de contatos (link
    `wa.me`), que já era coletado no formulário mas nunca exibido.
  - Verificado via HTTP real contra Postgres real: contato criado com
    telefone E whatsapp preservados como campos distintos (antes um
    sobrescrevia o outro); resolução de denúncia salva e devolvida
    corretamente. Playwright real (Chromium do sandbox): modal de
    confirmação aparece ao revogar acesso (não mais `window.confirm`);
    campo "Resolução / parecer" presente por relato; "Membros
    participantes" renderiza como lista de checkboxes com colegas reais
    (6 no tenant de teste). `tsc --noEmit` limpo; `eslint` nos 16
    arquivos tocados — só os mesmos warnings pré-existentes de
    `exhaustive-deps`, confirmados via `git stash`. `ruff check`/
    `py_compile` limpos no backend.
  - Não implementados nesta fase: os 21 achados restantes — seguem pras
    Fases 242-245.
- **Fase 242** (batch 3 dos 31 achados do diagnóstico de cadastros —
  vínculos e uploads faltando). Antes desta fase, o usuário pediu uma
  auditoria dos conectores MCP conectados à conta em busca de
  oportunidades de melhoria pro sistema — investigação (`ListConnectors`
  + testes reais de Vercel/Sentry/Lawve AI) concluiu que nenhum
  conector tinha uma integração genuína e executável disponível além do
  Legal Data Hunter (já integrado nos 2 skills de jurisprudência):
  Vercel sem acesso ao projeto real do AFJ nesta sessão (mesmo bloqueio
  já documentado nas Fases 199/230), Sentry/Lawve AI/Canva/Descript sem
  autorização completada (fora do alcance de sessão não-interativa), e
  os demais (Gmail/Drive/Calendar/Microsoft 365/etc.) são contas
  pessoais da sessão, não credenciais do AFJ — usá-las regrediria a
  arquitetura já correta (OAuth por tenant). Achado técnico relevante:
  Legal Data Hunter é um servidor MCP exposto só a sessões do Claude
  Code, não uma API REST com credencial própria que o backend Python em
  produção (Railway) possa chamar como já faz com CNJ DataJud/SERPRO/
  BrasilAPI — sem isso, integrá-lo no `jurisprudence_agent` de produção
  criaria código morto. Usuário optou por seguir direto pra Fase 242.
  - **242.1 — `FinancialEntry` sem vínculo de cliente/processo na UI**:
    o model já tinha `client_id`/`process_id` (usados em relatórios como
    `honorarios-historico`, Fase 215), só o formulário
    (`financeiro/page.tsx`) não oferecia os campos. Modal "Novo
    Lançamento" ganha 2 selects (Cliente/Processo, o 2º filtrado pelo
    cliente escolhido via `GET /processes?client_id=`) — só na criação,
    já que `PUT /financial/{id}` nunca aceitou esses 2 campos (decisão
    de escopo: não expandido, edição de vínculo não fazia parte do
    pedido). **Achado colateral corrigido**: `FinanceiroSchema`
    (`frontend/src/lib/schemas.ts`) tinha um campo `processo_id` que
    nunca batia com o `process_id` que o backend sempre esperou —
    inofensivo até agora porque nunca era enviado, mas teria quebrado o
    vínculo silenciosamente se alguém tentasse usá-lo antes deste fix.
  - **242.2 — Sem seleção de cliente na criação de processo**:
    `POST /processes` já aceitava `client_id` desde sempre
    (`ProcessCreate.client_id`), só a tela `processos/novo/page.tsx` não
    oferecia — só dava pra vincular depois, via Parte. Novo select
    "Cliente" (mesmo padrão de fetch de `GET /clients?limit=200` já
    usado em `faturas/page.tsx`/`clientes/funil/page.tsx`).
  - **242.3 — Upload de documento single-file**: `documentos/page.tsx`
    ganha `multiple` no input e `uploadDocs()` (upload sequencial, um
    POST por arquivo no mesmo endpoint de sempre — sem mudança de
    backend), com progresso "Enviando X de N..." no próprio botão e
    toast final resumindo quantos de quantos tiveram sucesso.
  - **242.4 — Bases de conhecimento do agente de IA hardcoded 2×**:
    `ProposeCustomAgentModal.tsx` e `BrainCustomAgents.tsx` mantinham
    cópias manuais de `VALID_COLLECTIONS` (`backend/app/api/v1/rag.py`)
    — mesma classe de risco já corrigida pra Área do Direito na Fase
    240. Novo `GET /rag/collections` (`get_current_user`, lista não é
    sensível) devolve a lista real; novo
    `frontend/src/lib/ragCollections.ts` centraliza só os RÓTULOS de
    exibição (nunca o conjunto de valores, que sempre vem do backend).
    `BrainCustomAgents.tsx` também trocou o campo de texto livre
    separado por vírgula (editar um agente já aprovado) pelo mesmo
    padrão de botões-toggle do modal de propor — evita o mesmo tipo de
    divergência silenciosa de nome de collection na edição.
  - **242.5 — OAB sem validação de formato**: `JuridicoTab.tsx`
    (OABs monitoradas do escritório) ganhou uma checagem de sanidade
    (3-7 dígitos) antes de aceitar uma OAB nova — a OAB não tem
    dígito verificador público/padronizado como CPF/CNPJ (confirmado:
    não existe algoritmo de DV documentado pela entidade), então o
    código e a UI deixam explícito que é só checagem de formato, nunca
    fingindo uma garantia de dígito verificador que não existe.
  - **242.6 — Stripe/Mercado Pago sem teste de credencial**:
    `integracoes/page.tsx` tinha `TESTAVEIS` sem os 2 gateways de
    pagamento, mesmo o botão "Testar" já existindo pra outras fontes.
    `integration_hub.py::testar_conexao` ganhou um caminho novo
    (`_testar_payment_gateway`) — sonda GET read-only autenticada
    (Stripe `/v1/balance`, Mercado Pago `/users/me`, mesmo padrão
    "401/403 = credencial ruim" já usado pras fontes credenciadas),
    sem reaproveitar a abstração `FonteProcessual` (que é de
    acompanhamento processual, não pagamento — não fazia sentido
    encaixar ali). Verificado real via HTTP: sem credencial → 
    `DESCONECTADA`; com uma chave forjada → o próprio egress deste
    sandbox bloqueia a chamada a `api.stripe.com` (mesma restrição já
    documentada desde a Fase 217/230/231 pra domínios externos) — o
    código captura a exceção corretamente e marca `ERRO` sem crashar,
    mas a distinção real "credencial inválida vs. sandbox sem egress"
    só pode ser confirmada depois do deploy (Railway tem egress
    irrestrito).
  - Verificado via HTTP real contra Postgres real: `/rag/collections`
    devolve as 7 collections certas; processo criado com `client_id` já
    vinculado na criação; lançamento financeiro criado com
    `client_id`/`process_id` persistidos; `GET /processes?client_id=`
    filtra corretamente. Playwright real (Chromium do sandbox, `npm run
    dev` com `API_URL` local): selects de Cliente/Processo presentes no
    modal financeiro e em Processos/novo; upload real de 2 arquivos PDF
    simultâneos confirma "2 de 2 arquivos enviados."; aviso "sem dígito
    verificador" presente na tela de OABs; card Stripe com botão testar
    visível em Integrações — zero console error atribuível a esta fase
    (só o warning de key duplicada pré-existente em `/dashboard`, já
    documentado em fases anteriores, não relacionado). `ruff check`/
    `py_compile` limpos nos 2 arquivos backend tocados; `tsc --noEmit`
    limpo; `eslint` nos 9 arquivos frontend tocados — só os mesmos 3
    warnings pré-existentes de `exhaustive-deps`, confirmados via `git
    stash` como idênticos antes desta fase.
  - Não implementados nesta fase: os 15 achados restantes — seguem pras
    Fases 243-245.
- **Fase 243** (batch 4 dos 31 achados do diagnóstico de cadastros —
  máscaras de input, calculadora de prazo unificada, senha temporária).
  - **Máscaras de digitação** — `frontend/src/lib/masks.ts` (novo:
    `maskCpf`/`maskCnpj`/`maskTelefone`/`maskCep`, puramente cosmético,
    nunca valida dígito verificador — isso já existe no backend desde a
    Fase 217/220/240) aplicado nos campos que só tinham placeholder
    estático: `ClienteFormFields.tsx` (CPF/CNPJ/telefone/WhatsApp/CEP),
    `EscritorioZone.tsx` (CEP do endereço do escritório),
    `PersonalZone.tsx` (telefone/WhatsApp do próprio usuário), e o
    modal "Novo Contato" do Cliente 360 (campos `type="tel"`).
  - **Calculadora de prazo unificada** — novo
    `frontend/src/components/prazos/PrazoCalculator.tsx` substitui as 2
    cópias manuais (`processos/[id]/page.tsx` e `agenda/page.tsx`), que
    tinham campos divergentes: a de Agenda não oferecia nenhum jeito de
    sugerir `data_fatal` (só a do processo sugeria, desde a Fase 240),
    então um prazo lançado direto pela Agenda nunca ganhava o destaque
    visual de prazo fatal. `agenda/page.tsx` ganhou o campo "Data fatal
    (opcional)" que faltava, fechando a divergência funcional, não só a
    duplicação de código.
  - **Senha temporária** — novo `User.must_change_password` (migração
    idempotente em `events.py`), setado `True` nos 3 pontos que geram
    senha temporária (`POST /users/invite`, `POST /users/{id}/reset-
    password`, provisionamento de escritório em `tenants_admin.py`) e
    zerado em `PATCH /auth/password` quando a troca é bem-sucedida.
    `POST /auth/login` devolve o flag no objeto `user`; o login do
    frontend redireciona direto pra `/configuracoes?zona=pessoal&aba=
    seguranca` (em vez de `/dashboard`) quando `must_change_password`
    é `true`, e a aba Segurança mostra um aviso persistente até a senha
    ser trocada — não é enforcement de middleware (nenhuma rota fica
    bloqueada), é um prompt visível no fluxo, como pedia o achado do
    diagnóstico. Os 3 endpoints que geram senha temporária agora
    tentam mandar por e-mail primeiro (mesmo padrão já existente no
    convite de usuário — `EMAIL_ENABLED`, fail-soft) e só expõem a
    senha em texto puro no JSON quando o e-mail não está configurado
    (o caso deste sandbox) — antes, o reset de senha e o provisionamento
    de escritório sempre expunham em texto puro, mesmo com e-mail
    disponível. **Achado colateral descoberto e corrigido nesta mesma
    fase**: `POST /users/invite` nunca tinha esse fallback — sem
    `EMAIL_ENABLED` (like agora), o convite não expunha a senha em
    lugar nenhum (nem e-mail, nem JSON) e o modal do frontend
    (`admin/usuarios/page.tsx`) ficava preso na tela do formulário vazio
    sem nenhuma confirmação de sucesso, porque `tempPwd` vinha sempre
    `undefined`. Corrigido com o mesmo padrão de fallback dos outros 2
    pontos + um estado `invitedByEmail` no frontend pra cobrir os 2
    casos.
  - Verificado via HTTP real contra Postgres real: fluxo completo
    convite→reset→login (confirma `must_change_password: true`)→troca
    de senha→relogin (confirma `must_change_password: false`);
    provisionamento de escritório (SUPERADMIN real) também confirma o
    flag `true` no primeiro login do ADMIN novo. Playwright real
    (Chromium do sandbox, `npm run dev` com `API_URL` local): máscaras
    aplicadas em tempo real (CPF "123.456.789-01", telefone "(85)
    99999-8888", CEP "80030-901"); calculadora presente tanto em
    Processos quanto em Agenda, com o campo "Data fatal" novo na
    Agenda; login com senha temporária redireciona pra Segurança com o
    aviso "Você está com uma senha temporária..." visível; modal de
    convite mostra "Usuário criado!" corretamente nos 2 casos (e-mail
    configurado vs. fallback). `ruff check`/`py_compile` limpos nos 5
    arquivos backend tocados; `tsc --noEmit` limpo; `eslint` nos 11
    arquivos frontend tocados — só os mesmos warnings pré-existentes de
    `exhaustive-deps`/`no-img-element`, confirmados via `git stash`
    como idênticos antes desta fase.
  - Não implementadas nesta fase: as 11 propostas restantes (Fases
    244-245).
- **Fase 244** (batch 5 dos 31 achados do diagnóstico de cadastros —
  features maiores, design próprio). Investigação prévia (1 Explore
  agent, 5 frentes) confirmou que cada uma tinha um esforço bem
  diferente do que a leitura inicial do diagnóstico sugeria — escopo
  ajustado por item, documentado abaixo, sem tentar a versão maximal de
  nenhuma.
  - **244.1 — sugestão de IA em Publicações, agora pré-computada**: antes
    a única sugestão de IA (tipo/dias de prazo) só existia sob demanda,
    dentro do modal de triagem, nunca persistida. Novo
    `Intimacao.prioridade_ia`/`resumo_ia`/`classificado_em` (migração
    idempotente) + `app/services/publicacao_prioridade.py` (novo,
    classificação ALTA/MEDIA/BAIXA + resumo curto via LLM, mesmo padrão
    de `jurisprudencia_sync.py::classificar_acordao` — chave central do
    servidor, sem `user_ai_creds()`, já que é job periódico sem usuário
    específico) chamado dentro de `scan_publicacoes`
    (`app/services/dje_monitor.py`) uma vez por intimação capturada,
    fail-soft (falha na classificação de 1 intimação não derruba a
    varredura inteira). Frontend: badge de prioridade + resumo já na
    listagem (`publicacoes/page.tsx`), sem precisar abrir o modal —
    mesmo padrão citado no diagnóstico como diferencial do Astrea.
  - **244.2 — assinatura eletrônica multi-signatário**: `esign.py::
    enviar_para_assinatura` aceitava só 1 e-mail/nome fixo; agora recebe
    `signatarios: list[{email, nome}]` e cria N signatários no MESMO
    documento/envelope Clicksign (a API já suporta isso nativamente,
    não precisou de N documentos). `POST /contracts/{id}/enviar-
    assinatura` aceita a lista nova, mantendo `email`/`nome` soltos como
    fallback de compatibilidade (nunca chamado pelo frontend novo, mas
    evita quebrar uma integração externa que ainda mande no formato
    antigo). Disparo automático na aprovação de contrato (Fase 192)
    também migrado (1 signatário — o cliente vinculado — dentro de uma
    lista de 1). Frontend (`contratos/page.tsx`): formulário vira lista
    de linhas com adicionar/remover, mínimo 1.
  - **244.3 — lançamento financeiro parcelado**: `FinancialEntry` ganha
    `grupo_recorrencia_id`/`parcela_atual`/`parcela_total` (migração +
    índice idempotentes). Decisão de design: todas as parcelas nascem
    JUNTAS na criação (`POST /financial` com `parcelas: int`), cada uma
    um `FinancialEntry` independente (editável/cancelável isolada) —
    nunca um job periódico "gerando a próxima depois", mais simples e
    mais previsível. `valor` informado é o de CADA parcela; vencimentos
    espaçados de 1 mês via `dateutil.relativedelta` (já era dependência
    do projeto). Frontend: campo "Parcelas" no modal de lançamento, só
    na criação (PUT continua sem esse campo, como já era).
  - **244.4 — meta de captação por mês futuro**: o backend (`POST/GET
    /crm/metas`, Fase 213) já aceitava qualquer período sem trava — só
    a UI do funil estava presa no mês atual. Navegação de mês (◀ ▶) no
    widget de meta (`clientes/funil/page.tsx`), sem mudança de schema.
    Decisão de escopo deliberada: meta "por equipe/responsável"
    (exigiria `CrmMeta` ganhar `responsavel_id` + mudar a
    `UniqueConstraint`) fica de fora — mudança de schema maior, não
    pedida com a mesma urgência no diagnóstico original.
  - **244.5 — dupla aprovação (HITL) na promoção a ADMIN/SUPERADMIN**:
    único achado do diagnóstico envolvendo a trilha HITL — promover
    alguém a ADMIN/SUPERADMIN era 1 clique de um único ADMIN, a única
    ação sensível do sistema sem o padrão de aprovação em 2 etapas já
    usado em petição/contrato/agente customizado. `PUT /users/{id}`
    agora cria um `Approval(tipo="USER_ROLE_CHANGE")` PENDENTE em vez de
    aplicar a mudança direto quando o papel muda PRA ADMIN/SUPERADMIN
    (demoção/desativação continuam imediatas — não é o risco que este
    achado mirava); a mudança de role real só acontece em
    `execute_approved_action` (novo branch), após aprovação de outro
    ADVOGADO/SOCIO/ADMIN via `/aprovacoes` — reaproveita a infra de
    `Approval` sem nenhuma mudança na tela de Aprovações (`tipo` já é
    renderizado genericamente). Limitação conhecida, não corrigida
    (documentada, não é regressão desta fase): nada impede o mesmo
    ADMIN que solicitou de resolver a própria aprovação — mesma
    limitação já presente no HITL de petição/contrato, não introduzida
    aqui.
  - Verificado via HTTP real contra Postgres real: fluxo completo de
    troca de role (role NÃO muda antes da aprovação, muda só depois);
    meta de período futuro (2027-03) criada e lida corretamente;
    `/publicacoes` devolve `prioridade_ia` no schema; lançamento com
    `parcelas=3` gera exatamente 3 `FinancialEntry` com descrições
    "(1/3)"/"(2/3)"/"(3/3)" e vencimentos 1 mês espaçados; envio de
    contrato pra 2 signatários chega até o guard de Clicksign não
    configurado (mesma limitação de sandbox sem credencial real já
    documentada pra Stripe/Mercado Pago na Fase 242 — comportamento só
    confirmável 100% pós-deploy). Verificação adicional com mocks reais
    (Postgres real, `call_llm` e `buscar_comunicacoes` monkeypatchados):
    `scan_publicacoes` persiste `prioridade_ia`/`resumo_ia`/
    `classificado_em` de ponta a ponta a partir de uma intimação
    simulada. Playwright real (Chromium do sandbox, `npm run dev` com
    `API_URL` local): badge "⚡ ALTA PRIORIDADE" + resumo renderizados
    na listagem de Publicações (screenshot confirma visualmente);
    campo Parcelas presente no modal financeiro; navegação de mês no
    funil avança corretamente (agosto → setembro); botão de assinatura
    presente em Contratos; aprovação `USER_ROLE_CHANGE` aparece
    normalmente na aba Resolvidas — zero console error novo. `ruff
    check`/`py_compile` limpos nos 11 arquivos backend tocados (+ 2
    arquivos de teste ajustados pra nova assinatura de
    `enviar_para_assinatura`); `tsc --noEmit` limpo; `eslint` nos 6
    arquivos frontend tocados — só warnings pré-existentes de
    `exhaustive-deps` (incluindo 1 novo do mesmo tipo, esperado por ter
    dividido 1 `useEffect` em 2 no funil), confirmados via `git stash`.
  - Não implementadas nesta fase: as 3 propostas do batch 6 (Fase 245 —
    importação em lote, faturamento do escritório, feriados forenses
    nacionais), últimas do diagnóstico de cadastros original.
- **Fase 245** (batch 6 — último dos 6 batches do diagnóstico de
  cadastros, fecha os 31 achados originais da Fase 203/237).
  - **245.1 — importação em lote (CSV)**: nenhuma tela de cadastro tinha
    isso; Cliente é o candidato mais comum de onboarding em massa
    (migração de outro sistema). Novo `POST /clients/importar-csv`
    (`ADMIN/SOCIO/GESTOR`, teto de 1000 linhas) — CSV com cabeçalho
    (`nome_completo` obrigatório; `tipo`/`cpf_cnpj`/`email`/`telefone`/
    `origem` opcionais, `tipo` inferido pela quantidade de dígitos do
    documento quando ausente). Decisão de escopo deliberada: não
    geocodifica endereço nem chama SERPRO por linha (custaria N chamadas
    de API externa numa importação de centenas de linhas) — isso
    continua disponível editando cada cliente depois, como já
    funcionava. Dedup reaproveita a mesma lógica decifra-e-compara de
    `_documento_ja_cadastrado` (Fase 240), mas pré-carregada 1x (não 1x
    por linha, senão seria O(linhas × clientes já cadastrados)) e cobre
    tanto duplicata contra o banco quanto duplicata DENTRO do próprio
    arquivo. Nenhuma linha ruim derruba a importação inteira — cada uma
    é reportada individualmente (criado/duplicado/erro). Frontend
    (`clientes/page.tsx`): botão "Importar CSV" + modal de resultado com
    contagem e detalhe por linha.
  - **245.2 — faturamento do escritório**: `GET /tenant/billing`
    (existia) só mostra o status ATUAL da assinatura; o histórico de
    pagamentos (`TenantPayment`, já existia) só era visível numa tela
    SUPERADMIN-only de gestão de TODOS os escritórios
    (`GET /billing/{tenant_id}/payments`). Novo `GET /tenant/billing/
    historico` (`ADMIN/SOCIO` do próprio tenant) — mesmo dado, mesma
    tabela, escopado ao próprio tenant. Frontend (`admin/plano/
    page.tsx`): tabela de histórico logo abaixo do card "Assinatura &
    Cobrança" já existente, só aparece quando há pagamentos registrados.
  - **245.3 — feriados forenses nacionais visíveis**: `app/utils/
    prazo.py::feriados_nacionais()` (fixos + móveis + recesso) já era
    usado automaticamente no cálculo de todo prazo do sistema desde
    sempre, mas nunca aparecia em lugar nenhum da UI — o escritório não
    tinha como conferir o que já é considerado antes de cadastrar um
    feriado local (`/feriados`, que já existia). Novo `GET /tenant/
    feriados-nacionais?ano=` (somente leitura — são fixos por lei
    federal, nada aqui é configurável pelo escritório) devolve a lista
    computada + o intervalo do recesso. Frontend (`JuridicoTab.tsx`):
    lista read-only logo abaixo do form de feriados locais, no mesmo
    card, deixando claro a distinção entre o que é fixo e o que é
    configurável.
  - Verificado via HTTP real contra Postgres real: CSV de 4 linhas (1
    nome vazio, 1 duplicata de CPF entre linhas do próprio arquivo) →
    2 criados, 1 duplicado, 1 erro, exatamente como esperado; `GET
    /tenant/billing/historico` responde vazio sem erro pro tenant de
    teste (sem `TenantPayment` cadastrado); `GET /tenant/feriados-
    nacionais?ano=2026` devolve os 12 feriados nacionais brasileiros de
    2026 + recesso 20/12/2026–20/01/2027, batendo com o calendário real.
    Playwright real (Chromium do sandbox, `npm run dev` com `API_URL`
    local, screenshots capturados): botão "Importar CSV" funcional
    (upload real de arquivo, modal de resultado renderiza "1 Criados"
    corretamente); card "Assinatura & Cobrança" intacto em Plano & Uso;
    feriados nacionais de 2026 visíveis e bem integrados visualmente na
    aba Jurídico de Configurações — zero console error novo (só o
    warning de key duplicada pré-existente em `/dashboard`, não tocado
    nesta fase, já documentado desde a Fase 219). `ruff check`/
    `py_compile` limpos nos 2 arquivos backend tocados; `tsc --noEmit`
    limpo; `eslint` nos 3 arquivos frontend tocados — só os mesmos
    warnings pré-existentes de `exhaustive-deps`, confirmados via `git
    stash`.
  - **Fecha os 31 achados do diagnóstico de cadastros** (Fase 203/237 →
    Artifact "Diagnóstico de Cadastros AFJ" → 6 batches, Fases 240-245)
    — todos implementados e verificados empiricamente, nenhum adiado sem
    registro explícito de decisão de escopo.
- **Fase 246** — rodada de teste geral (audit-only, usuário escolheu via
  pergunta "Nova rodada de teste geral" após o merge do PR #236, sem
  pedir correção nesta mesma rodada). Primeira rodada conjunta desde a
  Fase 237 — as Fases 238-245 (LGPD×portal, bloqueio de CLIENT em
  notifications/push, e os 6 batches do diagnóstico de cadastros) nunca
  tinham sido reconfirmadas juntas nem auditadas de fora, cada uma só
  verificada isoladamente no momento da própria implementação.
  - **Reconfirmação conjunta via HTTP real (nunca feita numa única
    passada)**: Fase 238 (esquecimento LGPD revoga `ClientPortalAccess`
    + mata `Session` — redeem e refresh falham depois de esquecer),
    Fase 239 (CLIENT bloqueado em `/notifications`/`/push`, STAFF e o
    portal em si intactos), Fase 240 (CPF/CNPJ duplicado bloqueado com
    409, área AMBIENTAL aceita), Fase 241 (`Report.resolucao` grava,
    `ClientContact.whatsapp` separado de `telefone`), Fase 242
    (`GET /rag/collections` com as 7 collections certas, `client_id`
    vinculado na criação de processo/lançamento, teste de credencial
    Stripe não crasha), Fase 243 (ciclo completo de
    `must_change_password`: convite→reset→login força o flag→troca→
    relogin limpa), Fase 244 (lançamento com `parcelas=3` gera 3 linhas,
    `PUT /users/{id}` promovendo a ADMIN cria `Approval` e só aplica
    após `POST /approvals/{id}/resolve`), Fase 245 (CSV de 4 linhas →
    2 criados/1 duplicado/1 erro exatamente como esperado,
    `GET /tenant/billing/historico` e `GET /tenant/feriados-nacionais`
    respondendo certo) — todas OK, sem achado.
  - **Lacuna fechada — interação entre features do mesmo lote** (nunca
    testada antes, cada fase só validou suas próprias mudanças
    isoladas): (1) cliente criado via `POST /clients/importar-csv`
    (Fase 245) recebe um lançamento financeiro parcelado (Fase 244,
    `parcelas=2`) vinculado por `client_id`, e o esquecimento LGPD
    (Fase 238) funciona nele normalmente — sem achado; (2) um usuário
    convidado com `must_change_password=True` (Fase 243) pode ser alvo
    de uma promoção de role via HITL (Fase 244) mesmo antes de trocar a
    senha — a promoção aplica normalmente (`ADMIN` confirmado após
    `resolve`), os 2 flags são independentes (`must_change_password`
    continua `True` até o usuário efetivamente trocar a senha, mesmo já
    promovido), e o ciclo de troca de senha segue funcionando sem
    interferência do HITL — sem achado; (3) contrato multi-signatário
    (Fase 244, `POST /documents/contracts/{id}/enviar-assinatura`) e o
    disparo automático de assinatura no branch de aprovação de contrato
    (`execute_approved_action`, Fase 192) são caminhos de código
    **estruturalmente independentes**, confirmado por leitura direta:
    o branch automático (`_tentar_envio_automatico_assinatura`,
    `app/services/approval.py`) sempre monta sua própria lista de
    1 signatário a partir do `Client` vinculado, nunca lê nem depende de
    qualquer lista de signatários que o endpoint manual da Fase 244
    tenha recebido — não há estado compartilhado entre os 2 caminhos
    pra uma interação de verdade acontecer; `enviar-assinatura` também
    não passa por nenhum gate HITL (ação direta do ADMIN).
  - **3 lacunas de verificação explicitamente sinalizadas, todas
    fechadas**: `GET /publicacoes` filtra por tenant corretamente
    (confirmado com 2 tenants reais, zero cruzamento, inclusive nos
    campos novos `prioridade_ia`/`resumo_ia`); `POST /users/{id}/
    reset-password` cross-tenant devolve `404` (não vaza senha
    temporária de usuário de outro tenant); `notifications`/`push`
    escopados por `current_user.id` confirmados sem vazamento — usuário
    do tenant demo não vê nenhuma notificação semeada no tenant afj.
  - **Auditoria paralela adversarial** (3 `Agent`, sem bloqueio de plan
    mode desta vez):
    - **Frente A — isolamento cross-tenant, 14 alvos** (4 rotas
      genuinamente novas + 10 pontos de lógica nova das Fases 238-245,
      testados com HTTP real e 2 tenants reais) — **14/14 PASS, zero
      vazamento**. Cobriu, entre outros: `importar-csv`,
      `billing/historico`, esquecimento LGPD cross-tenant (404, não
      500/200), `client_id`/`process_id` forjados de outro tenant no
      `POST /financial` (422, rejeitado — não aceito silenciosamente),
      `enviar-assinatura` em contrato de outro tenant (404), promoção
      de role HITL cross-tenant (404, `Approval` não vaza pra fora do
      tenant certo), `reset-password` cross-tenant (404, sem senha
      vazada), teste de credencial de integração isolado por tenant.
    - **Frente B — LGPD, alcance das superfícies novas das Fases
      244-245** — **2 achados novos confirmados empiricamente (não
      hipótese de leitura de código), 6ª ocorrência da mesma classe de
      bug já fechada 5x antes (176.3→210→220→228→235→238)**:
      - **`Intimacao.texto`/`resumo_ia`/`prioridade_ia` (Fase 244)
        sobrevivem ao esquecimento.** `Intimacao` não tem `client_id`
        próprio, mas carrega PII em texto livre (a publicação em si +
        o resumo gerado por IA) e tem vínculo indireto via
        `process_id → LegalProcess.client_id`. `lgpd.py` nunca
        referencia `Intimacao` (confirmado por grep, zero hits).
        Reproduzido de ponta a ponta: processo com `client_id` do
        titular → intimação com nome/CPF tagueados no `texto`/
        `resumo_ia` → `DELETE /lgpd/clients/{id}/data` →
        `GET /publicacoes` continua devolvendo o texto/resumo
        ORIGINAIS, intocados.
      - **`Contract.assinaturas` criado via `POST /contracts/create`
        (caminho manual) sobrevive ao esquecimento E some do export.**
        `lgpd.py` já sabe scrubar `Contract.assinaturas` (JSONB com
        nome/e-mail de signatário) — mas só alcança o contrato via
        `Document.client_id → Contract.document_id`. O endpoint manual
        de criação de contrato (`POST /contracts/create`, base da tela
        de Contratos e do fluxo de assinatura multi-signatário da Fase
        244) cria o `Document` com `client_id=NULL` e seta
        `Contract.client_id` diretamente — as 2 FKs divergem.
        Reproduzido: contrato criado por esse caminho, PII de
        signatário plantada diretamente no Postgres (simulando o que
        `esign.py::enviar_para_assinatura` grava — sem credencial
        Clicksign real neste sandbox, mesma limitação documentada desde
        a Fase 217/242) → esquecimento roda sem erro, mas
        `contracts.assinaturas` permanece com o nome/e-mail original
        intacto, e `GET /lgpd/clients/{id}/export` devolve
        `"contratos": []` pra esse contrato (invisível também na
        portabilidade, não só na anonimização). **Nuance confirmada**:
        o caminho de contrato gerado por IA (`contract_agent.py`) já
        seta `Document.client_id` corretamente — o gap é específico do
        endpoint manual.
    - **Frente C — walkthrough real via Playwright, sessão contínua**
      cobrindo as 11 telas tocadas nas Fases 240-245 numa única sessão
      de navegador (nunca feito — cada fase só testou suas próprias
      telas isoladas) — **todas as verificações PASS, zero regressão de
      interação**. Confirmou ao vivo, entre outros: badge "FATAL" com
      destaque visual na Agenda, barra de ações em lote com
      "Reatribuir responsável", os 11 pontos de `window.confirm`/
      `prompt` nativos da Fase 241 permanecem 100% substituídos pelo
      modal customizado (`page.on('dialog')` monitorado a sessão
      inteira — **zero diálogo nativo disparado**, incluindo em telas
      fora da lista original de exemplos), lista de bases de
      conhecimento do agente de IA vindo de `GET /rag/collections`
      (não mais hardcoded), aviso da OAB corretamente rotulado como
      "só checagem de formato" (sem prometer dígito verificador que não
      existe). Console limpo — só o warning de key duplicada
      pré-existente em `/dashboard` (documentado desde a Fase 219, não
      relacionado) e o log esperado do próprio 409 de CPF duplicado
      (tratado corretamente pela UI com um toast, não um crash).
  - Nenhuma correção de código foi feita nesta fase (metodologia
    padrão audit-only) — decisão do usuário sobre quais dos 2 achados
    de LGPD (ou ambos) viram fase de correção. **Próxima rodada deve**:
    se os 2 achados forem corrigidos, reconfirmar com o mesmo padrão
    criar→embutir PII→esquecer→conferir usado aqui; considerar, dado que
    esta é a 6ª ocorrência da mesma classe de bug, se vale a pena um
    mecanismo estrutural (ex.: um teste/lint que force toda tabela nova
    com qualquer vínculo a `client_id` — direto ou indireto via FK
    encadeado — a aparecer numa lista central que `lgpd.py` precisa
    cobrir) em vez de continuar corrigindo caso a caso pela 7ª vez no
    futuro — pergunta já repetida sem resposta definitiva desde a Fase
    219/228.
- **Fase 247** — implementação dos 2 achados de LGPD confirmados na Fase
  246, a pedido do usuário ("Continue" após o relatório).
  - **`Intimacao.texto`/`.resumo_ia`** (`backend/app/api/v1/lgpd.py`) —
    novo bloco em `erase_client_data`/`export_client_data` que junta
    `Intimacao` com `LegalProcess` via `process_id` e reaproveita
    `client_linked_processes_filter` (Fase 222, já usado pra
    `LegalProcess.descricao` — cobre `client_id` direto E via
    `ProcessParty`). `numero_cnj`/`tribunal`/`orgao`/`link` NÃO são
    tocados — identificam o processo em si, mesmo espírito de preservar
    `numero_processo`/`tribunal` do `LegalProcess`, só o texto livre
    (`texto`/`resumo_ia`) é PII. Export ganha a seção `intimacoes`.
  - **`Contract.assinaturas` via `POST /contracts/create`** (caminho
    manual, `backend/app/api/v1/documents.py`) — 2 frentes. Raiz do
    problema: esse endpoint criava o `Document` com `client_id=NULL` e só
    setava `Contract.client_id` diretamente (o único dos 2 caminhos de
    criação de contrato com essa divergência — o gerado por IA já setava
    `Document.client_id` corretamente), quebrando a cadeia
    `Document.client_id → Contract.document_id` que `lgpd.py` usa pra
    achar o contrato. Corrigido a propagar `client_id` (já validado por
    `_validar_client_id`) pro `Document` também — fecha a causa raiz pra
    contratos novos. Mas como este projeto nunca faz backfill de dado
    legado (mesma decisão já tomada pra outros dados históricos, ex.
    geocodificação de clientes na Fase 233), contratos manuais já
    existentes continuariam com `Document.client_id=NULL` pra sempre —
    por isso `lgpd.py` (`erase_client_data`/`export_client_data`) também
    ganhou alcance por OR: `Document.client_id` direto OU o `Document` de
    um `Contract` cujo `client_id` bate — cobre os 2 caminhos de vínculo,
    sem depender do fix de criação sozinho.
  - Testes novos
    (`test_lgpd_erasure_reaches_intimacao_contract_fase247.py`, mesmo
    padrão HTTP real de `test_lgpd_erasure_reaches_crm_fase210.py`) batem
    na mesma flakiness de pool asyncpg/pytest-asyncio documentada desde a
    Fase 199 — reproduzida de novo mesmo isolada, cross-checada contra o
    próprio `test_lgpd_erasure_reaches_crm_fase210.py` (arquivo de
    controle não tocado, falha de forma idêntica) — não é regressão desta
    fase. Verificação principal via HTTP real contra Postgres real
    (uvicorn reiniciado nesta sessão pra carregar o código novo),
    reproduzindo os 2 cenários exatos que a Fase 246 usou pra confirmar
    cada achado (criar→embutir PII→esquecer→conferir), **mais um 3º
    cenário só pra provar o fallback por OR**: um contrato criado pelo
    endpoint já corrigido, com `Document.client_id` forçado de volta a
    `NULL` direto no Postgres (simulando uma linha legada de antes deste
    fix) — confirmado que o esquecimento ainda alcança tanto o corpo do
    `Document` quanto `Contract.assinaturas` nesse cenário, sem depender
    do fix de criação sozinho. `ruff check`/`py_compile` limpos nos 3
    arquivos tocados (2 backend + 1 teste novo).
  - **Mecanismo estrutural não implementado nesta fase** (pergunta
    repetida desde a Fase 219/228, reaberta pela Fase 246) — decisão
    deliberada de não construir um teste/lint genérico agora; ficou só
    registrado, não resolvido, pra não expandir o escopo do pedido do
    usuário ("Continue" após o relatório, não um pedido de tooling novo).
    Continua valendo a pena considerar numa fase futura dedicada, já que
    esta é a 6ª ocorrência confirmada da mesma classe de lacuna.
- **Fase 248** — usuário pediu uma missão ampla (25 seções): analisar,
  corrigir, evoluir e simplificar a área de "Integrações", com foco em
  UX pra um administrador não-técnico, segurança de credenciais,
  arquitetura, e avaliação de novas APIs. Investigação completa (3
  Explore agents em paralelo — backend `integration_hub.py`, frontend
  `integracoes/page.tsx`+`admin/health/page.tsx`, e segurança/webhooks/
  sync/testes — mais 1 Plan agent pra desenhar a implementação) mapeou
  os 10 provedores já registrados no hub (stripe, mercadopago,
  clicksign, whatsapp, pdpj, escavador, judit, jusbrasil,
  google_drive_doutrina, google_workspace) — credenciais sempre
  cifradas (Fernet) e escopadas por tenant, exposição de credencial
  confirmada segura (nenhum endpoint devolve segredo cru/mascarado).
  Usuário confirmou (via 2 perguntas): (1) focar em corrigir/evoluir os
  10 provedores já existentes nesta fase, sem pesquisar/adicionar
  provedor novo — os mais valiosos pro mercado jurídico brasileiro já
  estão cobertos (mesma conclusão já documentada desde a Fase 217/242);
  (2) as 4 sub-fases completas do plano abaixo numa única sessão.
  - **248.1 — segurança & correção**:
    - **Assinatura HMAC nos webhooks de stripe/mercadopago**
      (`backend/app/services/webhook_signature.py`, novo) — camada
      ADICIONAL sobre a re-verificação real já existente (nunca a
      substitui); settings opcionais `STRIPE_WEBHOOK_SECRET`/
      `MERCADOPAGO_WEBHOOK_SECRET`, skip silencioso se não configurado
      (senão quebraria o webhook de todo tenant já conectado no
      instante do deploy). Verificado via HTTP real: assinatura
      válida/inválida/header ausente pros 2 provedores, os 5 cenários
      se comportando exatamente como esperado.
    - **Achado colateral crítico, corrigido na hora**: `receive_webhook`
      (`backend/app/api/v1/integrations_hub.py`) tinha um bug
      pré-existente — `log.info(..., event=...)` colide com a chave
      interna que o structlog já usa pro nome do evento de log,
      estourando `TypeError` em **toda** chamada. Bug nunca pego antes
      porque nenhum teste/tráfego real tinha batido nessa rota até
      agora (confirma exatamente o que a Fase 246 já tinha achado:
      "zero teste exercita o webhook receiver"). Corrigido renomeando
      pra `tipo_evento`.
    - **Fecha o gap do `testar_conexao`** pra clicksign/
      google_drive_doutrina/google_workspace — generaliza
      `_PAYMENT_TEST_PROBE`/`_testar_payment_gateway` (Fase 242) num
      `_GET_TEST_PROBE`/`_testar_via_get` reutilizável cobrindo os 3
      (Clicksign: query param, mesmo esquema de `esign.py`; Google
      Drive: `drive/v3/about`; Google Workspace: `oauth2/tokeninfo`).
      **Achado ao vivo durante a verificação**: `tokeninfo` do Google
      devolve HTTP 400 — não 401/403 — pra token inválido (confirmado
      contra a API real do Google); `_GET_TEST_PROBE` ganhou um
      `invalid_status` por provedor pra cobrir isso sem generalizar o
      400 pros outros (onde 400 pode significar outra coisa).
    - **`disconnect()` preserva `extra_data`** — trocou
      `db.delete(integ)` por limpar só `credentials_enc`/`status`/
      `connected_at`/`connected_by`/timestamps, mantendo a linha e
      `extra_data` (ex.: `folder_id` do Drive) intactos; reconectar
      reaproveita a config anterior. `list_status()` passou a derivar
      `DESCONECTADA` por `credentials_enc` vazio (não só por
      `integ.status`), já que a linha agora sobrevive ao disconnect.
    - **Gate SUPERADMIN no modal de diagnóstico**
      (`admin/health/page.tsx`) — reaproveita o sinal que a página já
      tem (200 vs. qualquer outra coisa em `/system/brain/infra`,
      já `SUPERADMIN`-only) pra decidir se pode citar nome de variável
      de ambiente cru (`REDIS_URL`, `SMTP_HOST`, `SENTRY_DSN`) — página
      é reachable por ADMIN/SOCIO também, que agora recebem mensagem
      genérica em português. Verificado via Playwright real com os 2
      papéis.
  - **248.2 — testes reais do caminho financeiro**: novo
    `backend/tests/test_api/test_integrations_webhooks.py` — ciclo
    completo stripe/mercadopago (connect→fatura→emitir→payment-link→
    webhook→PAGA→FinancialEntry, replay idempotente, session mismatch
    rejeitado) + lifecycle clicksign (connect→status→test→disconnect),
    mesmo padrão de mock só do HTTP de saída já usado no projeto
    (`monkeypatch.setattr(<módulo>.httpx, "AsyncClient", ...)`). Suíte
    bate na mesma flakiness de pool asyncpg/pytest-asyncio documentada
    desde a Fase 199 (cross-checada contra `test_invoices.py`, arquivo
    de controle não tocado, falha de forma idêntica) — verificação
    principal via script standalone no mesmo processo (mesmo workaround
    já usado nas Fases 202/209), confirmando os 3 cenários (confirmação
    + FinancialEntry único mesmo após replay + session mismatch
    rejeitado, fatura não vira PAGA) diretamente contra Postgres real.
  - **248.3 — UX compartilhada & mensagens amigáveis**:
    - **`friendly_detail()`** (`integration_hub.py`) — tradução por
      padrão regex (credencial inválida/timeout/OAuth expirado/escopo
      insuficiente/resposta inesperada) pra mensagem curada em
      português + fallback honesto que nunca inventa causa. `detail`
      cru continua sendo salvo/logado (auditoria/suporte) — a tradução
      é aditiva. Novos campos `detail_friendly` (`testar_conexao()`) e
      `last_error_friendly` (`list_status()`), consumidos no toast/
      banner de `integracoes/page.tsx` no lugar do texto técnico cru.
    - **`<StatusBadge>` compartilhado**
      (`frontend/src/components/integrations/StatusBadge.tsx`, novo) —
      só extrai o mapeamento tom→cor (a peça genuinamente idêntica
      entre os 2 usos); **não** virou um `<IntegrationCard>` genérico,
      já que o card do hub inteiro (connect/test/disconnect/toggle) não
      tem equivalente no `ModuleCard` de 6 linhas do health — forçar um
      componente único exigiria 10+ props opcionais de comportamento, a
      abstração não-usada que este projeto evita. 2 variantes visuais
      (`pill` no hub, `label` no health) preservam o visual já existente
      de cada página — confirmado sem regressão via Playwright
      (screenshot antes/depois nas 2 páginas).
  - **248.4 — polish & honestidade de UI**: removido o card "Backup
    Automático" (`admin/health/page.tsx`, sempre `"planejado"` por
    construção, nunca refletia dado real, ao lado de tiles de fato
    monitorados); "Progresso do Projeto" ganhou uma legenda
    ("Marco estático do roadmap — não é um indicador de saúde ao vivo");
    Google Workspace ganhou uma disclosure curta de "quais dados serão
    acessados" (Gmail send-only, Calendar events, Drive file-scope —
    grounded nos escopos OAuth reais registrados, não uma alegação
    genérica) no pré-consentimento, distinta do checklist de features já
    existente.
  - **Explicitamente fora desta fase** (decisão deliberada, documentada
    no plano): abstração `Provider` genérica (duplicação é de forma, não
    de lógica compartilhável real entre os 4 módulos vendor — revisitar
    só se um 3º/4º provedor do mesmo formato de pagamento/esign surgir);
    HMAC do Clicksign (aposta financeira menor, mecanismo de assinatura
    não confirmado com certeza, re-verificação já fecha o gap sozinha);
    `DROP TABLE google_integrations` (tabela órfã da Fase 139, inerte,
    zero risco); qualquer mudança em `AIProviderConfig.tenant_id`
    (subsistema BYOK-IA separado, fora do hub); pesquisa de provedor
    novo (confirmado com o usuário).
  - `ruff check`/`py_compile` limpos nos 6 arquivos backend tocados
    (incluindo o teste novo); `tsc --noEmit`/`eslint` limpos nos 3
    arquivos frontend tocados. Verificação principal via HTTP real
    contra Postgres+Redis+Celery+uvicorn reais (stack subida do zero
    nesta sessão, container tinha sido reiniciado) + Playwright real
    (Chromium do sandbox) após cada sub-fase, nunca só leitura de código.
- **Fase 249** — usuário colou um log de produção mostrando o Celery em
  crash-loop havia ~16h (desde o deploy do PR #236):
  `[AFJ][WARN] Processo Celery morreu — religando…` repetindo a cada
  ~10s, sempre com `ModuleNotFoundError: No module named
  '${{a61c37ce-...'`. Investigação (1 Explore agent, read-only)
  confirmou que **não havia bug de código**: `worker.py`/`config.py`
  passam `CELERY_RESULT_BACKEND`/`CELERY_BROKER_URL` direto de
  `Settings` pro `Celery(...)`, com fallback simples pra `REDIS_URL`
  quando vazio — nenhuma interpolação/templating em lugar nenhum do
  repo. O `${{...}}` cru só podia ter vindo de uma variável do painel
  do Railway contendo uma referência `${{ServiceName.VAR}}` que não
  resolveu — essas 3 variáveis são secrets de runtime configurados só
  na plataforma (já documentado acima), fora do alcance desta sessão.
  **Usuário corrigiu a variável quebrada no painel do Railway por conta
  própria** — não fez parte desta fase.
  - **Nota de correção**: uma investigação inicial (Plan agent) alegou
    que `backend/railway.toml`/`backend/Dockerfile` não invocavam
    `start.sh` (procurando em caminhos que não existem) — **verificado
    diretamente e descartado**: `railway.toml`/`Dockerfile` (raiz do
    repo, não dentro de `backend/`) já tinham `startCommand`/`CMD`
    apontando pra `sh start.sh` corretamente, exatamente como este
    próprio CLAUDE.md já documentava. Fica registrado como lembrete de
    sempre verificar diretamente uma alegação de subagente antes de
    confiar nela, mesmo quando soa plausível.
  - **O que esta fase resolveu**: por que o crash-loop passou
    despercebido por 16h. O watchdog do Fase 227 (`backend/start.sh`)
    religava o Celery a cada morte sem NUNCA distinguir um blip
    transitório (se recupera na religada) de uma config permanentemente
    quebrada (crasha em bem menos de 1s, sempre) — e sem soar alarme
    nenhum. Como só o `uvicorn` é observado pelo healthcheck do
    Railway, o deploy inteiro aparecia "successful" enquanto toda a
    `beat_schedule` (alertas de prazo, agentes de IA, sync de
    jurisprudência, capturas periódicas) ficava morta em silêncio.
    Achado adicional: `backend/app/workers/tasks/infra_check.py`
    (Fase 164) já faz esse tipo de alerta pra SUPERADMIN — mas É UMA
    TASK DO PRÓPRIO CELERY BEAT, então nunca dispara exatamente quando
    o Celery/beat é o que está quebrado. Por isso a checagem nova entra
    no watchdog do shell (fora do Celery), não em Python/Celery-land.
  - **`start.sh`** ganhou detecção de crash-loop: `CELERY_START_TS`
    grava quando o Celery sobe; se morrer antes de
    `CELERY_MIN_HEALTHY_SECONDS` (default 45s — folga confortável acima
    do boot legítimo do Celery, que importa 14 módulos de `include=
    [...]` antes de conectar), incrementa `CELERY_FAST_DEATH_COUNT`
    (zera se sobreviver além disso); ao atingir
    `CELERY_CRASHLOOP_THRESHOLD` (default 3) mortes rápidas seguidas,
    chama `maybe_alert_crashloop()`. Todos os thresholds são
    configuráveis por env var (mesmo padrão de opcionalidade de
    `CELERY_CONCURRENCY`). **Cuidado de implementação**: `start.sh` tem
    `set -e` na 1ª linha valendo pro script inteiro — `maybe_alert_
    crashloop()` sempre termina com `return 0` e é chamada com `||
    echo ...` por precaução extra, senão uma falha no envio do alerta
    derrubaria o watchdog inteiro (regressão bem pior que o bug sendo
    corrigido).
  - **Anti-spam**: marcador de timestamp em `/tmp/afj_celery_crashloop_
    alert.ts` (mesmo diretório gravável já usado pelo bloco
    `MIGRATE_FROM_URL`) — só reenvia depois de
    `CELERY_ALERT_COOLDOWN_SECONDS` (default 1h) desde o último alerta
    real, tratando arquivo ausente/valor não-numérico como "nunca
    alertou".
  - **`backend/app/scripts/alert_celery_crashloop.py`** (novo, +
    `__init__.py`) — invocado via `timeout 20 python3 -m app.scripts.
    alert_celery_crashloop "$N"`. Reaproveita só primitivas já
    existentes: `AsyncSessionLocal` (já falha rápido, `connect_
    args={"timeout": 5}`), `notification.create_batch(..., tipo=
    "INFRA_ALERTA", ...)` — `"INFRA_ALERTA"` já era um tipo válido em
    `TIPOS_VALIDOS` e já estava fora do mapa de opt-out por preferência
    (sempre notifica, sem toggle pro usuário desativar), e
    `email.send_email(..., db=db, tenant_id=None)` — `tenant_id=None`
    pula deliberadamente os branches de Gmail-Workspace/tenant-demo
    (ambos condicionados a `tenant_id is not None`), caindo direto no
    SMTP genérico, certo pra um alerta de plataforma inteira. Público:
    `User.role == "SUPERADMIN", is_active=True` — mesmo padrão já usado
    por `infra_check.py` pra esse tipo de alerta infra-wide (não o
    padrão per-tenant de `_notify_integration_error`, que é sobre
    credencial de 1 tenant, problema diferente). Ambos os canais
    (in-app + e-mail) — notificação in-app sozinha tem o mesmo ponto
    cego que causou as 16h sem ninguém notar (ninguém logado no
    painel); e-mail é o canal que escapa desse ponto cego. Cada etapa
    isolada em try/except própria — nunca deixa uma exceção virar
    traceback que trava o watchdog.
  - **Fora de escopo, deliberado**: Sentry como canal adicional (já
    integrado no projeto, `SENTRY_DSN`, ganho bônus barato — mas não
    substitui o e-mail, já que é outro dashboard que alguém precisa
    estar observando, o mesmo ponto cego do incidente original);
    framework de alerta genérico; retry/backoff no envio (se falhar,
    loga e a próxima tentativa, ainda protegida pelo cooldown, tenta de
    novo); diagnosticar qual variável específica está quebrada a partir
    do shell (o traceback do próprio Celery já mostra isso nos logs);
    monitoramento de recursos genérico (memória/CPU/disco).
  - **Verificado ao vivo, ponta a ponta, contra Postgres+Redis reais**
    (não só leitura de código): rodou `start.sh` de verdade localmente
    com `CELERY_RESULT_BACKEND='${{broken-service-id-reference}}'`
    (reproduzindo o exato padrão do incidente real) e thresholds
    reduzidos pra teste (`CELERY_MIN_HEALTHY_SECONDS=20`,
    `CELERY_CRASHLOOP_THRESHOLD=3`) — confirmado que o alerta NÃO
    dispara na 1ª nem na 2ª morte rápida, dispara exatamente na 3ª
    ("Celery crash-loop detectado (3x mortes rápidas seguidas)"), e
    que a 4ª/5ª/6ª mortes subsequentes corretamente logam "já alertado"
    sem reenviar (cooldown funcionando); confirmado via consulta direta
    no Postgres que exatamente 1 `Notification` nova foi criada por
    essa rodada (não duplicada pelas tentativas suprimidas pelo
    cooldown); confirmado que o watchdog sobrevive tanto a um envio de
    alerta bem-sucedido quanto a uma falha forçada do script (testado
    separadamente com `DATABASE_URL` também quebrada — o script loga em
    stderr e sai limpo, `set -e` nunca derruba o loop); confirmado que
    o `trap`/shutdown gracioso (Fase 227) continua funcionando sem
    regressão. **Achado de teste, não de produto**: o watchdog só faz
    polling a cada 10s (`sleep 10` no loop), então `RAN_FOR` nunca é
    medido abaixo de ~10s mesmo pra uma morte instantânea — thresholds
    de teste abaixo dessa granularidade (a 1ª tentativa usou 5s) dão
    falso-negativo silencioso (todas as mortes leem `RAN_FOR≈10s`,
    nunca contam como rápidas); o default de produção (45s) já tem
    folga suficiente acima dessa granularidade, não precisa de ajuste.
  - `ruff check`/`py_compile` limpos nos 2 arquivos novos; revisão
    manual cuidadosa do `start.sh` (`sh -n`/`dash -n` confirmam sintaxe
    válida no shell exato de produção — sem `shellcheck` disponível
    neste sandbox, mesma limitação já documentada desde a Fase 227).
- **Fase 250** — usuário reportou (com screenshot) que "Varrer agora" em
  `/publicacoes` devolvia `HTTP 403 da Comunica/DJEN` em **produção**
  (não é o bloqueio de egress deste sandbox — Railway tem egress
  irrestrito, o 403 veio do próprio servidor do PJe). Achado real:
  `backend/app/integrations/dje/comunica.py` mandava um User-Agent que
  se autoidentifica como sistema (`AFJ-Core/1.0 (Sistema interno de
  escritorio de advocacia)`, mesmo padrão de `tribunais/base.py`) — a
  Fase 114 tinha trocado o UA genérico do httpx por esse justamente pra
  resolver uma rejeição anterior (teste `test_comunica_diagnostico.py`
  documentava isso), mas o WAF do Comunica/DJEN evoluiu e passou a
  rejeitar também um UA que se autoidentifica como bot/sistema, só
  aceitando tráfego que pareça vir de um navegador — o mesmo formato
  que o próprio site público `comunica.pje.jus.br` usa pra chamar essa
  API (é uma API pública pensada pra consumo de terceiros, não um
  endpoint privado — mandar um UA de navegador aqui é o mesmo formato
  de requisição que qualquer usuário faria pela página de consulta
  pública, não uma técnica de evasão). Fix: `buscar_comunicacoes()`
  passa a mandar `User-Agent` (Chrome/Windows), `Accept-Language:
  pt-BR,...` e `Referer`/`Origin: https://comunica.pje.jus.br` —
  simulando a mesma origem que o site público real usa. Teste
  `test_requisicao_envia_user_agent_de_navegador` (renomeado do antigo
  `test_requisicao_envia_user_agent_identificado`, que agora
  explicitamente assertava o comportamento ultrapassado) reescrito pra
  confirmar os 4 headers novos e a ausência do UA antigo — os outros 4
  testes do arquivo (403/500/exceção de rede/sucesso, todos sobre
  `stats["status_code"]`/`stats["error"]`, Fase 114) continuam válidos
  sem mudança. **Limitação de verificação, documentada como em toda
  fase anterior que mexeu numa fonte pública brasileira**: este sandbox
  bloqueia egress pra `comunicaapi.pje.jus.br` no nível do próprio
  proxy da sessão (`curl` direto devolve `CONNECT tunnel failed,
  response 403` — um bloqueio ANTES de qualquer pacote chegar ao
  servidor real do PJe, diferente do 403 relatado pelo usuário, que veio
  do servidor de verdade) — não foi possível confirmar ao vivo, nesta
  sessão, que o novo conjunto de headers realmente destrava o 403 real.
  A confiança vem de: (a) o padrão documentado de WAFs de portais `.jus.br`
  rejeitarem clientes não-navegador só por header, sem fingerprint TLS
  real por trás; (b) os 5 testes automatizados (Postgres não necessário,
  só `httpx.MockTransport`) confirmando que os headers corretos saem na
  requisição. **Próximo passo real**: usuário reabrir "Varrer agora" em
  produção depois do deploy deste fix e confirmar se o 403 sumiu — se
  persistir, a causa mais provável muda de "header rejeitado" pra
  "IP do Railway bloqueado pelo WAF" (não resolvível por código, exigiria
  contato com o suporte do PJe/CNJ ou um canal de integração formal) ou
  um rate-limit temporário (a mensagem de erro já sugere "tente
  novamente mais tarde" como próxima tentativa antes de escalar).
  `tribunais/base.py` usa o mesmo UA autoidentificado
  (`AFJ-Core/1.0`) pras 4 fontes REST puras (PDPJ/Escavador/Judit/
  Jusbrasil) — **não tocado nesta fase** (fora do escopo do achado
  reportado, sem evidência de que essas fontes estejam com o mesmo
  problema); se alguma delas apresentar 403 similar em produção, é
  candidato ao mesmo fix.
- **Fase 251** — usuário reportou (sem screenshot desta vez) que "captura
  de processos" e "captura de publicações" aparentemente não estavam
  funcionando, pedindo um plano de análise e correção até o funcionamento
  pleno. Investigação (leitura direta de código) traçou as duas features
  até a raiz: **compartilham 100% do mesmo cliente HTTP de descoberta**
  (`buscar_comunicacoes`, `backend/app/integrations/dje/comunica.py`) —
  "captura de publicações" (`scan_publicacoes`, `dje_monitor.py`) chama
  essa função diretamente; "captura de processos"
  (`capturar_por_oab`, `oab_capture.py`) chama a mesma função por baixo
  de `ComunicaFonte.descobrir_por_oab()`. Ou seja, o fix da Fase 250 (headers
  de navegador contra o 403 do WAF do Comunica/DJEN, já mergeado minutos
  antes desta mensagem) já deveria ter corrigido as DUAS ao mesmo tempo —
  esta fase não encontrou nenhuma causa independente de 403 pra nenhuma
  das duas.
  - **Achado novo, real, corrigido nesta fase**: `ComunicaFonte.
    descobrir_por_oab()` (`backend/app/integrations/fontes/
    comunica_fonte.py`) era o **único** lugar em todo o código que
    implementava o circuit breaker manualmente (`allow()`/
    `record_success()`/`record_failure()` direto), em vez de usar
    `self._breaker.run(...)` como as outras 9 fontes do projeto
    (confirmado por grep completo de todo `_breaker\.` do repositório).
    `run()` é o que hidrata/persiste o estado no Redis (mecanismo da Fase
    166, para o painel Cérebro — processo web — enxergar falhas
    registradas pelo worker Celery). Como `ComunicaFonte` é um singleton
    por processo (`fontes/registry.py`), esse breaker específico nunca
    sincronizava com o Redis — o painel "Fontes da Captura" nunca
    refletia falhas reais de Comunica vistas pelo worker (não é a causa
    do 403 relatado, mas comprometia a única forma de o usuário confirmar
    "está funcionando" sem depender de tentativa manual). Fix:
    `circuit_breaker.py` ganha 2 métodos públicos finos
    (`sincronizar_de_redis()`/`sincronizar_para_redis()`, só chamando os
    já existentes `_hidratar()`/`_persistir()`); `comunica_fonte.py`
    passa a chamá-los antes do `allow()` e depois de
    `record_success()`/`record_failure()` — sem mudar o sinal de sucesso/
    falha em si (que continua vindo de `stats`, já que
    `buscar_comunicacoes` nunca lança, então não dava pra usar `run()`
    direto).
  - **Investigado e descartado como causa adicional**: o enriquecimento
    de processos via DataJud (`_enriquecer_via_datajud`, dentro de
    `capturar_por_oab`) usa `tribunais/cnj.py` — Elasticsearch REST
    autenticado por API key (`CNJ_API_KEY`, com valor público padrão já
    embutido em `config.py`, não depende de credencial por tenant),
    `api-publica.datajud.cnj.jus.br`, superfície tecnicamente diferente
    do Comunica (API de máquina, não portal de consulta pública com WAF
    anti-bot). `tribunais/base.py` (usado por essa e mais 4 fontes
    credenciadas) segue com o UA antigo — decisão da própria Fase 250 de
    não mexer sem evidência concreta continua valendo; revisitar se o
    usuário trouxer evidência real de 403 numa dessas fontes
    especificamente.
  - **Verificado ao vivo** (Postgres+Redis reais deste sandbox — egress
    real pra `comunicaapi.pje.jus.br`/`api-publica.datajud.cnj.jus.br`
    continua bloqueado no nível do proxy da sessão, mesma limitação da
    Fase 250, então `buscar_comunicacoes` foi monkeypatchada; o teste
    exercita o PIPELINE inteiro, não a rede em si): cenário de sucesso —
    `capturar_por_oab()` cria `LegalProcess` novo, `scan_publicacoes()`
    cria `Intimacao` nova, os dois com `SyncRun` fechando `OK`, e a chave
    `circuit_breaker:comunica` aparece no Redis como `closed` logo após
    (prova direta de que o achado foi corrigido, não só leitura de
    código); cenário de falha — 3 chamadas simuladas com HTTP 403
    seguidas abrem o disjuntor exatamente na 3ª (`circuit_open` logado),
    a 4ª tentativa é bloqueada SEM sequer tentar a rede de novo
    (`fonte_detalhe=None`, 0 chamadas reais a mais), e o Redis reflete
    `open` com contagem/timestamp corretos. Confirmado como ruído
    esperado de sandbox (não achado novo): a tentativa real de
    enriquecimento via DataJud dentro do próprio teste também bateu 403
    — mesma classe de bloqueio de proxy já documentada, não evidência de
    problema em produção (Railway tem egress irrestrito).
  - Suíte relacionada rodada (`test_oab_capture_syncrun_erro.py`,
    `test_oab_discovery.py`, `test_process_fonte.py`,
    `test_dje_monitor_circuit_breaker.py`,
    `test_dje_monitor_syncrun_erro.py`, `test_comunica_diagnostico.py`,
    `test_publication_monitor_real_scan.py`): 1 falha pré-existente e
    **confirmada não relacionada** (`test_process_fonte.py::
    test_process_response_expoe_fonte`, reproduz idêntica isolando
    `git stash` das mudanças desta fase — mesma classe de bug já
    documentada váras vezes nesta sessão, `_FakeDB`/objeto ORM construído
    em memória sem passar por um flush real, então `created_at` nunca é
    populado pelo `default` do SQLAlchemy; não é usado no cenário desta
    fase, fora de escopo, não corrigido). Os demais 22 testes passam
    limpos. `ruff check`/`py_compile` limpos nos 2 arquivos tocados.
  - **O que fica pra decisão do usuário, não verificável desta sessão**:
    se o tenant real não tiver NENHUMA OAB cadastrada (nem em usuário com
    login, nem em "OABs monitoradas" do escritório em `Configurações →
    Jurídico`), as duas capturas respondem corretamente "0 encontrado(s)"
    — não é bug, mas pode "parecer" quebrado; vale conferir essa tela
    antes de qualquer outra investigação. Nenhum mecanismo de reset
    manual do circuit breaker foi adicionado — o estado em memória já
    reseta em qualquer redeploy (novo processo), e mesmo sem redeploy o
    `reset_timeout` de 30min já limita o tempo de um breaker aberto por
    engano.
- **Fase 252** — usuário confirmou, depois do deploy das Fases 250
  (headers de navegador) e 251 (breaker sincronizando com Redis), que o
  403 do Comunica/DJEN **continua** aparecendo nas duas capturas — a
  hipótese "só faltava parecer um navegador nos headers" não se sustenta
  mais sozinha. Recontado o hipotético com o dado novo (documentado no
  código): pode ser fingerprint TLS/JA3 (WAFs modernos identificam o
  cliente pelo aperto de mão TLS antes de olhar qualquer header HTTP —
  nenhum header sozinho resolveria isso), bloqueio por IP do range de
  saída do Railway, ou o deploy anterior ainda não ter propagado —
  nenhuma das três é verificável desta sessão (sandbox sem egress real
  pro Comunica, sem acesso ao dashboard do Railway). Usuário escolheu
  (via pergunta) resolver o diagnóstico primeiro, sem apostar de novo
  numa correção mais pesada e especulativa sem dado real.
  - **`backend/app/integrations/dje/comunica.py`**: até aqui só o
    **status code** de uma falha era capturado — nunca o CORPO da
    resposta. Se o WAF devolve uma página de desafio (Cloudflare/Akamai,
    HTML) em vez de um 403 seco, estávamos cegos pra essa diferença.
    `buscar_comunicacoes()` agora captura `resp.text[:500]` (truncado,
    não é PII — é a resposta pública de um WAF) em `stats["body_snippet"]`
    e no log, pra qualquer 403 futuro já vir com o corpo real anexado.
  - **Achado colateral, corrigido junto**: ao contrário de
    `capturar_por_oab()` (`oab_capture.py`, expõe `fonte_respondeu`/
    `fonte_detalhe` desde a Fase 114), `scan_publicacoes()`
    (`dje_monitor.py`) descartava o `stats` de cada OAB a cada iteração
    do loop — "0 intimações" por não ter novidade no dia e "0 intimações"
    por 403 da Comunica pareciam **idênticos** pro chamador. Isso também
    explica por que o 403 relatado pelo usuário só aparecia como toast
    visível na captura de PROCESSOS (`/tenant/oabs/capturar`, que já
    tinha essa distinção) — a captura de PUBLICAÇÕES (`/publicacoes/
    varrer`) sempre respondia `"Varredura concluída."` mesmo numa falha
    total, escondendo o problema em vez de mostrar. `scan_publicacoes()`
    agora rastreia e expõe `fonte_respondeu`/`fonte_detalhe` também;
    `POST /publicacoes/varrer` (`publications.py`) ganha a mesma
    mensagem dinâmica de 3 vias que `/tenant/oabs/capturar` já tinha
    (novas>0 / fonte não respondeu com detalhe / fonte respondeu mas
    vazio) + um 4º caso (zero OAB monitorada); o frontend
    (`publicacoes/page.tsx`) troca o toast de sucesso sempre-verde por
    um aviso (`toast.warning`) quando `fonte_respondeu === false`.
  - Testes novos: `test_falha_captura_corpo_bruto_da_resposta`
    (`test_comunica_diagnostico.py`, corpo simulando uma página de
    desafio Cloudflare) e `test_falha_expoe_fonte_respondeu_e_detalhe`/
    `test_sucesso_expoe_fonte_respondeu_true`
    (`test_dje_monitor_circuit_breaker.py`) — 24 testes relacionados
    passam limpos (`test_dje_monitor_circuit_breaker.py`,
    `test_dje_monitor_syncrun_erro.py`, `test_comunica_diagnostico.py`,
    `test_publication_monitor_real_scan.py`,
    `test_oab_capture_syncrun_erro.py`, `test_oab_discovery.py`,
    `test_tribunais_base_http_client.py`). `ruff check`/`py_compile`
    limpos no backend; `tsc --noEmit` limpo; `eslint` no arquivo
    frontend tocado — 1 warning pré-existente de `exhaustive-deps`,
    confirmado via `git stash` como não-novo desta fase.
  - **Limitação de verificação, a mesma de toda fase anterior que mexeu
    nesta fonte**: este sandbox continua sem egress real pra
    `comunicaapi.pje.jus.br` (reconfirmado — `curl` → `CONNECT tunnel
    failed, response 403`, bloqueio do proxy da sessão, não do servidor
    real) — não foi possível reproduzir o 403 de produção nem confirmar
    ao vivo qual das 3 hipóteses é a real. **Nenhuma correção de causa
    raiz foi tentada nesta fase** (decisão deliberada do usuário) — só a
    melhoria de diagnóstico. **Próximo passo real**: usuário testar de
    novo em produção depois do deploy e colar o erro detalhado novo
    (agora com o corpo da resposta) + confirmar no dashboard do Railway
    qual commit está de fato rodando — com esse dado real, decide-se
    entre as 3 hipóteses (fingerprint TLS → trocar o cliente HTTP por um
    que imite um navegador de verdade, ex. `curl_cffi`; bloqueio por IP →
    não resolvível só com código, precisa de contato com o suporte do
    PJe/CNJ; deploy não propagado → nada a fazer, só esperar) antes de
    tentar mais uma correção às cegas.
- **Fase 253** — usuário pediu auditoria completa do módulo Mapa/
  geolocalização: pelo menos um cliente aparecia com marcador em local
  geograficamente incompatível com o endereço cadastrado (imagem de
  referência: escritório em Rio Branco/AC). Investigação (3 Explore
  agents em paralelo — backend de geocodificação/clientes, frontend do
  mapa/Leaflet, dados reais no Postgres local + histórico do CLAUDE.md —
  mais releitura direta de cada trecho citado antes de planejar)
  confirmou uma causa-raiz única, batida de forma independente pelos 2
  agentes de código sem eu ter direcionado nenhum dos dois pra lá:
  **`_geocodificar_endereco()` (`backend/app/api/v1/clients.py`) decidia
  se re-geocodificava só olhando se o payload JÁ tinha `latitude`/
  `longitude` — nunca comparava com o CEP anterior.** O formulário de
  edição de cliente (`frontend/.../clientes/page.tsx::abrirEdicao`)
  reidrata o `endereco_json` inteiro no estado de edição (inclusive
  coordenadas antigas); nenhum `onChange`/`autofillCep` as limpava ao
  trocar o CEP. No submit, o payload ia com `{cep: novo, ..., latitude:
  antiga, longitude: antiga}`, e `_geocodificar_endereco` via que já
  tinha coordenada e devolvia sem consultar a BrasilAPI de novo — texto
  do endereço novo, coordenada presa ao CEP antigo. Hipótese **E** da
  lista do usuário ("endereço alterado sem nova geocodificação"),
  confirmada por trace de código ponta a ponta.
  - **Descartado por evidência direta** (não suposição): Leaflet/
    react-leaflet sem troca de eixo lat/lng nem colisão de `key`; sem
    cache de coordenada em lugar nenhum (Redis só guarda estado do
    `CircuitBreaker`, nunca uma coordenada); mapa nunca usa a coordenada
    do escritório como fallback de cliente; `_extrair_coordenadas`
    (`cep_lookup.py`) lê `latitude`/`longitude` por nome, sem inversão;
    endereço do Tenant (escritório) não tinha esse bug (`EnderecoUpdate`
    não aceita lat/lng no body, sempre re-geocodificava). Dados locais
    deste sandbox não reproduzem o cenário exato do usuário (nenhum
    cliente com Rio Branco/AC aqui — os 4 clientes com coordenada no
    Postgres local são todos de São Paulo, semeados manualmente nas
    Fases 230/231/233, já que a geocodificação real nunca rodou neste
    sandbox por bloqueio de egress à BrasilAPI). **Não foi possível
    identificar o cliente exato do screenshot nem confirmar sua
    coordenada antes/depois** — sem acesso ao banco de produção desta
    sessão.
  - **Correção da causa-raiz**: `_geocodificar_endereco()` ganha
    `endereco_anterior` (o valor ainda não sobrescrito no banco, passado
    pelo chamador antes do `setattr`) — só pula a geocodificação se já
    tem coordenada **e** o CEP não mudou. Se o CEP mudou e a nova
    consulta falhar, a coordenada antiga é explicitamente zerada (nunca
    fica presa ao endereço novo). `update_client` passa `endereco_
    anterior=client.endereco_json`; `tenant.py::update_endereco` passa
    por simetria (não tinha o bug, mas ganha a mesma validação nova).
  - **Validação de sanidade, nunca existia**: `_extrair_coordenadas`
    (`cep_lookup.py`) ganha rejeição de faixa inválida (`-90..90`/
    `-180..180`) e de `(0,0)` (sentinela comum de "não encontrado" em
    geocodificadores) — ponto único, todo consumidor de `consultar_cep()`
    (Cliente/Tenant/preview do form) protegido de graça.
  - **Rastreabilidade, reaproveitando `endereco_json`** (sem tabela/
    coluna nova): `geocoded_at` (ISO 8601 UTC) e `geocode_source`
    (`"brasilapi"`) gravados junto com toda coordenada nova. Sem
    migração (JSONB schemaless) e sem backfill de dado legado (mesma
    decisão das Fases 233/245) — registros antigos simplesmente não têm
    essas chaves, o que vira o critério do badge de status abaixo.
  - **Botão "Recalcular localização"** — novo `POST /clients/{id}/
    recalcular-localizacao`: zera a coordenada atual e força nova
    consulta mesmo sem o CEP ter mudado (útil de forma geral, não só
    pro cliente do screenshot — o usuário decidiu resolver o registro
    já afetado reeditando manualmente, sem mecanismo dedicado pra isso
    especificamente).
  - **Badge de status ✓/⚠/○** — computado no frontend a partir do que a
    API já devolve, sem endpoint dedicado: `NAO_GEOCODIFICADO` (sem
    coordenada), `REQUER_REVISAO` (tem coordenada mas sem `geocode_
    source` — herdada de antes do fix, mesma classe de registro que
    pode ter sido afetada), `VALIDADA` (passou pelo caminho corrigido).
    Mostrado no cadastro de cliente (`ClienteFormFields.tsx`) e no
    popup do mapa (`EscritorioClientesMap.tsx`).
  - **Auditoria de geolocalização — só relatório**: novo `GET /clients/
    geolocalizacao/auditoria` (declarado antes de `GET /{client_id}`,
    mesmo cuidado de ordenação já usado em `/portal-access`), gate
    ADMIN/SOCIO/GESTOR, lista todo cliente com CEP + status computado.
    Nenhuma correção em massa automática — usuário decidiu não precisar
    disso nesta fase.
  - **Verificado ao vivo (Postgres real, `_consultar_cep_externa`
    monkeypatchada — mesma limitação de egress bloqueado à BrasilAPI já
    documentada desde a Fase 217/230)**: script direto reproduzindo o
    cenário exato do achado — cliente criado com CEP de São Paulo
    (geocodificado), editado pro CEP de Rio Branco/AC com o payload
    trazendo lat/lng antigas de SP (mesmo formato que o frontend real
    envia) — confirma que a coordenada persistida passa a ser a de Rio
    Branco, não fica presa a São Paulo; CEP inalterado não rebate a API
    (comportamento preservado); CEP mudado com geocodificação falha zera
    a coordenada em vez de deixar presa; botão Recalcular força nova
    consulta; validação de faixa/`(0,0)` rejeitada; auditoria classifica
    `REQUER_REVISAO` (registro legado sem `geocode_source`, inserido
    direto no banco simulando dado pré-fix) vs. `VALIDADA` corretamente.
    A suíte pytest (`test_client_geocoding_fase233.py` estendido) bateu
    na mesma flakiness de pool asyncpg/pytest-asyncio documentada desde
    a Fase 199 — reproduzida de novo mesmo isolando teste a teste, cross-
    checada contra um arquivo de controle não tocado
    (`test_crm_metas_fase213.py`, falha de forma idêntica) — não é
    regressão desta fase; a prova real veio do script standalone. Novo
    `test_cep_lookup_coordenadas_fase253.py` (puramente unitário, sem
    banco) passa limpo. Playwright real (Chromium do sandbox, `npm run
    dev` com `API_URL` local, backend local real): criou cliente com CEP
    via UI, confirmou que o botão "Recalcular localização" aparece no
    modal de edição e que trocar o CEP no formulário mostra ao vivo o
    aviso "CEP alterado — a localização será recalculada ao salvar" —
    zero erro de console atribuível a esta fase (só WebSocket do dev
    server, já documentado, e o warning de key duplicada pré-existente
    desde a Fase 219). `ruff check`/`py_compile` limpos no backend;
    `tsc --noEmit`/`eslint` limpos no frontend (2 warnings pré-
    existentes de `exhaustive-deps`, confirmados via `git stash` como
    não-novos desta fase).
  - **Fora de escopo desta fase** (decisão do usuário): busca por
    cliente, filtro por cidade/UF, clustering, legenda dedicada, ajuste
    manual arrastando o marcador no Leaflet, correção em massa com
    confirmação explícita — ficam pra uma fase futura se pedido.


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
- **Termo de Uso da API Pública do CNJ DataJud vs. uso comercial** (achado
  da Fase 217, pesquisa de APIs governamentais) — o sistema já integra o
  DataJud (`integrations/tribunais/cnj.py`) desde antes desta sessão pra
  enriquecer processos com movimentações. Segundo trechos localizados do
  Termo de Uso oficial (não lido por completo — `WebFetch` bloqueado neste
  sandbox pra qualquer domínio externo), o texto veda "modificar,
  distribuir, vender, ou explorar comercialmente a API ou qualquer
  informação derivada dela". O AFJ é um produto comercial. Precisa de
  leitura jurídica do PDF completo do termo pra decidir se o uso atual
  está em conformidade — não decidir unilateralmente sem esse parecer.
  Mesma classe de pendência que a retenção de auditoria acima: registrada,
  não resolvida arbitrariamente.
