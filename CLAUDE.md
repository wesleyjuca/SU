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
  api/v1/          — 298 rotas REST em 32 routers (contagem medida por
                     introspecção do app na rodada pós-260.5; o número
                     antigo, "82 endpoints / 15 routers", estava
                     desatualizado por 3,6× e subdimensionava auditorias)
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
- **Backend (Railway)** — integração nativa Railway↔GitHub (git-integration), auto-deploy no push para `main`. Configuração em `railway.toml` (raiz) + `Dockerfile` (raiz) + `start.sh`. O Root Directory do serviço é a **raiz do repositório** (confirmado pelo dono) — por isso é o `railway.toml` da raiz que governa.
- **Dois `Dockerfile` e dois `railway.toml`, de propósito** — não são duplicatas a limpar. `Dockerfile` (raiz) + `railway.toml` (raiz) servem ao Railway e rodam `start.sh` (Celery worker+beat embutidos, mais `postgresql-client` para o `pg_dump` do bloco `MIGRATE_FROM_URL`). `backend/Dockerfile` serve ao **Docker Compose** (`docker-compose.yml`, `docker-compose.prod.yml` e `make build-prod`), onde Celery são serviços separados e um watchdog embutido seria duplicação — **apagá-lo quebra os dois compose e o Makefile**. `backend/railway.toml` não é a config ativa; foi alinhado ao da raiz (fase pós-260.8) para que uma mudança de Root Directory no painel não troque silenciosamente o boot por um sem Celery.
- **Frontend (Vercel)** — workflow separado `deploy-frontend-auto.yml`, dispara no push para `main` que toque `frontend/**`, roda `vercel --prod`.

Secrets do **GitHub Actions** (usados pelos workflows acima): `VERCEL_TOKEN`, `RAILWAY_URL` (não-secreta, só a URL do backend pra build do frontend).

Secrets de **runtime da aplicação** (configurados direto na plataforma — Railway dashboard ou `.env.prod` no self-host, NÃO no GitHub Actions): `SECRET_KEY`, `ENCRYPTION_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DATABASE_URL`, `REDIS_URL`, `QDRANT_URL`/`QDRANT_API_KEY`.

## Testing

```bash
# Backend (venv direto — modo mais usado quando Docker não está disponível)
cd backend && source venv/bin/activate
pytest tests/                       # suíte completa
ruff check app/                     # lint
python -m py_compile <arquivo>.py   # sanity check rápido de sintaxe

# Frontend
cd frontend
npx tsc --noEmit        # type check
npx eslint <arquivo>    # lint

# Via Docker (padrão do Makefile — requer Docker disponível)
make test / make lint / make format
```

Verificação de mudança em endpoint/fluxo real: preferir subir a stack de
verdade (`backend/start.sh` + `npm run dev` no frontend, `API_URL` local)
e testar via HTTP/Playwright real, não só o resultado do `pytest` — ver
armadilhas abaixo sobre por que a suíte sozinha não é sempre confiável.

**Armadilhas conhecidas** (não óbvias, custam tempo real se
rediscobertas do zero a cada sessão — contexto completo de cada uma em
`HISTORICO_FASES.md`, se precisar):

- **Flakiness de pool asyncpg/pytest-asyncio** — **CORRIGIDA** (fase de
  correção pós-260.5). Ficam aqui a causa e o que fazer se voltar. Eram
  **duas** causas somadas: (a) **dois plugins async disputando o mesmo
  teste** e (b) o engine singleton reusado entre event loops. (a) foi
  resolvida com `addopts = -p no:anyio` no `pytest.ini`; (b), nos testes
  que falam com Postgres de verdade, com o helper
  `tests/db_isolada.py::sessao_isolada()` (engine próprio + `NullPool`,
  nascendo e morrendo dentro do loop do teste). Resultado: `tests/test_unit/`
  saiu de 12 falhas + 2 erros para **882 passes, zero falhas**, e é hoje
  gate real do CI. Detalhes históricos:
  `pytest.ini` tem `asyncio_mode = auto` (pytest-asyncio) *e* 38 arquivos
  usam `pytest.mark.anyio`, sem nenhuma fixture `anyio_backend` — o sufixo
  `[asyncio]` nos IDs de teste é a parametrização de backend do anyio,
  não do pytest-asyncio. O engine singleton do SQLAlchemy (a explicação
  anterior, das Fases 199/212) é o que transforma o conflito em erro
  visível, mas não é o gatilho. Experimento decisivo, sem editar nada:
  o mesmo arquivo falha como está e **passa com qualquer um dos dois
  plugins desligado** (`-p no:anyio` ou `-p no:asyncio`). Medido na
  `test_api/` inteira: 102 falhas/34 passes/142 erros → **20 falhas/90
  passes/78 erros** com plugin único. **Duas alternativas foram medidas e
  descartadas** (não retentar às cegas): loop de escopo de sessão
  (`asyncio_default_*_loop_scope=session`) zera os erros mas faz uma falha
  de fixture cascatear em ~38 pulos silenciosos; e `engine.dispose()`
  autouse por teste subiu os pulos de 42 para 78.

  **`tests/test_api/` também está verde** (fase seguinte): saiu de 27 falhas +
  75 ERROS para **zero**, em duas execuções seguidas contra o mesmo banco, e
  virou gate do CI. Nenhuma das causas estava em código de produto:
  (a) o engine da app tinha QueuePool e reusava conexão entre event loops —
  resolvido com `AFJ_DB_NULLPOOL=1` (ver `app/db/base.py`, ligado só pelo
  conftest); (b) a suíte estourava o próprio rate limit de login (~180 logins
  contra teto de 10/min no mesmo IP) — token agora é cacheado por processo e
  as chaves são limpas entre testes; (c) um teste colocava o token
  COMPARTILHADO na blacklist e derrubava todos os seguintes com 401;
  (d) FK fabricada e identificadores fixos (ver `tests/dados.py`);
  (e) asserções defasadas em relação ao código atual.
- **O CI hoje tem 4 gates reais de backend** (antes tinha zero: o passo de
  testes não instalava `requirements.txt`, a suíte morria na coleção e o
  `| head -80 || true` devolvia exit 0). Agora: `ruff check app/`,
  `pytest tests/test_unit/` (~889 testes), `pytest tests/test_api/
  test_lgpd_sentinela.py` (guarda de esquecimento) e **`pytest
  tests/test_api/` inteiro** (~185 testes). O job
  sobe um Postgres de serviço e roda schema + seed pelo mesmo caminho do
  boot da app — **o seed não é opcional**: sem o ADMIN semeado a fixture
  `auth_headers` chama `pytest.skip` e o gate viraria decorativo. As libs de
  teste moram em `backend/requirements-dev.txt` (`pytest`/`pytest-asyncio`),
  não em `requirements.txt` — o primeiro run do CI novo quebrou com "No
  module named pytest" justamente porque a simulação local rodou dentro de
  um venv que já os tinha. **Simular o CI num ambiente que já está montado
  não prova a instalação**; a prova de um passo de install é o run real. O
  2º run achou outro defeito latente que só um ambiente diferente expõe:
  `test_worker_reliability.py` comparava event loops por `id()` (endereço de
  memória em CPython) — com o 1º loop já coletado, o alocador devolveu o
  mesmo endereço pro 2º e o teste acusou "mesmo loop" com dois loops
  distintos. **Nunca use `id()` para provar que dois objetos de vida curta
  são distintos**; guarde as referências.
- **Teste de API pode quebrar o seed do seu banco local.** Enquanto a suíte
  não rodava, isso passava despercebido; assim que voltou a rodar,
  `test_password_change_success` trocou a senha do ADMIN semeado e derrubou
  o login de toda a sessão. Foi corrigido (o teste restaura o que muda),
  mas a lição vale para qualquer teste novo: **desfaça o que você fez**,
  especialmente em dado semeado.
- **O CI não tem Redis — só Postgres.** `/health` responde `degraded` lá (a
  resposta CERTA), e qualquer teste que exija `operational` reprova por
  ambiente, não por código. Aconteceu no 1º run com a suíte de API como gate.
  Ao verificar localmente, rode também **sem Redis e com banco novo**
  (`REDIS_URL= DATABASE_URL=<banco limpo> pytest ...`) — é a 3ª vez nesta
  série que a divergência entre o ambiente local e o do runner produz um
  vermelho que a verificação local não podia prever. E prefira asserção de
  **coerência** (status × componentes reportados) a asserção de literal: vale
  em qualquer ambiente e ainda pega "operational" mentiroso.
- **Teste que chama a função do endpoint DIRETO não resolve os defaults do
  FastAPI.** Um `limit: int = Query(default=50, le=200)` chega como o objeto
  `Query`, não como `50`, e estoura lá dentro (`.limit(Query(...))` →
  `TypeError`). Vários testes foram escritos quando a assinatura era
  `limit: int = 50` e quebraram silenciosamente quando ela virou `Query(...)`.
  Ao chamar um endpoint direto, passe TODOS os parâmetros explicitamente.
- **Fake de teste com assinatura desatualizada vira "erro do serviço
  externo".** Um mock de `drive_upload_doc` ficou com 3 parâmetros depois que
  o endpoint passou a mandar `parent_folder_id=`; o `TypeError` caiu no
  `except Exception` genérico do endpoint e virou **502**, como se o Google
  tivesse falhado. Prefira `**_kwargs` nos fakes e desconfie de 5xx em teste
  com mock.
- **`BaseAgent.run()` NUNCA propaga exceção** — converte em
  `AgentResult(status=FAILED)`. Quem chama um agente e só lê `result.output`
  trata falha total como sucesso: foi assim que `poll_all_processes` rodava a
  cada 30 min, podia falhar inteiro e retornava `None` sem acionar retry nem
  registrar `SyncRun`. **Sempre cheque `result.status`.** Cuidado extra em
  lote: `max_retries = 2` re-executa a chamada inteira até 3× — no polling só
  é tolerável porque a dedup por hash impede duplicata.
- **Fail-soft pode engolir o sinal**: `CircuitBreaker.run(..., default=[])`
  nunca levanta, então "a fonte está fora" e "não há novidade" viravam o mesmo
  `[]` — um ciclo sem nenhuma consulta bem-sucedida saía `status="OK",
  errors=0`. Ao usar um default fail-soft, garanta que o chamador consiga
  distinguir os dois casos (em `datajud_fonte.py` isso virou o parâmetro
  `sinalizar_falha`).
- **Teste que substitui a função inteira não prova a correção dela.** O 1º
  desenho do teste de "falha ao persistir deixa de contar como sucesso"
  trocava `_save_movements` por um fake que levantava — e passava mesmo com a
  correção revertida, porque o código corrigido nunca rodava. Injete a falha
  numa dependência de DENTRO da função. Só se descobre isso rodando o teste
  com o fix revertido, que por isso é obrigatório aqui.
- **Três mecanismos de gate de papel coexistem** — auditar só um produz
  falso positivo em escala (aconteceu 4× numa única rodada):
  `Depends(require_role(...))`, checagem inline no corpo
  (`if current_user.role not in (...)`) e helper (`_require_admin` em
  `users.py`). Ao avaliar se uma rota está protegida, cheque os três.
- **Alembic: consertado na fase pós-260.7 depois de nunca ter rodado.** Ficam
  aqui a causa e as 3 armadilhas que ele deixou. Eram **3 bugs empilhados**:
  (a) `alembic.ini` declarava `sqlalchemy.url = %(DATABASE_URL)s`, interpolação
  que o configparser resolve contra a própria seção e nunca contra o ambiente;
  (b) `env.py` a lia como 2º argumento de `os.getenv`, que o Python avalia
  SEMPRE — então falhava mesmo com a env var setada; (c) a cadeia de revisões
  tinha **2 elos errados** (`002.down_revision="001_initial_schema"` vs.
  `001.revision="001"`; `003.down_revision="002"` vs.
  `002.revision="002_add_tenant"`), mascarados por (a)+(b). Aparato inteiro
  nasceu assim no commit `057893b` (Fase 136) e nunca rodou em 182 commits.
  **Três coisas a não reaprender do zero**:
  - **Nunca rodar `upgrade head` num banco deste projeto.** As 4 migrações
    conhecem 26 tabelas; o app tem 58. Medido: `upgrade head` num banco VAZIO
    produz 27 tabelas + as extensões + o trigger de `audit_logs` — schema
    diferente de todo ambiente existente. Quem monta schema aqui é `create_all`
    + `DDL_IDEMPOTENTE`. A regra "carimbar, nunca migrar" vive em **um lugar
    só**, `backend/alembic_boot.sh`: carimba (`stamp head`) qualquer banco sem
    carimbo, vazio ou não, e só faz `upgrade` no que já tem carimbo — aí sim
    para migrações futuras, que funcionam (provado com uma migração de teste:
    `004 → 999_probe`, upgrade e downgrade). **Todos os 4 chamadores passam
    por ele**: `start.sh`, `docker-compose.prod.yml`, `scripts/migrate.sh` e
    `make migrate`. Se você escrever um 5º, use o script — não chame
    `alembic upgrade head` cru.
  - **Corolário que só apareceu na fase seguinte**: consertar o alembic
    transformou linhas antes inofensivas em armadilhas. O
    `docker-compose.prod.yml` fazia `alembic upgrade head || echo …`, que
    falhava sempre e por isso não fazia mal; com o alembic funcionando, uma
    instalação NOVA de VPS passaria a ganhar o schema híbrido + o trigger.
    Ao consertar algo que estava morto, procure quem dependia de ele estar
    morto.
  - **Model fora do `app/models/__init__.py` é armadilha de DROP TABLE.**
    `push_subscription` e `ai_call_log` só entravam no metadata porque routers
    os importam em runtime; o `env.py` faz só `import app.models`, então o
    autogenerate propunha apagar as 2 tabelas. Fechado com registro explícito
    + guarda em `tests/test_unit/test_schema_metadata_guard.py`, que mede num
    **interpretador separado** — medir no processo do pytest dá sempre
    "presente" (o conftest importa `app.main`) e o teste passa com o fix
    revertido. Foi o 1º desenho, e falhou nessa exata armadilha.
  - **O passo de schema do CI não era "o mesmo caminho do boot"**, apesar do
    nome: rodava `create_all` + seed e pulava o DDL idempotente. O banco do CI
    ficava sem 9 índices que produção tem, 3 deles constraints de integridade —
    e `test_tenant_user_unique_constraints` **pulava** por ausência do índice
    em vez de proteger (medido: 2 skipped → 2 passed depois do fix). O bloco
    virou `events.py::DDL_IDEMPOTENTE` + `aplicar_ddl_idempotente(engine)`,
    chamado pela `lifespan` E pelo CI.
- **Egress de rede bloqueado no sandbox de desenvolvimento** (não em
  produção — Railway tem egress irrestrito): domínios externos como
  `brasilapi.com.br`, `googleapis.com`, `graph.facebook.com`,
  `comunicaapi.pje.jus.br`, `api.stripe.com`, `tile.openstreetmap.org`
  são bloqueados pelo proxy da sessão. Pra verificar uma integração
  externa aqui, faça monkeypatch da chamada HTTP de saída — nunca
  conclua "não funciona" sem antes descartar esse bloqueio; a
  confirmação final fica pro usuário testar pós-deploy.
- **Docker não disponível neste sandbox** (`service docker start` falha
  com "Operation not permitted"). Pra testar contra um Qdrant SERVIDOR
  de verdade (não `:memory:`, que não aplica enforcement de índice de
  payload — só reproduzível assim), baixe o binário standalone do
  Qdrant do GitHub Releases.
- **LGPD erasure — checklist obrigatório pra tabela nova com vínculo a
  `clients.id`** (direto ou via FK transitivo, ex.
  `processo_id → LegalProcess.client_id`): toda tabela nova com PII de
  um titular precisa ser adicionada em `erase_client_data`/
  `export_client_data` (`backend/app/api/v1/lgpd.py`) — essa classe de
  bug já se repetiu 8+ vezes neste projeto (tabela nova esquecida pelo
  esquecimento LGPD). Ao adicionar uma tabela com vínculo (direto ou
  indireto) a `clients.id`, checar se ela precisa entrar nesses 2
  endpoints antes de considerar a feature pronta.
- **Fase pós-260.2** — usuário pediu pra transformar `/mapa` (visualização
  de pins) num "painel geográfico da carteira jurídica": indicadores,
  ações contextuais ao clicar num cliente, correção de geolocalização
  deslocada pra dentro da Auditoria (não mais um botão global de "Ajustar
  manualmente", removido por ser considerado edição manual de coordenada
  desnecessária). Investigação (3 Explore + 1 Plan agent) revelou que boa
  parte do pedido já existia — clusterização (`react-leaflet-cluster`),
  painel de Auditoria com as 3 contagens (VALIDADA/REQUER_REVISAO/
  NAO_GEOCODIFICADO), filtros de cidade/UF — mudando o escopo real pra
  remoção + acréscimos pequenos, não reforma do zero.
  - **Removido**: botão global "Ajustar manualmente" (draggable +
    popup de confirmar/cancelar coordenada crua) do header e do
    `EscritorioClientesMap.tsx` — junto com a prop `ajusteAtivo`/
    `onAjustarLocalizacao`. `PUT /clients/{id}/localizacao-manual`
    (backend) fica sem chamador no frontend web — mantido de propósito
    (decisão explícita: não deletar API sem necessidade comprovada),
    documentado com uma nota no próprio docstring do endpoint.
  - **Indicadores de topo** (geocodificados/sem localização/cidades/UFs)
    — fonte única: `GET /clients/geolocalizacao/auditoria` (cobre a
    carteira inteira, não só quem tem pino no mapa, sem o cap de 200 do
    `GET /clients`), buscada num efeito separado reagindo a
    `podeAjustar` — **achado real durante a verificação**: buscar no
    mesmo efeito de mount (`deps: []`) junto com a lista de clientes
    quebrava, porque `useUserStore` começa com `user: null` e hidrata
    de forma assíncrona — `podeAjustar` calculado no mount quase sempre
    vinha `false`, e a busca nunca rodava de novo (deps vazias).
    Corrigido com um 2º `useEffect([podeAjustar])` dedicado.
  - **Filtros de carteira** (tipo/status/segmento) — 100% frontend,
    `tipo`/`status`/`segmento` já vinham em `GET /clients` mas eram
    descartados no mapeamento da página antes de virar estado.
  - **Popup do marcador** ganhou `maxWidth` explícito + botão "Ver
    cliente completo" (link pra `/clientes/{id}`) — decisão confirmada
    com o usuário: estender o popup existente em vez de construir um
    painel lateral novo (sem nenhum precedente desse padrão no projeto).
  - **Auditoria** ganhou, por linha pendente: "Recalcular" (reaproveita
    `POST /clients/{id}/recalcular-localizacao`, já existia) e "Corrigir
    endereço" (`/clientes?editar={id}` em nova aba — decisão confirmada
    com o usuário, depois de um agente de plano achar que a proposta
    original, linkar pra `/clientes/{id}`, não funcionaria: essa página
    não tem NENHUMA UI de endereço, que só existe no modal da LISTA de
    clientes). Novo efeito em `clientes/page.tsx` lê `?editar=`, busca
    `GET /clients/{id}` direto e abre o modal já existente — salvar lá
    já re-geocodifica sozinho (`_geocodificar_endereco`, comportamento
    pré-existente). Também ganhou um rótulo agregado "Precisão
    aproximada" (clientes VALIDADA com `geocode_source="brasilapi"`,
    CEP/quadra, vs. `"nominatim"`, endereço+número) — sem nenhum campo
    novo de precisão no backend, só reinterpretação do campo existente.
  - **Fora de escopo, registrado**: heatmap (exigiria dependência nova,
    `leaflet.heat` ausente), filtro por raio (haversine já existe no
    frontend, mas não implementado nesta fase), camadas de mapa
    (provavelmente frontend puro via `LayersControl` do `react-leaflet`,
    não confirmado), histórico de mudança de coordenada (exigiria
    backend novo — `AuditLog` nunca popula `old_value`/`new_value`
    nessas rotas hoje). Cap de 200 clientes em `GET /clients` (limitação
    pré-existente) também registrado, não corrigido.
  - **Verificado**: `tsc --noEmit`/`eslint` limpos; `ruff`/`py_compile`
    limpos no backend; suíte pytest relacionada apresentou a mesma
    flakiness de pool asyncpg/pytest-asyncio já documentada (confirmada
    contra um arquivo de controle não tocado, que falha do mesmo jeito
    — não é regressão). Prova real: stack completa (Postgres+Redis+
    uvicorn+`npm run dev`) com dados semeados cobrindo os 4 status de
    auditoria + tipo/status/segmento variados — Playwright real
    confirmando "Ajustar manualmente" ausente em toda a tela,
    indicadores corretos, os 3 filtros novos funcionando (reduz
    contagem exibida), popup com o link navegando pro cliente certo,
    as 4 contagens + "Precisão aproximada" na Auditoria, "Recalcular"
    disparando requisição real com feedback, e "Corrigir endereço"
    abrindo nova aba com o modal de edição pré-carregado no cliente
    CERTO (nome conferido) — 27/27 checks PASS, zero diálogo nativo,
    console limpo.
- **Fase pós-260.3** — usuário reclamou (2ª vez, mesma frase): "a busca
  semântica deve usar a IA escolhida nas minhas IAs, não deve ter uma
  IA única". Investigação (1 Explore agent, leitura completa de
  `rag/embeddings.py`, `models/ai_config.py`, `integrations/byok.py`,
  `services/brain_assistant.py`, grep total por `OPENAI_API_KEY`,
  frontend "Minha IA") confirmou uma limitação técnica real e uma
  lacuna real e corrigível, distintas:
  - **Limitação técnica, não corrigível**: a etapa de embedding (o
    único ponto onde uma "IA" de fato participa da busca semântica —
    `POST /rag/search` não sintetiza resposta com LLM, só devolve
    trechos rankeados) está presa à OpenAI porque as 7 collections
    reais do Qdrant foram criadas com a dimensão do
    `text-embedding-3-large` (3072). A Anthropic não tem API pública de
    embeddings — não existe como "usar Claude" nesse passo, mesmo que
    seja a IA padrão do usuário em "Minha IA". Já mitigado desde a Fase
    pós-259: `_resolve_byok_openai_key()` já varre toda a cadeia BYOK
    do usuário (padrão + até 2 fallbacks), não só a padrão — se
    QUALQUER credencial OpenAI estiver cadastrada em qualquer posição,
    ela já é usada. O frontend ("Minha IA") já tem um aviso condicional
    explicando isso e orientando a cadastrar uma chave OpenAI mesmo sem
    torná-la padrão.
  - **Lacuna real corrigida**: `backend/app/services/brain_assistant.py`
    (RAG do assistente "Cérebro", separado da Pesquisa Jurídica) nunca
    tinha recebido o mesmo fix — `_rag_docs()` e `reindexar_documentacao()`
    só checavam `settings.OPENAI_API_KEY` (central), ignorando por
    completo qualquer BYOK do usuário. Além disso, mesmo se o guard
    fosse corrigido, `montar_system_prompt()` (que chama `_rag_docs()`)
    rodava ANTES do bloco `async with user_ai_creds(...)` em
    `responder_stream()` — o contextvar de credencial nunca estava
    setado quando o embedding da pergunta era tentado. Corrigido: guard
    de `_rag_docs()` removido (delega a resolução de chave pra
    `retrieve()`/`embed_text()`, que já fazem isso sozinhos e já
    degradam gracioso via o `except` existente); `montar_system_prompt()`
    movido pra dentro do `async with`; `reindexar_documentacao()` ganhou
    parâmetro `user_id` (passado pelo SUPERADMIN que chama
    `POST /system/brain/assistant/reindex`) e também passou a rodar
    dentro de `user_ai_creds()`, com uma checagem prévia (central OU
    BYOK) pra continuar devolvendo uma mensagem clara em vez de
    silenciosamente indexar 0 arquivos.
  - **Fora de escopo, decisão do usuário via pergunta**: motor de
    embedding alternativo/local (BGE-M3, já existe em modo de
    comparação/teste em `embeddings_local.py`) pra remover de vez a
    dependência de um provedor único — descartado por exigir
    reindexação completa das 7 collections (dimensão de vetor
    incompatível, 1024 vs. 3072) e ser uma mudança bem maior/mais
    arriscada que o pedido em si.
  - **Verificado**: `ruff`/`py_compile` limpos. Script standalone
    (Postgres real + Qdrant em memória + `AsyncOpenAI` mockado —
    mesmo padrão da Fase pós-259) provando ponta a ponta: usuário
    SUPERADMIN com Anthropic como IA padrão + uma credencial OpenAI
    cadastrada só como SECUNDÁRIA (não padrão), sem `OPENAI_API_KEY`
    central — `reindexar_documentacao()` indexa os 5 arquivos de
    documentação usando a chave secundária (confirmado pelo argumento
    real passado ao construtor do SDK); `responder_stream()`/
    `_rag_docs()` também alcançam a mesma chave secundária; regressão
    confirmada — sem nenhuma chave (nem central, nem BYOK), as duas
    funções degradam honesto (mensagem clara, sem crashar o chat) — 6/6
    checks PASS. 2 testes unitários novos + 1 mensagem de teste
    existente atualizada em `test_brain_assistant.py` (6/6 PASS
    isolado); demais testes relacionados (`test_rag_search_byok_
    fase255.py`) apresentaram a mesma flakiness de pool asyncpg/
    pytest-asyncio já documentada (confirmada isolada, não é regressão
    — arquivo nem foi tocado nesta fase).
- **Fase pós-260.4** — usuário pediu 5 opções novas pro `/mapa`: mapa de
  calor, satélite, terreno, tela cheia, abrir em outra janela — "priorizar
  implementação simples e reutilizar estrutura/componentes existentes".
  100% frontend, nenhum endpoint/modelo novo — todas reaproveitam dado já
  buscado (`clientesFiltrados`) ou APIs nativas do navegador/Leaflet:
  - **Satélite/Terreno** — `LayersControl`/`LayersControl.BaseLayer`,
    nativos do `react-leaflet` (nenhuma dependência nova), envolvendo os
    `TileLayer` — "Padrão" (OSM, já existia), "Satélite" (Esri World
    Imagery, `server.arcgisonline.com`, grátis/sem chave) e "Terreno"
    (OpenTopoMap, grátis/sem chave) — mesmo espírito "grátis, sem
    credencial" já usado pro tile OSM original. Zero UI customizada — o
    seletor de camadas é o controle nativo do Leaflet.
  - **Mapa de calor** — única dependência nova (`leaflet.heat` + `@types/
    leaflet.heat`, ~5KB, sem chave de API, puramente client-side).
    Alterna com o `MarkerClusterGroup` (nunca os dois juntos — ficaria
    poluído), peso uniforme por cliente (sem métrica de ponderação real
    ainda).
  - **Tela cheia** — Fullscreen API nativa do navegador
    (`element.requestFullscreen()`/`document.exitFullscreen()`), sem
    plugin. **Achado real durante a verificação**: o botão inicialmente
    ficava no cabeçalho da página — fora do elemento que entra em
    fullscreen. Como a Fullscreen API só renderiza o elemento-alvo e seus
    filhos, uma vez em tela cheia o próprio botão pra SAIR desaparecia
    (só restava `Esc`). Corrigido movendo o botão pra dentro do container
    do mapa, como overlay flutuante (mesmo padrão já usado pela
    `Legenda`) — fica acessível nos dois estados. `invalidateSize()` do
    Leaflet disparado com um pequeno atraso ao entrar/sair (o canvas não
    recalcula sozinho numa mudança de tamanho só por CSS).
  - **Abrir em outra janela** — `window.open(window.location.href,
    "_blank", "noopener,noreferrer")`, zero componente novo.
  - **Verificado**: `tsc --noEmit`/`eslint` limpos. Playwright real
    (Chromium do sandbox, dados de teste da Fase pós-260.2 reaproveitados)
    confirmando as 3 camadas listadas no controle nativo, canvas do mapa
    de calor aparecendo/sumindo ao alternar (com os marcadores voltando
    corretamente), o botão de tela cheia continuando clicável DENTRO do
    fullscreen (a prova do achado corrigido), saindo corretamente ao
    clicar de novo, e "abrir em outra janela" abrindo `/mapa` numa aba
    nova — 18/18 checks PASS, zero diálogo nativo, console limpo.
- **Fase pós-260.5** — usuário pediu (pedido formal, 9 requisitos técnicos
  + levantamento obrigatório antes de código) pra desacoplar a Pesquisa
  Jurídica (busca semântica) de um provedor único de embeddings — hoje
  presa à OpenAI mesmo quando o cliente configura Gemini como IA. Pedido
  explícito: "não assuma que a solução é trocar `OpenAIEmbeddings` por
  outra classe — mapeie o fluxo completo primeiro."
  - **Achado-chave**: já existia abstração pronta pra reaproveitar — o
    registro central `services/ai_providers.py` (`AI_PROVIDERS`) e o
    padrão já usado por `_call_openai_compatible()` em `llm_client.py`
    pra chat completions (gemini/openai/grok/deepseek/openrouter/ollama
    tratados identicamente, só muda `base_url`/chave). Pesquisa externa
    confirmou Gemini expõe endpoint OpenAI-compatible de embeddings
    (`gemini-embedding-001`, 3072 dimensões — igual ao
    `text-embedding-3-large` já usado); xAI/Grok sem API de embeddings
    (confirmado); DeepSeek/OpenRouter não confirmados com confiança
    (tratados como indisponíveis, não assumidos); Ollama/Vertex AI fora
    de escopo (self-hosted sem dimensão fixa / auth própria).
  - **Achado crítico de arquitetura**: das 8 collections Qdrant, 4 são
    PRIVADAS por tenant (`peticoes_afj`, `memorias_afj`,
    `documentos_clientes`, `doutrina_privada`) e 3+1 são
    PÚBLICAS/compartilhadas (`jurisprudencia`, `legislacao`, `doutrina`,
    `documentacao_sistema`). Um vetor Gemini e um vetor OpenAI NÃO são
    comparáveis por cosseno mesmo com dimensão idêntica — decisão
    confirmada com o usuário via pergunta: collections privadas seguem o
    BYOK de quem gerou o conteúdo; collections públicas sempre resolvem
    pro provedor PADRÃO do sistema (hoje OpenAI), pra funcionar pra
    qualquer tenant sem depender do provedor dele.
  - **Achado de compatibilidade retroativa**: nenhum ponto já indexado
    tem `embedding_provider` no payload — tratado em todo filtro de busca
    como equivalente a `"openai"` (via `IsEmptyCondition`), senão todo o
    conteúdo pré-fase desapareceria da busca no dia do deploy.
  - **`services/ai_providers.py`**: cada entrada de `AI_PROVIDERS` ganhou
    `embedding_model`/`embedding_dimensions` (`openai`:
    `text-embedding-3-large`/3072; `gemini`: `gemini-embedding-001`/3072;
    demais: `None`) + novo `embedding_capable_providers() -> set[str]`.
  - **`rag/embeddings.py` generalizado**: `_resolve_byok_openai_key()`
    (mantido, compat retroativa — `brain_assistant.py` continua preso a
    OpenAI especificamente, fora de escopo desta fase) ganhou irmã
    `_resolve_embedding_credentials()` (varre a mesma cadeia BYOK
    primária+fallback, mas filtra por `provider in
    embedding_capable_providers()`, não só `"openai"`).
    `get_openai_client()` (mantido, wrapper fino) ganhou irmã
    `get_embeddings_client(*, force_system_default=False)` — devolve
    `(client, provider, model, dimensions)`; com BYOK resolvido usa o
    provedor do usuário, sem BYOK ou `force_system_default=True` cai no
    padrão do sistema. Novo tipo `EmbeddingProviderUnavailable(RuntimeError)`
    (antes um `RuntimeError` genérico) — permite ao endpoint devolver um
    campo estruturado no 503 em vez de string. **Achado real durante a
    implementação**: mesmo com `force_system_default=True`, se a chave
    central estiver ausente, o sistema ainda tenta uma credencial
    `"openai"` do usuário disparador (nunca outro provedor) como
    fallback — preserva o fix da Fase 255 (BYOK cobre a ausência de
    chave central) sem reabrir o risco de usar um vetor Gemini pra
    consultar conteúdo público indexado em OpenAI. `embed_text`/
    `embed_batch` viraram wrappers finos sobre novas
    `embed_text_with_meta`/`embed_batch_with_meta` (retornam
    `(vetor(es), provider, model)`) — `embeddings_compare.py` (única
    ferramenta que só precisava do vetor) continua funcionando sem
    mudança.
  - **`rag/collections.py`**: as 8 collections ganharam
    `"embedding_provider": PayloadSchemaType.KEYWORD` em
    `payload_fields` — self-healed via `ensure_collections()` já
    idempotente (Fase 116/198), sem migração manual.
  - **`rag/ingestion.py` + `rag.py`**: `ingest_document(...,
    force_system_default=False)` grava `embedding_provider`/
    `embedding_model` REAIS no payload de cada chunk. `POST /rag/ingest`
    força `force_system_default=True` pras collections fora de
    `PRIVATE_COLLECTIONS` (públicas). Pipelines automáticas sem
    `user_id` (`sync_stj_diario`, `sync_legislacao`) passaram a declarar
    `force_system_default=True` explicitamente nos 2 call sites
    (`jurisprudencia_sync.py`/`legislacao_sync.py`) por clareza, embora
    já caíssem nesse comportamento naturalmente (sem contexto BYOK ativo
    em background).
  - **`rag/retrieval.py`** (ponto de maior risco): `retrieve()` passou a
    computar até 2 vetores da mesma pergunta — público (sempre
    `force_system_default=True`) e privado (BYOK ativo), conforme quais
    collections a busca abrange. Novo `_provider_filter()`: filtro
    `should` exigindo `embedding_provider == <provider>` OU (só quando
    `provider == "openai"`) o campo estar ausente — a compat retroativa
    documentada acima.
  - **Frontend**: `GET /users/me/ai-providers` já expunha
    `embedding_model`/`embedding_dimensions` de graça (endpoint já
    devolvia o dict inteiro `AI_PROVIDERS`, sem mudança de backend
    necessária). `minha-ia/page.tsx`: banner condicional trocou
    `!configs.some(c => c.provider === "openai" && c.enabled)` por
    `!configs.some(c => providers[c.provider]?.embedding_model &&
    c.enabled)`, texto agora lista dinamicamente os provedores
    embedding-capable do registro central em vez de hardcoded "OpenAI".
    `busca-juridica/page.tsx`: `error.toLowerCase().includes("openai")`
    (string sniffing) virou `needsEmbeddingProvider` (estado dedicado,
    lido de `detail.needs_embedding_provider` no corpo do 503 — `rag.py`
    passou a devolver `detail` como dict `{message,
    needs_embedding_provider}` só nesse caso específico, string simples
    nos demais erros).
  - **Testes**: `test_embeddings_byok.py` ganhou 12 testes novos
    (`_resolve_embedding_credentials()` — openai-only, gemini-only,
    prioridade entre os dois, anthropic-only→`None`, grok ignorado; e
    `get_embeddings_client()` — dispatch openai/gemini,
    `force_system_default` ignora BYOK, anthropic cai no padrão).
    `test_rag_search_byok_fase255.py` ganhou um teste de integração
    (Postgres+Qdrant real em memória) provando um tenant 100% Gemini
    BYOK ingerir+buscar numa collection privada sem NENHUMA chave OpenAI
    — incluindo um ponto legado tageado `"openai"` com vetor IDÊNTICO
    que precisa ficar de fora do resultado (prova de que é o filtro de
    provider, não a distância do vetor, que decide). 5 testes existentes
    (`test_rag_cache.py`, `test_rag_retrieval_real_qdrant.py`,
    `test_rag_ingest_tenant_stamping.py`,
    `test_google_drive_sync_dedup_real_qdrant.py`) tiveram seus
    monkeypatches de `embed_text`/`embed_batch` migrados pras novas
    `_with_meta`.
  - **Verificado**: `ruff`/`py_compile` limpos no backend;
    `tsc --noEmit`/`eslint` limpos no frontend; 48 testes automatizados
    relacionados a RAG/embeddings PASS isolados. **Achado de
    verificação**: a suíte HTTP real de `test_rag_search_byok_fase255.py`
    apresentou a mesma flakiness de pool asyncpg/pytest-asyncio já
    documentada (todos os testes `pytest.mark.anyio` desse arquivo
    falham com "attached to a different loop" nesta sessão, mesmo
    isolados) — confirmada contra um arquivo de controle NÃO tocado
    (`test_lgpd_erasure_reaches_crm_fase210.py`), que falha de forma
    idêntica, não é regressão desta fase. Prova real veio de um script
    standalone (`asyncio.run()` + `AsyncSessionLocal` direto, Postgres
    real + Qdrant em memória + `AsyncOpenAI` mockado) cobrindo os 13
    cenários do critério de aceite: tenant Gemini ingere/busca privado
    sem chave OpenAI nenhuma; busca pública do mesmo tenant sempre usa a
    chave central (nunca a BYOK Gemini dele) e ainda acha conteúdo
    legado sem `embedding_provider`; tenant 100% OpenAI (regressão)
    idêntico a antes; isolamento cross-tenant e cross-provider
    preservado; sem nenhuma chave disponível, `POST /rag/search` devolve
    503 com `needs_embedding_provider: true` estruturado — 13/13 PASS.
    Playwright real (Chromium do sandbox, stack completa) confirmando o
    banner dinâmico em `/minha-ia` (sem citar mais só "OpenAI") e o link
    "Ir para Minha IA" aparecendo em `/busca-juridica` só quando o erro é
    de fato falta de provedor de embedding — 7/8 checks PASS (a 1 falha
    é um warning de React key pré-existente em `/dashboard`, não
    relacionado a esta fase).
  - **Fora de escopo, documentado**: `deepseek`/`openrouter`/`ollama`/
    `vertex_ai` como provedores de embedding (capacidade não confirmada
    ou auth própria); reindexação em massa do conteúdo privado ao trocar
    de provedor (tag+filtro já evita resultado errado; "reindexar tudo"
    fica como possível fase futura); `brain_assistant.py`/
    `embeddings_compare.py` continuam presos a OpenAI especificamente
    (fora do escopo pedido, mantidos funcionando via os wrappers de
    compat retroativa); `TASK_LABELS` ganhar `rag_search`/`rag_ingest`
    explicitamente na UI de "Ajuste por área" (o fallback-chain já
    resolve sem precisar disso).
- **Fase pós-260.9** — usuário reportou "Deploy Ran Out of Memory!" no
  Railway (print do painel Cérebro → Insights, achado nº1 severidade ALTA
  especulando "possivelmente relacionado ao Orquestrador ou LLMs").
  **Causa raiz confirmada nesta sessão, não hipótese**:
  `get_orchestrator_graph()` (`app/agents/brain/orchestrator.py`) compilava
  o grafo com `checkpointer=MemorySaver()` — o checkpointer em memória de
  processo do LangGraph, sem TTL/eviction, guardando pra sempre o estado
  completo (`agent_results`, saída de LLM inteira) de todo `thread_id`
  (= todo `agent_run` disparado, 19 agentes nativos + custom). Achado-chave:
  **era código morto que ninguém desligou** — `chain_resume.py` e
  `approval.py` já documentavam desde a Fase 169.2/171 que a retomada de
  HITL foi reconstruída a partir de `AgentRun` justamente porque o
  checkpointer nunca sobreviveu entre processos; ninguém removeu a
  instanciação em si. `core/events.py::_background_warmup()` chama
  `get_orchestrator_graph()` no boot, então o singleton nascia cedo e
  crescia com o uso normal — em produção, **4 processos por container**
  (uvicorn + Celery principal + 2 filhos, `start.sh`) cada um com seu
  próprio `MemorySaver`, competindo pelo mesmo teto de memória do Railway.
  Datado via `git log -S`: o commit que tornou o checkpointer código morto
  é de 2026-08-14 — o vazamento rodou silenciosamente por 3+ semanas antes
  de bater no teto do plano. Diagnóstico confirmado por 5 verificações
  independentes (nenhum consumidor lê `get_state`/`.checkpointer`; o grafo
  nunca usa `interrupt_before`/`interrupt_after`; `checkpointer=None` é o
  próprio default documentado do LangGraph; testado ao vivo que
  `.ainvoke()` com `thread_id` roda sem checkpointer; é o único
  `MemorySaver`/`StateGraph` do sistema) e plano aprovado com o usuário.
  - **Achado de coordenação**: entre o diagnóstico e o push desta sessão,
    uma segunda sessão (disparada separadamente a partir do mesmo alerta de
    produção, PR #257 "Fix memory leak in LangGraph checkpointer") já havia
    corrigido a MESMA causa raiz de forma independente — `compile
    (checkpointer=None)`, com a mesma conclusão — e foi mergeada primeiro.
    A versão dela é ligeiramente mais completa: além de remover o
    `MemorySaver`, `AgentContext` ganhou `clear_transient()` (libera
    `audit_events`/`retrieved_memory`/`state` ao final do run,
    `agent_tasks.py::_run_async`), reduzindo retenção de memória residual
    mesmo sem o checkpointer. Nada nesta fase reabre `orchestrator.py`/
    `context.py`/`agent_tasks.py` — o fix já está em `main`, reconfirmado
    ao vivo (`get_orchestrator_graph().checkpointer is None`) e coberto por
    guarda de regressão nova (`tests/test_unit/
    test_orchestrator_no_checkpointer.py`, 5 testes: ausência do símbolo
    `MemorySaver` no módulo, singleton com `checkpointer=None`, `.ainvoke()`
    com `thread_id` funcionando sem checkpointer, docstring de
    `node_awaiting_approval` sem citar `MemorySaver` como ativo — prova
    bidirecional feita antes da coordenação ficar clara).
  - **Achado secundário 1, corrigido nesta fase (usuário confirmou
    incluir)**: `_com_timeout()` (`services/brain_infra.py`), usado por 5
    sondas (Celery/Redis/Qdrant/`_jobs`/`_fontes`), logava sempre o mesmo
    evento `brain_probe_timeout` sem dizer qual sonda nem a causa real — e
    o resumo que alimenta o LLM de Insights (`brain_insights.py::
    _resumo_logs()`) mandava só o *nome* do evento, nunca o `error=`. Foi
    isso que produziu a especulação sem base do insight nº1 do print (a
    sonda que falhou é 100% infraestrutura, sem nenhuma relação com
    LLM/Orquestrador). `_com_timeout` ganhou parâmetro `origem: str` (os 5
    call sites passam `"celery"|"redis"|"qdrant"|"jobs"|"fontes"`);
    `_resumo_logs()` ganhou `_formata_evento_log()` incluindo
    `(origem=...) — erro` na linha enviada ao LLM. Testes novos em
    `test_brain_infra.py`/`test_brain_insights.py`.
  - **Achado secundário 2, corrigido nesta fase (usuário confirmou
    incluir, não relacionado a memória)**: `system_map.py::
    construir_mapa()` gerava PDPJ como **dois nós** — `prov_pdpj` (do loop
    sobre `PROVIDERS`, `integration_hub.py`) e um `fonte_pdpj` hardcoded
    separado. Investigado antes de remover às cegas: são a MESMA
    credencial — `pdpj_fonte.py::para_tenant()` lê `integration_hub.
    get_credentials(db, tenant_id, "pdpj")`, a conexão do Hub. Consolidado
    no único nó `prov_pdpj`, com a metadata (`capabilities`/`credenciado`)
    preservada e a aresta `captura→pdpj` redirecionada. Teste de guarda
    `test_pdpj_nao_aparece_duplicado_no_mapa` novo; 1 teste pré-existente
    (`test_brain_fontes.py`, Fase 77/78) que ainda esperava o nó
    `fonte_pdpj` duplicado foi atualizado para o novo contrato.
  - **Fora de escopo, registrado**: separar uvicorn/Celery em serviços
    Railway distintos (mudança estrutural maior, não necessária); confirmar
    queda de memória real em produção (só observável pós-deploy, painel
    Railway/Cérebro→Infraestrutura — não medível deste sandbox).
  - **Verificado**: branch reiniciada a partir do `main` pós-#257 (PR
    anterior desta branch, #256, já estava mergeado — histórico não
    empilhado sobre trabalho já mergeado). Suíte completa na configuração
    exata do runner (banco do zero via `create_all`+
    `aplicar_ddl_idempotente`+seed, `REDIS_URL=` vazio) — `tests/test_unit/`
    926 passed/4 skipped, `tests/test_api/` 185 passed/9 skipped (2ª
    rodada contra o mesmo banco: 183 passed/11 skipped, mesma classe de
    skip condicional a rate-limit já documentada — sem regressão de
    ordem/estado). `ruff check app/` limpo. HTTP real contra `GET
    /system/brain/map` (SUPERADMIN) confirmando `prov_pdpj` como único nó
    PDPJ, com metadata e as 2 arestas (`hub→prov_pdpj`, `captura→
    prov_pdpj`) intactas. Confirmado ao vivo, no processo real da app,
    `get_orchestrator_graph().checkpointer is None`.
- **Fase pós-260.10** — usuário reportou "captura de publicações" e "busca
  de processos por OAB e UF" não funcionando, e pediu fonte alternativa
  pra "captura das partes do processo". Também pediu pra "informar ao
  DataJud que o sistema não possui uso comercial" — investigado e
  **descartado do escopo por decisão do usuário**: confirmado que a API
  pública do DataJud não tem nenhum mecanismo de registro/declaração de
  uso (nem no código, nem documentado pelo CNJ), e que a alegação em si
  seria factualmente incorreta (o AFJ é produto comercial pago) — via
  correta é contato formal com CNJ/parecer jurídico, fora do que este
  sandbox consegue fazer (egress bloqueado pros domínios do CNJ/PJe).
  - **Achado central**: os 2 primeiros sintomas têm a MESMA causa raiz,
    já diagnosticada e nunca corrigida —
    `backend/app/integrations/dje/comunica.py::buscar_comunicacoes()`
    (único ponto de consulta à Comunica/DJEN, usado tanto pela varredura
    diária de publicações quanto pela descoberta de processos por OAB+UF)
    recebe HTTP 403 do WAF do portal. Fase 250 (headers de navegador) e
    Fase 251 (fix não relacionado de circuit breaker) não resolveram; Fase
    252 confirmou que o 403 persistiu e parou no diagnóstico (captura do
    corpo da resposta), sem implementar correção. Como headers HTTP já
    foram descartados como suficientes, a causa mais provável é
    fingerprint na camada TLS (JA3) — limitação estrutural do stack TLS
    puro-Python do `httpx`, que nenhum header resolve.
  - **Correção**: cliente HTTP trocado de `httpx` pra `curl_cffi`
    (`curl_cffi==0.16.3`, wheel pré-compilada, mesma classe de dependência
    binária que `cryptography`/`psycopg2-binary` já usadas — sem mudança
    de Dockerfile necessária, ambos já usam `--prefer-binary`), com
    `impersonate="chrome124"` — reproduz o fingerprint TLS/JA3 real de um
    Chrome, técnica padrão da indústria pra esse cenário de WAF. `User-
    Agent`/`Accept`/`Accept-Language` deixam de ser setados manualmente
    (o `default_headers=True` padrão do `curl_cffi` já gera esse conjunto,
    consistente com o fingerprint); `Referer`/`Origin` seguem manuais
    (específicos deste contexto). Resto do arquivo (parsing, paginação,
    `stats`, o `except Exception` fail-soft) intocado — o contrato "nunca
    lança, sempre degrada" já vale automaticamente (exceções do
    `curl_cffi` também são `Exception`). Testado end-to-end neste sandbox
    contra `pypi.org` (domínio não-bloqueado) — `AsyncSession` com
    `impersonate="chrome124"` funciona de ponta a ponta (200, `.json()`).
    Corrige as 2 features de uma vez, já que ambas dependem do mesmo
    cliente.
  - **Achado secundário (não é bug, é lacuna de visibilidade)**: a
    captura de partes **já** tinha fonte alternativa ao DataJud —
    `oab_capture.py::_enriquecer_partes()` já busca via
    `fonte_partes_credenciada()` (PDPJ → Escavador → Judit → Jusbrasil,
    a que tiver credencial configurada em Integrações) — só que sem
    nenhuma configurada, devolvia silenciosamente `0`, sem sinal pro
    usuário de que a causa é falta de configuração, não erro. Corrigido:
    `_enriquecer_partes()` passa a devolver `{"total", "fonte_configurada"}`
    em vez de só o count (o chamador antes nem lia o retorno);
    `capturar_por_oab()` inclui os 2 campos em `resultado` (nos 3 pontos
    de retorno, pra shape consistente); `POST /tenant/oabs/capturar`
    apenda uma frase orientando a configurar uma das 4 fontes quando
    `partes_fonte_configurada` vier `False` — frontend
    (`JuridicoTab.tsx`) já renderiza `message` como vem, sem mudança
    necessária.
  - **Achado ao rodar a suíte, não hipótese**: `test_caminho_feliz_
    finaliza_ok` (`test_oab_capture_syncrun_erro.py`) mockava
    `_enriquecer_partes` com um fake devolvendo `None` (formato antigo,
    int implícito) — quebrou com `TypeError` assim que o retorno virou
    dict, exatamente o tipo de teste desatualizado que a suíte pega antes
    do CI. Corrigido pro novo contrato.
  - **Verificado**: prova bidirecional no fix do cliente HTTP — os 6
    testes de `test_comunica_diagnostico.py` (reescritos com fake
    `AsyncSession` monkeypatchada, já que `curl_cffi` não tem equivalente
    a `httpx.MockTransport`) falham todos ao reverter pra `httpx`, passam
    com o fix. Suíte completa na configuração exata do runner (banco do
    zero, `REDIS_URL=` vazio): `tests/test_unit/` 928 passed/4 skipped
    (+2 vs. antes desta fase), `tests/test_api/` 185 passed/9 skipped,
    sem regressão. `ruff check app/` limpo.
  - **O que este sandbox não pode provar**: se `impersonate="chrome124"`
    de fato derruba o 403 contra o Comunica/DJEN real — impossível testar
    daqui (egress bloqueado pros domínios `*.pje.jus.br`/`*.cnj.jus.br`,
    reconfirmado nesta fase). Correção é best-effort, baseada na prática
    padrão da indústria pra esse tipo de bloqueio — pedir ao usuário pra
    testar em produção pós-deploy e reportar o resultado (sucesso, ou o
    novo `body_snippet`, que ajuda a próxima investigação se ainda
    falhar).

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

**Rodadas registradas** (1-2 linhas cada; detalhe em `HISTORICO_FASES.md`):
- **pós-255** — reconfirmou as Fases 247-255; achou 8 gaps de LGPD + o bug
  do `RateLimitMiddleware`. **Nenhum deles foi corrigido até hoje.**
- **pós-260.5** — auditou pela 1ª vez o próprio aparato de qualidade (a
  suíte nunca rodou no CI; causa-raiz da flakiness isolada), trocou a
  auditoria de LGPD por tabela pela **varredura de sentinela** (achou 2
  colunas novas que 8 rodadas não viram: `documents.titulo` e
  `opportunities.titulo`), e provou a classe "gate de papel só na
  navegação". **Deixou pra próxima**: as 20 falhas + 78 erros residuais da
  suíte, o fluxo de escrita de `portal`/`billing`/`publications`,
  `ContractAgent`/`OrchestrationAgent`/`poll_all_processes` (zero testes),
  e o cache do `retrieve()` sem provedor na chave.
  **Correção pós-260.5 (2 fases seguintes, já aplicadas)**: os 7 itens do
  plano consolidado foram implementados. Primeiro os 3 aprovados — plugin
  async duplicado desligado, gate de CI ligado e as 5 colunas de PII do
  esquecimento fechadas com a varredura de sentinela virando teste. Depois os
  4 restantes: `tests/test_api/` zerado (27 falhas + 75 erros → 0) e promovido
  a gate; rate limiter com TTL garantido e auto-curável; gates de papel que só
  existiam no menu fechados em 10 rotas; e o provedor de embedding na chave de
  cache do `retrieve()`. **A lista de "deixou pra próxima" está esgotada**,
  incluindo `ContractAgent`/`OrchestrationAgent`/`poll_all_processes`, que
  ganharam 28 testes na fase seguinte — e essa fase achou nos três o mesmo
  padrão: **falha aparecendo como sucesso**, corrigido em 4 pontos.

Histórico completo (achados, decisões de escopo, correções, verificações
empíricas de cada fase) fica em `HISTORICO_FASES.md` — movido pra fora
deste arquivo pra não inflar o contexto carregado em todo turno.
**Leia-o antes de planejar uma nova rodada de teste geral**: é onde cada
rodada anterior registrou o que cobriu e o que deixou pra trás
propositalmente, exatamente o insumo que a regra fixa acima pede.

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
- **Retenção de auditoria (LGPD)** — **levantamento técnico pronto em
  `docs/juridico/RETENCAO_AUDIT_LOGS.md`** (fase pós-260.6); segue travado
  na decisão do escritório, que é quem define o prazo. `audit_logs` cresce
  indefinidamente (1 linha por request de escrita autenticado, não por
  evento de negócio) sem nenhuma rotina de expurgo/arquivamento, e a LGPD
  pede retenção limitada de dado pessoal. **Duas correções ao que este
  parágrafo dizia antes, ambas medidas, não deduzidas**:
  - **A tabela NÃO é imutável.** `trg_audit_logs_immutable` só existe na DDL
    de `alembic/versions/001_initial_schema.py:415-428`, e `alembic upgrade
    head` **falha incondicionalmente** — `alembic.ini:6` declara
    `sqlalchemy.url = %(DATABASE_URL)s`, interpolação que o configparser não
    resolve, e o erro acontece no carregamento do config, antes de qualquer
    conexão (reproduzido com `DATABASE_URL` exportado). Como `start.sh:52-54`
    roda a migração em best-effort e cai em `create_all` (que não cria
    trigger), o banco real não tem a trava: no banco local desta sessão,
    `pg_trigger` para `audit_logs` volta **vazio**, não existe
    `alembic_version`, e `UPDATE`/`DELETE` numa linha **executam** (testado
    dentro de transação desfeita, 3.948 linhas intactas). **Não confundir
    com deriva de schema**: a migração 001 cria a tabela sem
    `user_agent`/`session_id`; como ela nunca roda, o schema vem do model
    atual e essas colunas existem. Produção não foi verificada (sem acesso);
    o dossiê traz o SQL read-only.
  - **A superfície de PII é menor do que se registrava.** O middleware
    (`core/middleware.py:88-115`) grava sempre `ip_address`/`user_agent`/
    `user_id`, mas **nunca** `old_value`/`new_value`, e nunca corpo de
    request, query string ou outro header. `old_value`/`new_value` só vêm de
    3 call sites (`approvals.py:209-210`, `google_integration.py:200`,
    `financial.py:358-364`) — medido: 40 e 46 linhas de 3.948 (~1%).
  - Medição local (12 dias): 3.948 linhas, ~329/dia, 1.384 kB ⇒ ~0,35 kB por
    linha; 88,6% vêm do middleware, 11,4% dos call sites explícitos.
  - **Nó a resolver**: `erase_client_data` nunca toca linhas pré-existentes
    de `audit_logs` e o teste de sentinela exclui 4 colunas dela de propósito
    (`test_lgpd_sentinela.py:31-39`) — justificando pela imutabilidade que a
    verificação acima não confirmou; e a exclusão não cobre `user_agent`/
    `ip_address`. O log é a prova do esquecimento e o último lugar onde o
    esquecido sobrevive.
  - **Corolário de engenharia — RESOLVIDO na fase pós-260.7** (não era o
    débito jurídico, mas nasceu dele): o alembic estava quebrado e nenhuma
    migração jamais rodava. Consertado; o trigger **continua deliberadamente
    não criado** em nenhum caminho (é a pergunta 6 do dossiê, do escritório).
    Ver a armadilha "Alembic" abaixo.
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
  não resolvida arbitrariamente. **Levantamento técnico pronto em
  `docs/juridico/DATAJUD_TERMO_DE_USO.md`** (fase pós-260.6), com 4 achados
  que o parecer precisa ter na mão:
  - **Não existe credencial por escritório** — `CNJ_API_KEY`
    (`config.py:57-61`) tem como default a chave que o próprio CNJ publica
    na wiki, embutida no código. Toda instalação chama com a mesma chave, e
    não há registro de aceite de termo em lugar nenhum. Muda a pergunta de
    "o escritório aceitou ao se credenciar?" para "existe aceite?".
  - **O dado derivado sai do escritório** — `GET /portal/processes/{id}`
    (`portal.py:146-217`) entrega até 30 movimentações **com o resumo por
    IA** ao cliente final, e é justamente a tela que **não** atribui a fonte
    (as 3 telas que dizem "CNJ DataJud" são todas internas). É o ponto
    central pra leitura de "distribuir informação derivada".
  - **Segunda camada de derivação**: `ai_summary` gerado por LLM
    (`process_agent.py:104-122`), detecção de prazo, e `citacao_check`
    carimbando "confirmada"/"não verificável" dentro de **petições
    protocoláveis** (`documents.py:1012`, `petition_agent.py:131`).
    Verificado que NÃO acontece: export CSV/PDF/XLSX, e-mail/WhatsApp,
    webhook, API pública própria, ingestão no RAG.
  - **Não há kill switch, mas há alternativa desligada** —
    `registry.py:14-20` instancia `DataJudFonte()` incondicionalmente e
    `processes.py:762` instancia o cliente direto; sem flag por env ou por
    tenant. Em compensação, PDPJ/Escavador/Judit/Jusbrasil **já implementam
    `movimentos()`** e nenhum caminho de produção as chama pra isso (só pra
    partes, `oab_capture.py:128-164`) — trocar de fonte é ligar peça
    existente, o custo real é comercial, não técnico.
