# API Pública do CNJ DataJud vs. uso comercial — levantamento técnico

**Para**: parecer jurídico
**De**: levantamento técnico do sistema AFJ CORE
**Data do levantamento**: 06/09/2026
**Status**: pendência aberta desde a Fase 217, nunca resolvida

> **Este documento não conclui nada sobre conformidade.** Ele não afirma que o
> uso atual viola ou respeita o Termo de Uso do CNJ, e não recomenda manter,
> alterar ou desligar a integração. Ele descreve, com precisão e com a
> referência de onde cada fato foi verificado, **o que exatamente o sistema faz
> com o DataJud** — para que o parecer possa ser dado sobre fatos, e não sobre
> uma descrição aproximada.

---

## 0. A dúvida, em uma frase

O AFJ CORE é um produto comercial e consome a API Pública do CNJ DataJud para
enriquecer processos com andamentos. Trechos localizados do Termo de Uso oficial
vedam "modificar, distribuir, vender, ou explorar comercialmente a API ou
qualquer informação derivada dela". A pergunta é se o uso atual cabe nessa
vedação — e, se couber, o que precisa mudar.

**Aviso sobre a fonte da citação**: o PDF completo do Termo de Uso **nunca foi
lido**. A citação acima vem de trechos localizados em pesquisa, não de leitura
integral do documento oficial. O ambiente onde este levantamento foi feito
bloqueia acesso à internet externa (limitação conhecida e registrada desde a
Fase 217). **A leitura integral do Termo é o primeiro passo do parecer**, e este
documento não substitui essa leitura — ele descreve o outro lado da equação: o
que o sistema faz.

Ponto de partida documental: <https://datajud-wiki.cnj.jus.br/api-publica/acesso>

---

## 1. O que o sistema pede ao DataJud, e com que credencial

**Endereço**: `https://api-publica.datajud.cnj.jus.br`
(`backend/app/integrations/tribunais/cnj.py:14`), com uma requisição de busca
por tribunal (`POST /{índice-do-tribunal}/_search`, `cnj.py:111-113`). Os
índices de cada tribunal — TJs, TRFs, TRTs e tribunais superiores — estão
mapeados no próprio código (`cnj.py:16-83`).

**Credencial** — este é o primeiro achado que muda a pergunta jurídica. A chave
de acesso é enviada no cabeçalho `Authorization: APIKey ...`
(`cnj.py:147`, `cnj.py:219`) e vem de `settings.CNJ_API_KEY`. O valor padrão
está **escrito diretamente no código-fonte** (`backend/app/config.py:57-61`),
com este comentário:

> Chave PÚBLICA do CNJ DataJud (compartilhada abertamente na doc:
> `https://datajud-wiki.cnj.jus.br/api-publica/acesso`). O CNJ pode rotacioná-la
> a qualquer momento — se o enriquecimento parar, basta setar a env `CNJ_API_KEY`.

Ou seja: **não existe credencial por escritório**. Toda instalação do AFJ chama
o DataJud com a mesma chave que o próprio CNJ publica abertamente. Isso é
relevante porque muda a pergunta de "o escritório aceitou algum termo ao se
credenciar?" para "**existe algum ato de aceite de termo, por parte de quem
quer que seja, em algum momento?**" — e, pelo que foi verificado no código, não
há nenhum registro de aceite em lugar nenhum do sistema.

**O que é solicitado** (campos pedidos na consulta):

- Consulta de andamentos (`cnj.py:125-188`): `movimentos`, `dataAjuizamento`,
  `tribunal`.
- Consulta de processo (`cnj.py:199-244`): `numeroProcesso`, `classe`,
  `assuntos`, `orgaoJulgador`, `dataAjuizamento`, `grau`, `tribunal`,
  `movimentos`.

**O que a API não oferece e o sistema não usa**: busca por advogado/OAB — a API
Pública não indexa partes nem advogados, e o código registra isso explicitamente
(`cnj.py:190-197`).

---

## 2. Com que frequência é chamado

| Caminho | Gatilho | Frequência |
|---|---|---|
| Atualização de andamentos de um processo (`POST /processes/{id}/atualizar-andamentos`, `backend/app/api/v1/processes.py:762`) | Botão, ação humana | Sob demanda |
| Verificação de citações em peças geradas por IA (`backend/app/services/citacao_check.py:96`) | Ação humana (gerar/revisar documento ou petição) | Sob demanda |
| Polling automático de processos (`backend/app/agents/process/process_agent.py:79-88`) | Rotina automática | **A cada 30 minutos**, para todos os escritórios ativos (`backend/app/workers/worker.py:73-78`, intervalo em `config.py:137`) |
| Enriquecimento de processos descobertos por OAB (`backend/app/services/oab_capture.py:98`) | Manual **e** automático | Manual sob demanda; automático **diário às 8h** (`worker.py:146-151`) |

---

## 3. O que é derivado do DataJud e onde fica armazenado

O ponto de entrada dos dados é `backend/app/services/movements_import.py`.

**`process_movements`** (`backend/app/models/process.py:84-101`) — uma linha por
andamento:

- `descricao` — o texto do andamento, truncado em 2.000 caracteres
  (`movements_import.py:61`);
- `data_movimento`, `tipo`, `documento_url`;
- **`raw_html`** — na rotina automática de polling, recebe o **JSON bruto do
  andamento vindo do DataJud**, serializado como texto
  (`backend/app/agents/process/process_agent.py:174-184`). Na rotina de
  importação canônica esse campo fica vazio;
- `ai_summary` — resumo do andamento gerado por IA (ver seção 4);
- `possivel_prazo` — resultado de uma heurística sobre o texto.

**Retenção**: **indefinida**. Não há expurgo automático. O único caminho que
altera esses campos depois é a rotina de exclusão de dados por pedido do titular
(LGPD, `backend/app/api/v1/lgpd.py:372-396`), que zera `descricao`, `raw_html` e
`ai_summary` — e isso acontece por pedido, não por prazo.

**`legal_processes`** (`backend/app/models/process.py:11-63`) — campos
preenchidos a partir do DataJud (`backend/app/services/oab_capture.py:99-120`):
`tipo_acao` (classe processual), `vara` (órgão julgador), `area_direito`
(inferida dos assuntos), `distribuicao_data`, mais um resumo bruto guardado em
`metadata_json["datajud"]` = `{classe, grau, assuntos[:5]}`.

**`sync_runs`** — registro de cada execução de captura, com a fonte identificada
como `"datajud"` / `"comunica+datajud"` / `"multi"`. Guarda contadores, não
conteúdo.

**Não é armazenado**: nada do DataJud é indexado no mecanismo de busca semântica
(Qdrant/RAG) — verificado.

---

## 4. Até onde o dado derivado chega — a cadeia completa

Esta é a seção mais relevante para a expressão "**informação derivada**" do
Termo. A cadeia tem três degraus.

### Degrau 1 — exibição interna ao escritório

- `GET /api/v1/processes/{id}/movements`
  (`backend/app/api/v1/processes.py:447-480`);
- tela do processo: `frontend/src/components/processes/ProcessTimeline.tsx`,
  linha do tempo com o texto do andamento e etiquetas.

### Degrau 2 — transformação por IA e uso operacional

- **Resumo por IA**: o texto do andamento é enviado a um modelo de linguagem que
  produz um resumo (`process_agent.py:104-122`), gravado em `ai_summary`.
- **Detecção de prazo**: gera registros de prazo processual
  (`process_deadlines`) e a marcação "possível prazo"
  (`process_agent.py:125`, `movements_import.py:107`).
- **Notificação à equipe**: cria notificação interna do tipo `NOVO_ANDAMENTO`
  (`backend/app/services/andamento_notify.py:12-50`), apenas dentro do sistema
  (não há envio por e-mail nem WhatsApp — verificado).
- **Verificação de citações em petições**: ao gerar ou revisar uma peça por IA, o
  sistema consulta o DataJud para marcar cada processo citado como "confirmada"
  ou "não verificável" (`backend/app/api/v1/documents.py:1012`,
  `backend/app/agents/petition/petition_agent.py:131`) — e esse resultado é
  incorporado ao texto da peça, que pode ser exportada e protocolada.

### Degrau 3 — saída para fora do escritório

**Este é o ponto que mais importa para o parecer.** O Portal do Cliente entrega
dados originados do DataJud diretamente ao **cliente final do escritório**:

- `GET /api/v1/portal/processes/{id}` (`backend/app/api/v1/portal.py:146-217`)
  devolve até 30 andamentos, cada um com `descricao` e `ai_summary`
  (`portal.py:197-205`), além de `tribunal`, `vara`, `comarca`, `tipo_acao` e
  `distribuicao_data`;
- exibidos em `frontend/src/components/portal/ProcessosSection.tsx:249-287`;
- o acesso exige vínculo com o cliente e link de portal válido
  (`portal.py:21-38`) — não é público, mas **é fora do escritório**.

### O que foi verificado e **não** acontece

Registrado para que o parecer não precise assumir o pior caso:

- **Não** há exportação de andamentos em CSV, PDF ou XLSX;
- **Não** há envio de andamentos por e-mail nem por WhatsApp;
- **Não** há webhook de saída com esses dados;
- **Não** existe API pública própria do AFJ que os exponha — todos os endpoints
  exigem autenticação e são isolados por escritório;
- **Não** há revenda direta do dado nem do acesso à API: o produto comercial é o
  sistema de gestão; o dado do DataJud entra como um dos insumos.

---

## 5. Atribuição de fonte hoje

O sistema **nomeia** a fonte em três telas internas, como rótulo funcional —
sem aviso legal, sem menção a Termo de Uso, sem atribuição formal:

- `frontend/src/app/(dashboard)/admin/health/page.tsx:134` — cartão de saúde:
  "CNJ DataJud — API pública, enriquecimento de metadados e andamentos";
- `frontend/src/app/(dashboard)/admin/health/page.tsx:247` — lista de recursos;
- `frontend/src/app/(dashboard)/processos/page.tsx:703` — modal de captura por
  OAB: "Importa automaticamente todos os processos vinculados ao número da OAB
  via CNJ DataJud".

**No Portal do Cliente não há atribuição nenhuma** — os andamentos aparecem sem
qualquer menção à origem dos dados. Como o Portal é exatamente o ponto onde a
informação derivada sai do escritório (seção 4, degrau 3), essa assimetria pode
ser relevante para o parecer.

Não existe, em nenhum lugar do repositório, o texto do Termo de Uso, nem
qualquer aviso ao usuário final sobre a origem ou o licenciamento dos dados.

---

## 6. Se o parecer disser "não pode" — o custo real

### Não existe um botão para desligar

- O registro de fontes instancia o DataJud de forma incondicional
  (`backend/app/integrations/fontes/registry.py:14-20`) — **não há configuração,
  variável de ambiente nem opção por escritório** que o desative.
- O endpoint de atualização de andamentos nem passa pelo registro: ele instancia
  o cliente diretamente (`backend/app/api/v1/processes.py:762`).

### Existe um desligamento parcial, grosseiro

Invalidar a chave `CNJ_API_KEY` faz a autenticação falhar
(`cnj.py:115-123`) e todas as chamadas passam a retornar vazio de forma
silenciosa (o sistema é tolerante a falha e não quebra). **Mas é global**: vale
para todos os escritórios de uma vez, sem granularidade, e as chamadas continuam
sendo feitas — apenas falham.

### O que pararia de funcionar, e sem substituto ativo

| Funcionalidade | Efeito |
|---|---|
| Botão "Atualizar andamentos" | Sempre responde "a fonte não respondeu" (`processes.py:770-774`) |
| Polling automático a cada 30 min | Todo processo passa a `fonte_indisponivel` (`process_agent.py:89-100`) |
| Enriquecimento de processos capturados por OAB | Processos novos entram sem classe, vara, área e data de distribuição |
| Verificação de citações em peças | Toda citação vira "não verificável" (`citacao_check.py:109`) |

**Nenhum desses caminhos tem substituição automática configurada hoje.**

### Mas a alternativa existe — está implementada e desligada

Este é o segundo achado relevante. O sistema integra outras fontes processuais:

| Fonte | Natureza | Credencial por escritório | Ativa hoje |
|---|---|---|---|
| Comunica/DJEN | Pública, sem autenticação | Não | Sim |
| **CNJ DataJud** | Pública (chave pública embutida) | Não | **Sim** |
| PDPJ (Portal de Serviços do PJe) | Governamental, credenciada | Sim, obrigatória | Só se o escritório conectar |
| Escavador | Comercial | Sim | Só se conectar |
| Judit | Comercial | Sim | Só se conectar |
| Jusbrasil | Comercial | Sim | Só se conectar |

As quatro fontes credenciadas (PDPJ, Escavador, Judit, Jusbrasil) **já
implementam a obtenção de andamentos** (método `movimentos()` em cada
`backend/app/integrations/fontes/*_fonte.py`), mas **nenhum caminho de produção
as chama para isso** — hoje elas só são acionadas para obter as **partes** do
processo (`oab_capture.py:128-164`). A ordem de preferência entre elas já está
definida (`backend/app/integrations/fontes/credenciadas.py:12-26`).

**Em resumo**: se o parecer concluir que o DataJud não pode ser usado, a
substituição é um trabalho de ligação de peças já existentes — não de construir
uma integração nova do zero. O custo passa a ser o custo comercial de contratar
uma dessas fontes, que é uma decisão do escritório, não uma limitação técnica.

*(Existem ainda dois clientes de tribunal no código — ESAJ e PJe direto — que
não são chamados por nenhum caminho do sistema; são código inativo e não contam
como alternativa disponível.)*

---

## 7. As perguntas para o parecer

1. **Leitura integral do Termo**: o texto oficial, lido por inteiro, veda o uso
   descrito nas seções 1 a 4? A citação que motivou esta pendência veio de
   trechos, não de leitura completa.

2. **Existe aceite?** Se a chave de acesso é pública e vem embutida no código
   (seção 1), houve algum ato de aceite do Termo por parte do escritório? Se o
   CNJ publica a chave abertamente, o simples uso configura adesão ao Termo?

3. **O que conta como "informação derivada"?** O andamento copiado literalmente,
   o resumo gerado por IA a partir dele, o prazo processual calculado a partir
   dele — todos os três recebem o mesmo tratamento?

4. **O Portal do Cliente configura "distribuição"?** Entregar o andamento (e seu
   resumo por IA) ao cliente final do escritório, dentro de um produto pago,
   é distribuição de informação derivada, ou é o exercício normal da relação
   advogado-cliente sobre informação que já é processual e pública?

5. **"Explorar comercialmente" alcança este uso?** O escritório não vende o
   dado nem o acesso à API; vende um sistema de gestão que, entre muitas outras
   funções, consulta uma fonte pública. Isso está dentro ou fora da vedação?

6. **Atribuição é exigida?** Se sim, em quais superfícies — só internas, ou
   também no Portal do Cliente, hoje sem qualquer menção à origem (seção 5)?

7. **Se não puder**: a saída é trocar de fonte (seção 6, com custo comercial de
   contratação), buscar credenciamento específico junto ao CNJ, ou existe uma
   modalidade de uso do DataJud compatível com produto comercial?

---

## 8. O que este levantamento **não** conseguiu verificar

- **O Termo de Uso em si** — nunca lido integralmente. O ambiente onde este
  levantamento foi feito bloqueia acesso a domínios externos (limitação
  documentada desde a Fase 217). Toda a caracterização da vedação neste
  documento é reprodução de trechos previamente localizados, não leitura direta.
- **Se existe algum aceite de termo fora do código** — contratos, cadastros ou
  comunicações do escritório com o CNJ estão fora do alcance deste levantamento.
- **Comportamento em produção** — as chamadas ao DataJud não puderam ser
  exercidas neste ambiente (mesmo bloqueio de rede). Toda a descrição vem de
  leitura do código, não de observação de tráfego real.

---

## 9. Referências de código citadas

| Assunto | Arquivo |
|---|---|
| Cliente HTTP e endereço da API | `backend/app/integrations/tribunais/cnj.py:14`, `:111-113`, `:125-244` |
| Chave pública embutida | `backend/app/config.py:57-61` |
| Registro de fontes (sem opção de desligar) | `backend/app/integrations/fontes/registry.py:14-20` |
| Endpoint que instancia o cliente diretamente | `backend/app/api/v1/processes.py:762`, `:770-774` |
| Polling automático (30 min) | `backend/app/agents/process/process_agent.py:79-100`, `backend/app/workers/worker.py:73-78` |
| Descoberta por OAB (diária, 8h) | `backend/app/services/oab_capture.py:98-120`, `backend/app/workers/worker.py:146-151` |
| Importação e persistência de andamentos | `backend/app/services/movements_import.py:48-129` |
| JSON bruto gravado em `raw_html` | `backend/app/agents/process/process_agent.py:174-184` |
| Resumo por IA e detecção de prazo | `backend/app/agents/process/process_agent.py:104-125` |
| Notificação interna | `backend/app/services/andamento_notify.py:12-50` |
| Verificação de citações em peças | `backend/app/services/citacao_check.py:80-116`, `backend/app/api/v1/documents.py:1012` |
| Saída pelo Portal do Cliente | `backend/app/api/v1/portal.py:146-217`, `frontend/src/components/portal/ProcessosSection.tsx:249-287` |
| Anonimização por pedido do titular (LGPD) | `backend/app/api/v1/lgpd.py:372-396` |
| Fontes alternativas já integradas | `backend/app/integrations/fontes/*_fonte.py`, `backend/app/integrations/fontes/credenciadas.py:12-26` |
| Atribuição de fonte nas telas internas | `frontend/src/app/(dashboard)/admin/health/page.tsx:134`, `:247`, `frontend/src/app/(dashboard)/processos/page.tsx:703` |
