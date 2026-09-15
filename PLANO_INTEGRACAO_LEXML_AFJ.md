# Plano de Integração do LexML ao AFJ CORE SYSTEM

> **Status**: plano. Nenhuma linha de código foi alterada para produzi-lo.
> **Base**: auditoria do repositório em 15/09/2026 (3 agentes, leitura direta,
> tudo citado com `arquivo:linha`).
> **Método**: nada aqui foi assumido a partir do enunciado. Onde o repositório ou
> a documentação oficial do LexML não puderam confirmar um fato, está escrito
> **NÃO VERIFICADO**.

---

## 1. Resumo executivo

### 1.1 Duas correções de premissa, antes de tudo

**O LexML já está integrado ao AFJ.** O pedido foi redigido como se a integração
não existisse. Ela existe e roda em produção:

| Peça | Arquivo | Desde |
|---|---|---|
| Cliente SRU | `backend/app/integrations/lexml/client.py` (226 linhas) | antes desta sessão |
| Pipeline diária 06:00 | `backend/app/workers/tasks/legislacao_sync.py` | Fase 138.3 |
| Collection vetorial | `legislacao` em `backend/app/rag/collections.py:80-92` | — |
| Consulta **ao vivo** | `backend/app/services/citacao_check.py:53-77` chama `buscar_lei()` | — |

Consequência prática: isto **não é uma integração nova**. É a evolução de uma que
já funciona, e a maior parte do valor está em fechar as lacunas dela — não em
construir do zero. Essa diferença muda o cronograma, o risco e o custo.

**A stack presumida no pedido não é a deste sistema.** O enunciado pede para
examinar `package.json`, Supabase, Edge Functions e RLS. Medido:

- `grep -ri supabase` no repositório inteiro — **incluindo `backend/venv/` com
  todos os `site-packages` instalados** — retorna exatamente 2 arquivos, ambos
  prosa: `DEPLOY.md:60,64,86,104` e `HISTORICO_FASES.md:397`, descartando-o como
  opção de Postgres gerenciado por causa do teto de 500 MB do plano free. Não
  existe nem como dependência transitiva instalada.
- **Nenhuma Edge Function, nenhum Deno.** Os únicos hits de `edge function` no
  repositório são falso-positivo de teoria dos grafos dentro do `networkx`
  instalado no venv (funções sobre *arestas*). O deploy é container Docker
  (Railway) + Next.js na Vercel.
- **Nenhum RLS.** `CREATE POLICY` / `ROW LEVEL SECURITY` não aparecem em
  `backend/app/`, `backend/alembic/` nem no `DDL_IDEMPOTENTE`. O isolamento
  entre escritórios são **191 filtros manuais** `Model.tenant_id ==
  current_user.tenant_id`, sem helper de escopo — convenção, não mecanismo.

O plano abaixo é escrito contra a arquitetura real: FastAPI 0.115 +
SQLAlchemy 2.0 async + asyncpg + PostgreSQL (Railway) + Redis + Qdrant + Celery,
Python 3.12 em produção.

### 1.2 O que será feito

Entregar as duas metades que hoje faltam, aproveitando o que já existe:

1. **Pesquisa ao vivo** — o advogado consulta o acervo LexML pela tela, com
   filtros, e vê resultados que ainda não entraram na base local.
2. **Acervo estruturado** — normas com URN, tipo, ano, órgão e ementa numa
   tabela consultável; favoritar, vincular a processo/documento, citar.

### 1.3 Por que desta maneira

- **Acervo compartilhado entre escritórios** (decisão do usuário): uma Lei
  federal é a mesma para todos. Ingerir uma vez, todos consultam — é como a
  collection `legislacao` já funciona. Só o que é do escritório (favorito,
  vínculo, anotação) fica por `tenant_id`.
- **Metadados + link, texto sob demanda** (decisão do usuário): o LexML é um
  agregador de metadados; o texto integral vive no órgão de origem. Guardar
  cópia integral de todo o acervo seria replicação de conteúdo de terceiro num
  produto comercial — a mesma classe de questão já registrada neste projeto
  sobre o Termo de Uso do DataJud, hoje aguardando parecer jurídico
  (`docs/juridico/DATAJUD_TERMO_DE_USO.md`).
- **Sem banco de grafos, sem pgvector**: justificado nas seções 15 e 16.

### 1.4 Ordem exata de implementação

Fase 0 (sonda + 3 correções) → Fase 1 (acervo) → Fase 2 (pesquisa ao vivo) →
Fase 3 (tela e vínculos) → Fase 4 (grafo e citação, condicional) → Fase 5
(ampliação). Detalhe na seção 20.

### 1.5 Riscos principais

O maior risco não é técnico: **não foi possível alcançar `lexml.gov.br` deste
ambiente** (egress bloqueado, confirmado por `curl` e `WebFetch`). Os nomes das
tags do XML, os índices CQL aceitos e os limites de requisição continuam não
confirmados — e o próprio código existente admite isso (`client.py:6-11`). Por
isso a Fase 0 começa com uma sonda real antes de qualquer código novo.

---

## 2. Arquitetura atual encontrada

### 2.1 Stack

| Camada | Tecnologia | Evidência |
|---|---|---|
| Frontend | Next.js 14.2.18 (App Router), React 18.3, TypeScript 5.7, Tailwind 3.4 | `frontend/package.json` |
| Backend | FastAPI 0.115.14, Starlette 0.46.2, uvicorn 0.32.1 | `backend/app/main.py:45-52` |
| Runtime | Python 3.12 (produção), 3.11 (venv local) | `Dockerfile:6` |
| ORM | SQLAlchemy 2.0.49 async + asyncpg 0.30 | `backend/app/db/base.py:39-56` |
| Banco | PostgreSQL (Railway) | `backend/app/config.py:17-21` |
| Cache/fila | Redis 5.3.1 + Celery 5.6.3 | `backend/app/db/redis.py`, `backend/app/workers/worker.py` |
| Vetorial | Qdrant 1.18, 8 collections, 3072 dims | `backend/app/rag/collections.py` |
| IA | Anthropic + OpenAI + Gemini, BYOK por usuário | `backend/app/integrations/llm_client.py` |
| Storage | S3-compatível (aioboto3), fallback base64 inline | `backend/app/integrations/object_storage.py` |
| Observabilidade | structlog 24.4 + Sentry (opcional) | `backend/app/main.py:19-43` |

### 2.2 O que já existe de LexML — inventário

**Cliente** (`backend/app/integrations/lexml/client.py`):

- `LEXML_SRU_URL = "https://www.lexml.gov.br/busca/SRU"` (`:24`)
- Protocolo **SRU 1.1**, resposta XML. **Não há OAI-PMH. Não há JSON.**
- Duas chamadas distintas:
  - `buscar_lei(referencia)` (`:56-81`) — `operation=searchRetrieve`,
    `version=1.1`, `query=<referência crua>`, `maximumRecords=1`. Nota: o
    `query` **não é CQL** aqui, é a string crua (`"8078/1990"`).
  - `buscar_lote_legislacao(tipo_norma)` (`:132-153`) — `query=localidade=federal
    and tipoDocumento={Lei|Decreto}`, `maximumRecords=50`. **Este sim é CQL.**
- `TIPOS_NORMA_SUPORTADOS = ("Lei", "Decreto")` (`:95`) — só isso, só federal.
- Parser: `xml.etree.ElementTree` (`:15`), casando por **nome local** da tag e
  descartando namespace (`_local()`, `:29-30`).
- Campos extraídos: `numberOfRecords`, `title`, `urn` (`:44-48`); URL tentada em
  três tags alternativas — `_URL_TAGS = ("location", "url", "identifier")`
  (`:97`).
- **O texto integral não vem do LexML**: `baixar_texto_norma(url)` (`:173-204`)
  faz GET na URL de publicação que veio no XML (na prática `planalto.gov.br`) e
  raspa com BeautifulSoup + lxml.
- `CircuitBreaker(name="lexml")` module-level (`:26`), timeout 15s.
- **Sem retry. Sem User-Agent** — usa o default do httpx.

**Pipeline** (`backend/app/workers/tasks/legislacao_sync.py`):

- Beat: 06:00 diário (`worker.py:124-127`), `TaskLock` ttl 2100s,
  `time_limit=1800`, `soft_time_limit=1500`, `max_retries=3`.
- Idempotência por URN via `JurisprudenciaIngerida` (unique `(fonte,
  fonte_documento_id)`) — é o "cursor implícito" da pipeline.
- Grava no Qdrant com `ingest_document(collection="legislacao",
  document_id=urn, force_system_default=True)` (`:81-90`).
- Status final honesto: `"OK" if falhas == 0 else "ERRO"` (`:110`).

### 2.3 Sistema de pesquisa existente

- `retrieve()` (`backend/app/rag/retrieval.py:51`) — busca vetorial com cache
  Redis (TTL 300s), `score_threshold=0.35`, filtro por `embedding_provider`,
  e **dois vetores por busca** (público com provedor do sistema, privado com
  BYOK do usuário).
- `POST /rag/search` (`backend/app/api/v1/rag.py:53`) — gate de 5 papéis;
  aceita `filters` de **igualdade exata apenas**; sem paginação, sem ordenação,
  sem range de data, sem busca lexical.
- Tela `/busca-juridica` — chips de collection, `k=8` fixo, sem filtros de
  metadado, sem paginação, sem destaque de termos. O campo `filters` da API
  **nunca é preenchido pelo frontend**.

### 2.4 Autenticação e autorização

- `require_role(*roles)` (`backend/app/dependencies.py:59-65`) — **`SUPERADMIN`
  passa sempre**, de graça.
- `_BLOCK_STAFF` (`backend/app/api/v1/router.py:26`) = bloqueio por
  inadimplência + fronteira de confiança (papel `CLIENT` só alcança
  `/portal/*` e `/auth/*`). É o default dos routers de negócio, incluindo `rag`.
- **Aviso registrado no `CLAUDE.md:275-278`**: existem três mecanismos de gate
  coexistindo (`Depends(require_role)`, checagem inline, helper local). Auditar
  só um produz falso positivo.

### 2.5 Evolução de schema

**Não existe migration como mecanismo de evolução.** O schema nasce de
`Base.metadata.create_all` (`backend/app/core/events.py:586-588`) mais o bloco
`DDL_IDEMPOTENTE` (`:22-356`, ~180 statements), aplicado a **todo boot** com
cada statement em transação própria e fail-soft (`aplicar_ddl_idempotente`,
`:359-372`).

**Regra explícita: nunca rodar `alembic upgrade head` cru.** As 4 migrações
conhecem 26 tabelas; o app tem 58. A regra "carimbar, nunca migrar" vive em
`backend/alembic_boot.sh` e está documentada em `CLAUDE.md:290-302`.

---

## 3. Arquitetura proposta

```
Tela /busca-juridica  ▸ aba "Legislação"
        │   filtros: texto, tipo, ano, órgão, URN
        ▼
GET  /api/v1/lexml/normas          ← acervo local (Postgres) — rápido, sempre
POST /api/v1/lexml/buscar          ← consulta ao vivo (SRU) — quando o local não basta
        │
        ▼
services/lexml_acervo.py           ← cache → acervo → SRU; normaliza, dedup por URN, persiste
        │
        ├──► integrations/lexml/client.py   (estendido: CQL com filtros, paginação)
        ├──► Redis                          (cache de resposta SRU)
        └──► PostgreSQL
                ├── lexml_normas        (compartilhada, sem tenant_id)
                └── lexml_norma_tenant  (por escritório: favorito, vínculo, anotação)
                        │
                        └──► Qdrant `legislacao` (inalterado)
```

### 3.1 Decisões e justificativas

| Decisão | Por quê |
|---|---|
| **Service layer**, não lógica no endpoint | O fluxo tem três caminhos (cache → acervo → SRU) e persiste o que descobre. É lógica de negócio. Precedente: `services/oab_capture.py`, `services/citacao_check.py`. |
| **Síncrono**, não fila | A busca é síncrona do ponto de vista do usuário. Celery fica onde já está: a ingestão diária. Precedente para ação manual com rede externa: `POST .../sync-now`, `POST /tenant/oabs/capturar`. |
| **Sem Edge Function / API Route** | Não existem nesta stack. |
| **Cron**: mantém o existente (06:00) | A Fase 5 troca a dedup-como-cursor por cursor de data, sem mudar o agendamento. |
| **Cache Redis** | Padrão já estabelecido em `rag/retrieval.py:24-48`. |

### 3.2 Convenções herdadas (não inventar nada novo)

- Router com `_BLOCK_STAFF`, gate por `Depends(require_role(...))` na
  assinatura — nunca checagem inline.
- Erros via `core/exceptions.py` (`NotFoundError`, `ValidationError`,
  `ForbiddenError`), que herdam de `HTTPException`. Handler global para o resto
  em `main.py:72-75`.
- Chamada externa dentro de closure passada a `CircuitBreaker.run(...)`, que
  **nunca propaga exceção**; status != 200 vira `RuntimeError` para o breaker
  contar a falha. Timeout explícito sempre.
- `structlog` com nome de evento snake_case + kwargs; exceção como
  `error=str(exc)`.

---

## 4. Diagnóstico de compatibilidade

| Área | Compatível? | Observação |
|---|---|---|
| Padrão de integração externa | ✅ | O cliente LexML já segue (breaker, timeout, fail-soft) |
| Multi-tenant | ⚠️ | Acervo é **compartilhado** — exceção deliberada, igual à collection `legislacao`. A tabela por tenant segue o padrão normal. |
| Schema | ✅ | `create_all` + `DDL_IDEMPOTENTE`; nenhuma migration nova |
| RAG | ✅ | Nada muda no Qdrant, exceto corrigir um índice faltante |
| Frontend | ✅ | Aba dentro de tela existente, componentes e classes reaproveitados |
| LGPD | ⚠️ | `lexml_norma_tenant` entra no erasure; `lexml_normas` não (norma é pública) |
| Gate de papel | ✅ | `_BLOCK_STAFF` + `require_role` |

### 4.1 Conflitos identificados

1. **`document_id` sem índice na collection `legislacao`** — bug latente real.
   `legislacao_sync.py:88` chama `ingest_document(document_id=urn)`, mas
   `collections.py:80-92` não declara `document_id` em `payload_fields`. As três
   collections que usam `delete_document_chunks()` declaram, e o comentário em
   `collections.py:43` registra que sem o índice o Qdrant responde HTTP 400.
   **Efeito**: reingerir uma norma duplicaria chunks em vez de substituí-los.
2. **Breaker `"lexml"` invisível no painel Cérebro** — LexML não é uma
   `FonteProcessual` e não está no `registry.py` (que só tem Comunica e
   DataJud). O estado é persistido em `circuit_breaker:lexml` no Redis, mas
   nenhuma tela o lê.
3. **Registrar os models em `app/models/__init__.py`** — armadilha documentada:
   model fora dali só entra no metadata por import de runtime, e o autogenerate
   do Alembic propõe `DROP TABLE`. Há guarda
   (`test_schema_metadata_guard.py`).

---

## 5. Dependências

**Nova**: `defusedxml` (ver seção 10). É a única.

**Não serão adicionadas**, e por quê:
- `lxml` para o SRU — já está no projeto (usado pelo BeautifulSoup), mas
  `ElementTree` + `defusedxml` basta e mantém o parser atual.
- Biblioteca de grafo (Neo4j, networkx) — ver seção 16.
- `pgvector` — ver seção 15.

---

## 6. Modelo de dados

### 6.1 `lexml_normas` — acervo compartilhado

`tenant_id` **ausente de propósito** (mesma decisão já aplicada à collection
`legislacao`).

| Campo | Tipo | Nota |
|---|---|---|
| `id` | UUID PK | só para FK interna |
| `urn` | VARCHAR(500) **UNIQUE NOT NULL** | **chave natural** — identificador jurídico externo |
| `titulo` | TEXT | |
| `ementa` | TEXT NULL | **NÃO VERIFICADO** se o SRU retorna ementa |
| `tipo_norma` | VARCHAR(80) | "Lei", "Decreto", … |
| `numero` | VARCHAR(40) NULL | derivado da URN quando possível |
| `ano` | INTEGER NULL | idem |
| `autoridade` | VARCHAR(160) NULL | |
| `localidade` | VARCHAR(80) NULL | "br", "br;sp", … |
| `data_publicacao` | DATE NULL | |
| `url_fonte` | TEXT NULL | link oficial (Planalto etc.) |
| `texto_integral` | TEXT NULL | preenchido **sob demanda** |
| `texto_obtido_em` | TIMESTAMPTZ NULL | idade do cache de texto |
| `metadata_json` | JSONB | o que o SRU trouxer e não couber acima |
| `created_at` / `updated_at` | TIMESTAMPTZ | padrão do projeto |

Índices: `urn` (unique), `(tipo_norma, ano)`, GIN FTS sobre `titulo || ementa`.

**Campos do enunciado deliberadamente omitidos**: `fonte` (é sempre LexML nesta
tabela — redundante), `status` (não há máquina de estados; `texto_obtido_em`
nulo já expressa "sem texto"), `data_assinatura` (**NÃO VERIFICADO** se
disponível), `orgao` (coberto por `autoridade`).

### 6.2 `lexml_norma_tenant` — o que é do escritório

| Campo | Tipo |
|---|---|
| `id` | UUID PK |
| `tenant_id` | UUID FK `tenants.id` ON DELETE CASCADE, indexado |
| `norma_id` | UUID FK `lexml_normas.id` ON DELETE CASCADE |
| `favorito` | BOOLEAN default false |
| `process_id` | UUID FK `legal_processes.id` ON DELETE CASCADE, NULL |
| `document_id` | UUID FK `documents.id` ON DELETE CASCADE, NULL |
| `anotacao` | TEXT NULL |
| `created_by` | UUID FK `users.id` |
| `created_at` | TIMESTAMPTZ |

Unique `(tenant_id, norma_id, process_id)`.

### 6.3 Tabelas avaliadas e NÃO propostas agora

- **`fontes`** — só há uma fonte nesta tabela. Redundante.
- **`versões` / `alterações`** — depende de o LexML expor a cadeia de versões:
  **NÃO VERIFICADO**. Fase 5.
- **`relacionamentos` / `citações`** — Fase 4, condicional (seção 16).
- **`indexação`** — o Qdrant já é o índice.
- **`favoritos`** — coberto por `lexml_norma_tenant.favorito`.
- **`histórico de pesquisas`** — não existe precedente no projeto e não foi
  pedido como requisito funcional. Fica registrado, não implementado.

### 6.4 Migrations propostas

**Nenhuma migration Alembic.** Seria código morto, como as 4 existentes. O
procedimento correto neste projeto:

1. Declarar os models em `backend/app/models/lexml.py`.
2. Registrá-los em `backend/app/models/__init__.py`.
3. `create_all` os cria no boot.
4. Acrescentar ao `DDL_IDEMPOTENTE` (`backend/app/core/events.py:22`) **apenas
   o que `create_all` não faz** — no formato já usado:

```
"CREATE INDEX IF NOT EXISTS ix_lexml_normas_tipo_ano ON lexml_normas (tipo_norma, ano)",
"CREATE INDEX IF NOT EXISTS ix_lexml_normas_fts ON lexml_normas
   USING GIN (to_tsvector('portuguese', coalesce(titulo,'') || ' ' || coalesce(ementa,'')))",
```

---

## 7. APIs

Todas em `backend/app/api/v1/lexml.py`, router montado com `_BLOCK_STAFF`.

| Método | Rota | Gate | Descrição |
|---|---|---|---|
| GET | `/lexml/normas` | 5 papéis (igual `/rag/search`) | Acervo local, filtros + paginação |
| GET | `/lexml/normas/{urn}` | 5 papéis | Detalhe; `?incluir_texto=true` busca sob demanda |
| POST | `/lexml/buscar` | 5 papéis | Consulta ao vivo no SRU |
| POST | `/lexml/normas/{urn}/acervo` | ADVOGADO+ | Adiciona ao acervo do escritório |
| DELETE | `/lexml/normas/{urn}/acervo` | ADVOGADO+ | Remove |
| POST | `/lexml/normas/{urn}/vincular` | ADVOGADO+ | Vincula a processo/documento |

Resposta de erro segue `core/exceptions.py`; indisponibilidade do LexML devolve
503 com `detail` estruturado distinguindo **"não encontrei"** de **"não consegui
consultar"** — a mesma distinção que esta base de código já teve de corrigir em
quatro lugares diferentes.

---

## 8. Fluxos

### 8.1 Pesquisa

```
Usuário digita "Lei 14.133/2021"
        │
        ▼
   Cache Redis?  ──sim──► devolve
        │ não
        ▼
   Acervo local (Postgres FTS + filtros)
        │
        ├── resultados suficientes ──► devolve (origem: acervo)
        │
        └── poucos/nenhum ──► consulta SRU ao vivo
                                    │
                                    ├── erro/timeout ──► devolve o que o acervo tinha
                                    │                     + aviso honesto de indisponibilidade
                                    ▼
                              normaliza URN → dedup → UPSERT em lexml_normas
                                    │
                                    ▼
                              devolve (origem: LexML) + grava cache
```

### 8.2 Texto integral sob demanda

```
Usuário abre a norma
        │
        ▼
texto_integral preenchido e texto_obtido_em recente? ──sim──► devolve
        │ não
        ▼
baixar_texto_norma(url_fonte)  ← já existe (client.py:173)
        │
        ├── sucesso ──► grava texto_integral + texto_obtido_em ──► devolve
        └── falha ────► devolve metadados + link para a fonte oficial,
                        dizendo que o texto não pôde ser obtido
```

---

## 9. Interface

**Aba "Legislação" dentro de `/busca-juridica`** — não uma tela nova. O sistema
já tem uma tela de Pesquisa Jurídica, e criar uma segunda fragmentaria o fluxo.

Reaproveitar, sem inventar identidade visual nova:
`.afj-card`, `.afj-table`, `.afj-page-header`, `.afj-section-header`,
`.btn-afj-primary`, `.btn-afj-outline`, `.afj-empty-state`; componentes
`EmptyState`, `Skeleton`/`SkeletonTable`, `AlertBanner`, `useToast`,
`useConfirmDialog`.

Nota factual sobre o design system: **não existem componentes `Button`, `Input`,
`Select`, `Modal` ou `Table` reutilizáveis** em `frontend/src/components/ui/`
(só `AlertBanner`, `EmptyState`, `Skeleton`, `Toast`, `ViewToggle`). As telas
montam esses elementos inline com as classes `afj-*`. A aba nova seguirá a mesma
convenção — não é o momento de introduzir uma biblioteca de componentes.

Filtros na primeira entrega: texto livre, tipo de norma, ano, órgão/autoridade,
URN. Paginação server-side real. Ordenação por relevância e por data.

Por resultado: metadados, badge de origem (acervo × LexML ao vivo), abrir fonte
oficial, ver texto (sob demanda), copiar URN, adicionar ao acervo, favoritar,
vincular a processo/documento.

Gate: `/busca-juridica` é `roles: null` (`nav.ts:59`), então a aba herda isso.
As ações de escrita seguem o gate do endpoint.

---

## 10. Segurança

### 10.1 XML externo — medido, não suposto

Rodei os dois ataques clássicos contra o parser em uso (Python 3.11.15):

| Ataque | Resultado |
|---|---|
| **XXE** — entidade externa apontando para `file:///etc/passwd` | **Recusado** — `ParseError: undefined entity`. `xml.etree.ElementTree` não resolve entidades externas. |
| **Expansão de entidade interna** (billion laughs) | **Passa** — o parser expandiu normalmente. |

Conclusão honesta: **a preocupação com XXE do item 11 do enunciado não se aplica
a este parser.** O vetor real é DoS de memória por expansão de entidade, não
leitura de arquivo. `defusedxml` **não está instalado**.

**Mitigação proposta**: adicionar `defusedxml` e trocar `ET.fromstring` por
`defusedxml.ElementTree.fromstring`, mais um teto de tamanho de resposta antes
do parse. Custo baixo, fecha o vetor que existe.

### 10.2 Demais itens

| Item | Situação |
|---|---|
| Autenticação | Herdada — JWT + `get_current_user` |
| Autorização | `_BLOCK_STAFF` + `require_role` |
| RLS Supabase | **Não se aplica** — não há Supabase nem RLS neste sistema |
| Exposição de endpoints | Nenhum endpoint público novo; tudo autenticado |
| Chaves/secrets | **O LexML é API aberta, sem autenticação** — não há segredo a proteger |
| Rate limiting | `RateLimitMiddleware` já cobre; o limite *do lado do LexML* é **NÃO VERIFICADO** |
| **SSRF** | **Risco real, não teórico**: `baixar_texto_norma(url)` faz GET numa URL **que veio da resposta externa**. Hoje sem validação. Mitigação: allowlist de domínios (`planalto.gov.br`, `lexml.gov.br`, domínios `.gov.br`), rejeitar IP literal, rejeitar redirect para host fora da allowlist. |
| Injeção SQL | ORM parametrizado; sem SQL cru na feature |
| Sanitização de HTML | O texto do Planalto já passa por BeautifulSoup com remoção de `script`/`style`; renderizar como **texto puro**, nunca `dangerouslySetInnerHTML` |
| Controle de acesso ao acervo interno | `lexml_norma_tenant` filtrado por `tenant_id` em toda query |

---

## 11. LGPD e governança

### 11.1 Classificação

| Categoria | Tratamento |
|---|---|
| **Dado público** (texto de lei, ementa, URN) | Não é dado pessoal. `lexml_normas` **fora** do erasure. |
| **Dado pessoal em norma** | Raro, mas possível (nome em decreto de nomeação). Não é dado do *cliente* do escritório; não há base para apagá-lo do acervo público. Registrado. |
| **Dado do escritório** (`anotacao`, vínculo a processo) | **Entra no erasure** — `process_id` é alcançável a partir do cliente. |
| **Dado do cliente** | Não trafega nesta feature. |

### 11.2 O checklist obrigatório

O `CLAUDE.md` registra que "tabela nova com vínculo a `clients.id` esquecida
pelo erasure" já se repetiu **9+ vezes** neste projeto. `lexml_norma_tenant` tem
vínculo **transitivo** (`process_id → legal_processes.client_id`), exatamente o
caso que a regra cobre.

Ação: incluir a tabela em `erase_client_data` e `export_client_data`
(`backend/app/api/v1/lgpd.py`), anonimizando `anotacao` com o placeholder já
padronizado (`"[Conteúdo removido — LGPD art. 18 IV]"`) e preservando o vínculo
estrutural.

O teste de sentinela (`test_lgpd_sentinela.py`) varre o banco inteiro por valor
e pegaria a falha — **desde que a tabela seja preenchida no cenário do teste**.
Isso precisa ser explicitado, senão a guarda passa vazia.

### 11.3 Finalidade, retenção, auditoria

- **Finalidade**: pesquisa jurídica para a atividade advocatícia. Compatível.
- **Retenção**: norma pública não tem prazo de expurgo. O texto integral
  cacheado tem `texto_obtido_em` e pode ser purgado sem perda.
- **Auditoria**: o `AuditMiddleware` já registra toda escrita autenticada.
- **Origem**: `url_fonte` + `urn` preservam a proveniência de cada registro.

---

## 12. Cache

| Cache | Chave | TTL | Padrão |
|---|---|---|---|
| Resposta SRU | `lexml:busca:{sha256(params)}` | curto (5-15 min) | igual a `rag/retrieval.py:24-48` |
| Texto integral | coluna `texto_integral` + `texto_obtido_em` | dias | revalidação por idade |
| Acervo local | — | — | é a fonte, não cache |

Falha de cache **só loga**, nunca derruba a busca — padrão já estabelecido
(`rag_cache_read_failed` / `rag_cache_write_failed`). Sem Redis configurado, o
sistema degrada graciosamente (`get_redis()` devolve `None`, consumidores checam
`if redis:`).

**Invalidação**: por TTL. Não há invalidação ativa porque norma publicada não
muda — o que muda é a *vigência*, que é informação nova, não correção da antiga.

---

## 13. Sincronização

A pipeline diária de 06:00 continua. Mudanças propostas:

1. **Fase 1**: além do Qdrant, gravar metadados estruturados em `lexml_normas`.
2. **Fase 5**: trocar a dedup-como-cursor por cursor de data real. Hoje o teto é
   ~100 normas/dia (50 Leis + 50 Decretos, sem paginação) e a dedup por URN é o
   que impede reprocessar as mesmas.

**Detecção de alteração normativa**: **NÃO VERIFICADO** se o LexML expõe isso.
Sem confirmação, não há como planejar. Fase 5.

**Falhas**: o `SyncRun` já grava `"OK" if falhas == 0 else "ERRO"`, e o
`sync_reaper` (a cada 30 min) libera execuções travadas em RUNNING.

---

## 14. Pesquisa

Duas modalidades, complementares:

| Modalidade | Motor | Boa para |
|---|---|---|
| **Lexical** | PostgreSQL FTS sobre `titulo`/`ementa` + filtros de coluna | "Lei 14.133", "decreto de 2021", filtro por órgão |
| **Semântica** | Qdrant (já existe) | "o que a lei diz sobre dispensa de licitação" |

A aba nova usa a lexical (é o que os filtros do mockup pedem). A busca semântica
continua onde está, na aba atual. **Não unificar as duas agora** — são perguntas
diferentes, e fundi-las prematuramente pioraria as duas.

---

## 15. Indexação

| Opção | Veredito |
|---|---|
| **PostgreSQL FTS** | **Agora.** Índice GIN sobre `titulo || ementa`. Resolve a busca lexical com zero infraestrutura nova. |
| **Índices B-tree** | **Agora.** `(tipo_norma, ano)`, `urn` unique. |
| **Trigram (`pg_trgm`)** | **Fase 2**, se a busca por título com erro de digitação se mostrar necessária. Exige extensão. |
| **Busca semântica / embeddings** | **Já existe.** Qdrant, collection `legislacao`. Nada a fazer. |
| **pgvector** | **Evitar.** Seria um segundo motor vetorial ao lado do Qdrant — duas fontes de verdade para a mesma pergunta, dois lugares para reindexar, dois comportamentos de filtro. |
| **Motor externo (Elasticsearch/Meilisearch)** | **Evitar.** Quarto datastore para um volume que o Postgres resolve. |

---

## 16. Grafo jurídico

**Condicional, Fase 4.** Depende de a Fase 0 confirmar que o LexML expõe
relações entre normas — hoje **NÃO VERIFICADO**. Sem fonte, não há grafo.

Se confirmado, a implementação é **PostgreSQL relacional**, não banco de grafos:

```sql
lexml_relacoes (
  id, origem_urn, destino_urn,
  tipo,          -- altera | revoga | regulamenta | cita
  fonte,         -- de onde veio a afirmação
  created_at
)
```

**Justificativa técnica para não adotar banco de grafos:**
1. As consultas reais são de **1-2 saltos** ("o que altera esta lei?"), não
   travessias profundas — exatamente onde SQL recursivo (`WITH RECURSIVE`) é
   suficiente.
2. O volume é pequeno (dezenas de milhares de arestas).
3. Neo4j seria o **quarto datastore** do sistema (Postgres + Redis + Qdrant),
   com custo operacional e de deploy desproporcional ao ganho.

Revisitar só se aparecer uma consulta de travessia profunda que o SQL recursivo
não sustente — e aí com medição, não com suposição.

---

## 17. Preparação para IA

A maior parte já existe: chunking (`rag/chunker.py`, híbrido por seção jurídica
+ janela deslizante), embeddings multi-provedor com BYOK, busca vetorial com
filtro por provedor, e o `legislacao` já indexado.

O que esta integração acrescenta para o futuro:

- **Rastreabilidade por URN**: hoje a resposta da IA cita um chunk. Com o acervo
  estruturado, cada chunk tem URN → o sistema pode devolver documento, URN,
  fonte, artigo, trecho e data da consulta.
- **Separação das quatro camadas** (requisito 13 do enunciado), garantida por
  desenho: `texto_integral`/`url_fonte` (fonte), colunas estruturadas
  (metadado), `anotacao` (interpretação do escritório), `urn` (referência).

**Regra invariante**: nenhuma coluna de texto de norma pode receber saída de
LLM. Onde houver interpretação, ela vem rotulada e com o URN da norma que a
originou. O sistema já tem o precedente — a tela de busca exibe aviso fixo de
verificação de fonte (`busca-juridica/page.tsx:580-585`) e o `citacao_check`
distingue `confirmada` / `nao_encontrada` / `nao_verificavel`.

**Nível de confiança**: não propor agora. O sistema não tem calibração para
isso, e um número inventado é pior que nenhum.

---

## 18. Tratamento de erros

| Situação | Comportamento |
|---|---|
| LexML indisponível | Breaker abre; devolve o acervo local + aviso honesto de que a consulta ao vivo falhou |
| Timeout | Idem (15s, já configurado) |
| XML inválido | `None` do parser → tratado como "não verificável", nunca como "não encontrado" |
| Resposta vazia | "Nenhuma norma encontrada" — distinto de indisponibilidade |
| Documento inexistente | 404 `NotFoundError` |
| URN inválida | 422 `ValidationError` |
| Duplicidade | UPSERT por URN; nunca erro ao usuário |
| Erro de banco | 500 genérico pelo handler global; detalhe só no log |
| Limite de requisições | **NÃO VERIFICADO** — se aparecer 429, o breaker abre e a mensagem usa `friendly_detail()`, que já tem padrão para cota |
| Falha de autenticação | N/A — API aberta |
| Erro de parsing | Log com o trecho problemático; registro pulado, nunca a busca inteira |

**Princípio**: mensagem amigável na tela, técnica no log. `friendly_detail()`
(`services/integration_hub.py:81-103`) já faz essa tradução, com
`fallback=False` para não embrulhar mensagens que o próprio sistema escreveu em
português claro.

---

## 19. Observabilidade

- **Logs**: eventos `lexml_busca_*`, `lexml_norma_ingerida`,
  `lexml_texto_obtido`, `lexml_sru_falhou` — padrão structlog do projeto.
- **Métricas via `SyncRun`**: `processados` / `pulados` / `falhas` já gravados;
  desde a fase pós-265, `brain_infra` os expõe no painel Cérebro.
- **Correção pendente**: registrar o breaker `"lexml"` de modo que o painel
  Cérebro o enxergue (hoje é invisível — ver 4.1).
- **Auditoria de importação**: `JurisprudenciaIngerida` já registra origem,
  status e erro por documento.

---

## 20. Plano de implementação por fases

### Fase 0 — Sonda e correções do que já existe
**Sem feature nova.** Pré-requisito de tudo.

| Item | Detalhe |
|---|---|
| Objetivo | Substituir suposição por dado; corrigir 3 achados |
| Ações | (a) Sonda SRU real (`operation=explain` + uma busca), resposta crua salva; (b) índice `document_id` na collection `legislacao`; (c) `defusedxml` + teto de tamanho; (d) User-Agent identificando o AFJ; (e) allowlist de domínio em `baixar_texto_norma` |
| Arquivos | `rag/collections.py`, `integrations/lexml/client.py`, `requirements.txt` |
| Riscos | A sonda exige ambiente com egress — **este sandbox não alcança o LexML** |
| Aceitação | Resposta crua existe; campos do parser confirmados contra ela; SSRF fechado |

### Fase 1 — Acervo estruturado

| Item | Detalhe |
|---|---|
| Objetivo | Normas consultáveis por metadado |
| Ações | Models + `__init__.py` + DDL idempotente; normalização/validação de URN; backfill do que já está em `jurisprudencia_ingerida` (fonte `lexml_legislacao`) |
| Arquivos | `models/lexml.py`, `models/__init__.py`, `core/events.py` |
| Riscos | Backfill sobre dados cujo `metadata_extraida` só tem `{titulo, tipo_norma, url}` — campos como `ano` e `autoridade` virão nulos até a próxima sincronização |
| Aceitação | Toda norma já ingerida aparece no acervo com URN válido; reingestão não duplica |

### Fase 2 — Pesquisa ao vivo

| Item | Detalhe |
|---|---|
| Objetivo | Consultar o LexML sob demanda |
| Ações | Cliente estendido (CQL com filtros, paginação, mais tipos); `services/lexml_acervo.py`; endpoints; cache |
| Arquivos | `integrations/lexml/client.py`, `services/lexml_acervo.py`, `api/v1/lexml.py`, `api/v1/router.py` |
| Riscos | Índices CQL não confirmados (`ano`, `autoridade`) — a Fase 0 decide quais existem |
| Aceitação | Busca por "Lei 14.133/2021" devolve URN correto; LexML fora do ar degrada distinguindo indisponibilidade de ausência |

### Fase 3 — Tela e vínculos

| Item | Detalhe |
|---|---|
| Objetivo | O advogado usa |
| Ações | Aba Legislação, filtros, paginação, texto sob demanda, favoritar, vincular; entrada no checklist LGPD |
| Arquivos | `frontend/.../busca-juridica/page.tsx`, `frontend/src/components/legislacao/*`, `api/v1/lgpd.py` |
| Riscos | LGPD — a tabela precisa entrar no erasure **e** no cenário do teste de sentinela |
| Aceitação | Playwright real: busca → abrir → adicionar ao acervo → vincular → reload persiste |

### Fase 4 — Grafo e citação *(condicional)*

Só se a Fase 0 confirmar que o LexML expõe relações. Tabela `lexml_relacoes` em
PostgreSQL + formatador de citação jurídica (hoje o projeto só tem verificador,
não gerador).

### Fase 5 — Ampliação

Mais tipos de norma e esferas; cursor por data em vez de dedup-como-cursor;
reindexação; detecção de alteração normativa (se houver fonte).

---

## 21. Riscos

| # | Risco | Severidade | Mitigação |
|---|---|---|---|
| 1 | Tags do XML SRU não confirmadas | **Alta** | Fase 0 é uma sonda real antes de qualquer código |
| 2 | Índices CQL (`ano`, `autoridade`) podem não existir | **Alta** | Fase 0; se não existirem, filtrar no acervo local |
| 3 | Texto integral vem de scraping do Planalto | **Média** | Já é o comportamento atual; falha degrada para link |
| 4 | SSRF em `baixar_texto_norma` | **Média** | Allowlist de domínio na Fase 0 |
| 5 | Termos de uso do acervo não verificados | **Média** | Política "metadados + link" já reduz exposição; registrar para parecer jurídico, como o DataJud |
| 6 | Reingestão duplicando chunks (`document_id` sem índice) | **Média** | Corrigido na Fase 0 |
| 7 | Tabela nova esquecida pelo erasure LGPD | **Média** | Checklist do `CLAUDE.md` + teste de sentinela |
| 8 | Expansão de entidade XML (DoS) | **Baixa** | `defusedxml` na Fase 0 |
| 9 | Volume: ~100 normas/dia | **Baixa** | Fase 5 |

---

## 22. Critérios de aceitação

**Globais**: `ruff check app/` limpo; `tsc --noEmit` e `eslint` limpos; suíte
completa na configuração do runner (banco do zero, `REDIS_URL=` vazio), **duas
execuções contra o mesmo banco**, sem regressão frente à baseline
(`test_unit` 1005 passed/4 skipped; `test_api` ~190/9).

**Prova nos dois sentidos**: cada correção precisa de um teste que **falhe com o
fix revertido**. É regra fixa deste projeto, e já pegou desenho de teste furado
mais de uma vez.

Por fase, os critérios estão na seção 20.

---

## 23. Arquivos a criar / alterar

**Novos**
- `backend/app/models/lexml.py`
- `backend/app/services/lexml_acervo.py`
- `backend/app/api/v1/lexml.py`
- `frontend/src/components/legislacao/*`
- `backend/tests/test_unit/test_lexml_acervo.py`, `test_lexml_urn.py`
- `backend/tests/test_api/test_lexml_endpoints.py`

**Alterados**
- `backend/app/integrations/lexml/client.py` — CQL com filtros, paginação,
  `defusedxml`, User-Agent, allowlist SSRF
- `backend/app/rag/collections.py` — índice `document_id` em `legislacao`
- `backend/app/core/events.py` — DDL idempotente
- `backend/app/models/__init__.py` — registro dos models
- `backend/app/api/v1/router.py` — montagem do router
- `backend/app/api/v1/lgpd.py` — erasure de `lexml_norma_tenant`
- `backend/app/workers/tasks/legislacao_sync.py` — grava metadados estruturados
- `frontend/src/app/(dashboard)/busca-juridica/page.tsx` — aba nova
- `backend/requirements.txt` — `defusedxml`
- `CLAUDE.md`, `HISTORICO_FASES.md`

---

## 24. Variáveis de ambiente

**Nenhuma obrigatória.** O LexML é API aberta, sem autenticação — não há
credencial a configurar. Isso é uma diferença relevante em relação a toda outra
integração deste sistema.

Opcionais, se a Fase 0 revelar necessidade:

| Variável | Default | Para quê |
|---|---|---|
| `LEXML_SRU_URL` | `https://www.lexml.gov.br/busca/SRU` | Hoje hardcoded em `client.py:24`; externalizar só se houver ambiente alternativo |
| `LEXML_TIMEOUT_SECONDS` | `15.0` | Hoje hardcoded |
| `LEXML_MAX_RECORDS` | `50` | Teto por chamada |

---

## 25. O que NÃO foi verificado

`www.lexml.gov.br` e `projeto.lexml.gov.br` estão **bloqueados pelo proxy de
egress** deste ambiente (confirmado por `curl` — HTTP 000 — e por `WebFetch` —
`EGRESS_BLOCKED`).

| Item | Status |
|---|---|
| Nomes exatos das tags do XML de resposta | **NÃO VERIFICADO** — o próprio código admite (`client.py:6-11, 85-93`) |
| Índices CQL aceitos além de `localidade` e `tipoDocumento` | **NÃO VERIFICADO** |
| Limites de requisição / rate limit | **NÃO VERIFICADO** — nada encontrado |
| Termos de uso do acervo | **NÃO VERIFICADO** — relevante, dada a pendência análoga do DataJud |
| Relacionamentos entre normas (altera/revoga/regulamenta) | **NÃO VERIFICADO** — sem isso a Fase 4 não tem fonte |
| OAI-PMH para consumo | **NÃO VERIFICADO** — as fontes indicam OAI-PMH para **provedores publicarem ao LexML**, direção oposta à que o enunciado assume |
| Disponibilidade de ementa, `data_assinatura`, vigência | **NÃO VERIFICADO** |

**Confirmado por fonte secundária** (não oficial): é SRU com resposta XML
`<srw:recordData>` contendo `<urn>`, `<title>`, `<tipoDocumento>`, `<date>`;
parâmetros `startRecord` e `maximumRecordsPerPage`; URN na forma
`urn:lex:<localidade>:<autoridade>:<tipo>:<descritor>`.

Fontes: [py-lexml-acervo](https://github.com/netoferraz/py-lexml-acervo) ·
[Manual de Pesquisa do Portal LexML](https://projeto.lexml.gov.br/documentacao/ManualPesquisaWeb.pdf) ·
[LexML Brasil Parte 2 — URN](https://projeto.lexml.gov.br/documentacao/Parte-2-LexML-URN.pdf) ·
[LexML Brasil Parte 4 — Coleta de Metadados](https://projeto.lexml.gov.br/documentacao/Parte-4-Coleta-de-Metadados.pdf)

**A fonte de verdade mais confiável disponível é o cliente que já roda em
produção** — o que ele faz, funciona.

---

## 26. Checklist final

**Antes de começar**
- [ ] Fase 0 executada em ambiente com egress; resposta crua do SRU salva
- [ ] Campos do parser confirmados contra a resposta real
- [ ] Decisão registrada sobre os termos de uso do acervo

**Durante**
- [ ] Models registrados em `app/models/__init__.py`
- [ ] DDL idempotente, **nenhuma migration Alembic**
- [ ] Router com `_BLOCK_STAFF`; gate por `require_role` na assinatura
- [ ] Chamada externa dentro de `CircuitBreaker.run(...)`, com timeout
- [ ] Allowlist de domínio antes de qualquer GET em URL vinda de fora
- [ ] `lexml_norma_tenant` em `erase_client_data` **e** `export_client_data`
- [ ] Teste de sentinela LGPD preenchendo a tabela nova
- [ ] Prova nos dois sentidos em cada correção

**Antes de entregar**
- [ ] `ruff` / `tsc --noEmit` / `eslint` limpos
- [ ] Suíte completa 2× contra o mesmo banco, sem regressão
- [ ] Playwright real na aba nova
- [ ] `CLAUDE.md` e `HISTORICO_FASES.md` atualizados
- [ ] O que não pôde ser provado neste ambiente, declarado na entrega
