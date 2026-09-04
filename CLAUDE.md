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

- **Flakiness de pool asyncpg/pytest-asyncio**: testes que abrem
  `AsyncClient` HTTP real falham intermitentemente com "attached to a
  different loop" (causa raiz: engine assíncrono do SQLAlchemy é
  singleton de módulo, mas `pytest-asyncio` cria um event loop por
  teste por padrão). Reproduz mesmo isolado às vezes. Antes de tratar
  como regressão de uma mudança, rodar um teste de controle **não
  tocado** — se ele falhar do mesmo jeito, não é a sua mudança. A prova
  real de um fix costuma vir de um script standalone
  (`asyncio.run()` + `AsyncSessionLocal` direto, fora do pytest) contra
  Postgres real, não da suíte.
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
