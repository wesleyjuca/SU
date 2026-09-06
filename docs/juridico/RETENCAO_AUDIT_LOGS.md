# Retenção do log de auditoria (`audit_logs`) — levantamento técnico

**Para**: decisão do escritório / parecer jurídico
**De**: levantamento técnico do sistema AFJ CORE
**Data do levantamento**: 06/09/2026
**Status**: pendência aberta desde a Fase 148, nunca resolvida

> **Este documento não decide nada.** Ele não propõe prazo de retenção, não
> afirma que o sistema está ou não em conformidade e não recomenda uma opção
> sobre as outras. Ele reúne os fatos técnicos que a decisão exige, cada um com
> a referência de onde foi verificado, e termina com as perguntas que só o
> escritório pode responder.

---

## 1. O que é essa tabela, em uma frase

`audit_logs` é o registro de quem fez o quê no sistema: cada vez que alguém
cria, altera ou apaga qualquer coisa, uma linha é gravada com o usuário, a
ação, a data, o endereço de rede e o navegador usado. Serve para responder
"quem mexeu nisso?" — inclusive para provar que um pedido de exclusão de dados
(LGPD) foi de fato executado.

O impasse é que essa mesma tabela guarda dado pessoal (endereço de rede,
identificação de navegador, identificação do usuário) **sem prazo de validade**,
enquanto a LGPD pede que dado pessoal não seja mantido por tempo indefinido.

---

## 2. O que exatamente fica gravado

A tabela tem 19 colunas (`backend/app/models/audit_log.py:17-38`). Para efeito
da decisão, o que importa é separar o que é gravado **sempre**, **às vezes** e
**nunca**.

### Sempre (em toda linha escrita automaticamente)

O sistema grava uma linha a cada operação de escrita autenticada, por um
componente automático (`backend/app/core/middleware.py:88-115`). Nessa linha vão:

| Campo | Conteúdo | É dado pessoal? |
|---|---|---|
| `ip_address` | Endereço de rede de quem fez a operação | **Sim** |
| `user_agent` | Texto que identifica navegador/dispositivo | **Sim** (pode ajudar a singularizar alguém) |
| `user_id` | Identificador interno do usuário logado | **Sim**, indiretamente |
| `tenant_id` | Identificador do escritório | Não (é pessoa jurídica) |
| `action` | Método e caminho da operação, ex. `POST:/api/v1/clients` | Não |
| `timestamp` | Data e hora | Não isoladamente |
| `success` / `error_detail` | Se deu certo; se não, o código do erro | Não |

### Às vezes (só em 3 pontos específicos do sistema)

As colunas `old_value` e `new_value` (que guardam "valor antes / valor depois")
**não são preenchidas pelo componente automático** — ele nem as envia
(`middleware.py:102-111`). Elas só são preenchidas por 3 rotas específicas, e
sempre com dicionários curtos, montados pela própria rota:

- decisão de aprovação humana — `backend/app/api/v1/approvals.py:209-210`
  (grava só `{"status": ...}` e o motivo da rejeição);
- exportação de documento para o Google Docs —
  `backend/app/api/v1/google_integration.py:200` (só identificadores do arquivo);
- exportação financeira para o Google Sheets —
  `backend/app/api/v1/financial.py:358-364` (contadores e filtros usados).

**Medição no banco local**: de 3.948 linhas, apenas **40** têm `old_value` e
**46** têm `new_value` — cerca de 1%.

### Nunca

Verificado por leitura do código: **não é gravado** o corpo da requisição
(o conteúdo enviado pelo usuário), **não é gravada** a query string, e **nenhum
outro cabeçalho** além do `User-Agent` — nem token de autenticação, nem cookie.

> **Correção relevante ao registro anterior.** A anotação interna que abriu esta
> pendência descreve o conteúdo como podendo conter "IP, user_agent,
> `old_value`/`new_value`". Isso é verdade, mas dá a impressão de uma superfície
> maior do que a real: os dois últimos aparecem em ~1% das linhas e com conteúdo
> curto e controlado. O que está em toda linha é endereço de rede + navegador +
> usuário. A decisão deve ser tomada sobre esse conjunto, que é mais estreito.

---

## 3. Volume e crescimento

**A regra**: 1 linha por operação de escrita (`POST`, `PUT`, `PATCH`, `DELETE`)
autenticada. A lista de exceções (`middleware.py:14`) tem só 5 caminhos —
essencialmente login e verificações técnicas. Ou seja: cadastrar um cliente,
editar um processo, lançar um valor, cada um gera sua linha. Isso cresce muito
mais rápido do que o número de processos ou clientes do escritório.

**Medição feita no banco local desta sessão** (ambiente de desenvolvimento, não
produção):

| Métrica | Valor medido |
|---|---|
| Total de linhas | 3.948 |
| Período coberto | 22/08/2026 a 06/09/2026 (12 dias com movimento) |
| Média por dia | ~329 linhas/dia |
| Espaço em disco (com índices) | 1.384 kB → **~0,35 kB por linha** |
| Linhas escritas pelo componente automático | 3.496 (88,6%) |
| Linhas escritas pelas rotas específicas | 452 (11,4%) |

Distribuição por tipo de ação:

| Tipo | Linhas |
|---|---|
| Automático — `POST` | 2.761 |
| Automático — `DELETE` | 418 |
| Registro de operação LGPD (`LGPD:*`) | 359 |
| Automático — `PUT` | 208 |
| Automático — `PATCH` | 109 |
| Acesso ao painel interno (`BRAIN_*`) | 47 |
| Decisão de aprovação humana (`HITL:*`) | 40 |
| Outros | 6 |

**O que isso permite estimar**: a ~0,35 kB por linha, 1.000 operações de escrita
por dia gerariam cerca de **128 MB por ano**. É pouco em disco — o problema
apontado pela LGPD não é o espaço ocupado, é o **tempo de guarda do dado
pessoal**.

**Para medir em produção** (consulta somente-leitura, pode ser rodada pelo
responsável técnico no banco do Railway):

```sql
SELECT count(*)                                          AS total_linhas,
       min(timestamp)::date                              AS primeira,
       max(timestamp)::date                              AS ultima,
       round(count(*)::numeric
             / GREATEST(count(DISTINCT timestamp::date), 1), 1) AS media_por_dia,
       pg_size_pretty(pg_total_relation_size('audit_logs'))     AS tamanho
FROM audit_logs;
```

---

## 4. A trava técnica — e um achado que muda a premissa

### O que se acreditava

A premissa registrada até hoje, e repetida em vários lugares do projeto, é que
`audit_logs` **é imutável por uma trava do banco de dados**: ninguém consegue
alterar nem apagar uma linha, nem o próprio sistema. É por causa dessa premissa
que a tabela vinha sendo tratada como intocável, e é dela que nasce o impasse
("não dá para expurgar, é imutável").

### O que foi verificado

A trava (`trg_audit_logs_immutable`) é definida em **um único lugar do código**:
o arquivo de migração `backend/alembic/versions/001_initial_schema.py:415-428`.
Ela só passa a existir num banco se essa migração tiver sido executada nele.

O sistema executa as migrações no início (`backend/start.sh:52-54`), mas em modo
**tolerante a falha**: se o comando falhar, o boot segue em frente e o próprio
programa cria as tabelas por outro caminho (`create_all`,
`backend/app/core/events.py:228`) — e esse outro caminho **não cria travas**.

Ao testar o comando de migração nesta sessão, ele **falhou** — e falhou por um
defeito de configuração que não depende do ambiente nem do banco: o arquivo
`backend/alembic.ini:6` declara a conexão como `%(DATABASE_URL)s`, uma
substituição que a biblioteca de configuração não sabe resolver, e o erro
acontece antes mesmo de qualquer tentativa de conexão. O comando foi executado
com a variável de ambiente corretamente definida e falhou do mesmo jeito.

### A verificação direta, no banco

| Verificação | Resultado |
|---|---|
| Existe a trava de imutabilidade em `audit_logs`? | **Não. Nenhuma trava.** |
| Existe o registro de migrações aplicadas (`alembic_version`)? | **Não existe** — as migrações nunca rodaram neste banco |
| Um `UPDATE` numa linha de auditoria é bloqueado? | **Não. Foi executado com sucesso.** |
| Um `DELETE` numa linha de auditoria é bloqueado? | **Não. Foi executado com sucesso.** |

O teste de alteração e exclusão foi feito dentro de uma transação desfeita ao
final (`ROLLBACK`) — as 3.948 linhas permaneceram intactas, conferidas antes e
depois.

### O que isso significa para a decisão

**O log de auditoria não é, hoje, tecnicamente imutável no banco verificado.**
Ele pode ser alterado ou apagado por quem tiver acesso ao banco de dados.

Isso tem duas consequências opostas, e as duas importam:

1. **Para a LGPD**: o obstáculo técnico que impedia o expurgo pode não existir.
   A pergunta deixa de ser "como contornar a trava" e passa a ser "qual o prazo".
2. **Para o valor probatório**: se o registro pode ser alterado, ele é mais
   fraco como prova de que uma operação ocorreu — inclusive como prova de que um
   pedido de exclusão de dados foi atendido. E a tela `/sobre` do sistema
   descreve hoje o log como "imutável"
   (`frontend/src/app/(dashboard)/sobre/page.tsx:62`), o mesmo fazendo a nota
   interna que justifica tratá-lo como intocável.

**Limite desta verificação**: ela foi feita no banco de desenvolvimento desta
sessão. O banco de **produção** (Railway) não é acessível daqui. Como a falha
do comando de migração é de configuração — não de ambiente — o resultado
provavelmente se repete lá, mas isso **precisa ser confirmado** antes de
qualquer conclusão. Consulta somente-leitura para rodar em produção:

```sql
-- Deve retornar 1 linha se a trava existir; 0 linhas se não existir.
SELECT tgname FROM pg_trigger
WHERE tgrelid = 'audit_logs'::regclass AND NOT tgisinternal;

-- Deve retornar 1 linha se as migrações já rodaram; erro/vazio se nunca rodaram.
SELECT version_num FROM alembic_version;
```

**Nota, sem recomendação**: mesmo que a trava exista num banco, ela é do tipo
que atua linha a linha em alterações e exclusões — pela forma como foi escrita,
ela não cobre o comando `TRUNCATE` (que esvazia a tabela inteira de uma vez), e
o próprio arquivo de migração contém o comando que a remove
(`001_initial_schema.py:446-448`). Isso é registrado como característica do que
está escrito, não como caminho sugerido.

---

## 5. O nó com a LGPD — o ponto central da decisão

Quando um titular pede exclusão dos seus dados, o sistema executa uma rotina que
anonimiza cerca de 15 tabelas diferentes
(`backend/app/api/v1/lgpd.py:50-434`). Essa rotina **não altera nenhuma linha
pré-existente de `audit_logs`** — ela apenas **acrescenta** uma linha nova
registrando que a exclusão foi feita (`lgpd.py:416-422`).

Essa escolha está documentada de forma explícita no teste automatizado que
verifica se sobrou algum dado do titular no banco. O teste varre o banco inteiro
atrás de vestígios, mas exclui de propósito 4 colunas de `audit_logs`, com esta
justificativa escrita no próprio arquivo
(`backend/tests/test_api/test_lgpd_sentinela.py:31-39`):

> `audit_logs` é imutável por trigger de banco e é a própria prova de que o
> esquecimento foi executado (retenção é decisão jurídica em aberto, registrada
> no CLAUDE.md como débito).

**Duas observações sobre essa justificativa**, ambas factuais:

1. A premissa "é imutável por trigger de banco" é a que a seção 4 acima mostrou
   não se sustentar no banco verificado.
2. A exclusão do teste cobre 4 colunas (`action`, `resource_type`, `old_value`,
   `new_value`), mas **não** cobre `user_agent` nem `ip_address` — que são
   justamente as colunas presentes em toda linha.

**O impasse, formulado sem resolvê-lo**: o log de auditoria é ao mesmo tempo
(a) a prova de que o titular foi esquecido e (b) o último lugar onde rastros
dele — endereço de rede, navegador, identificador de usuário, e o próprio
identificador do titular dentro do texto da ação — continuam registrados. Apagar
o log enfraquece a prova; manter o log mantém o rastro. Não existe uma resposta
técnica para isso: é uma escolha de ponderação jurídica.

---

## 6. O que um expurgo quebraria (e o que não quebraria)

| O que usa `audit_logs` | Onde | Quem acessa | Efeito de um expurgo por data |
|---|---|---|---|
| Tela de Auditoria (listagem com filtro de data) | `frontend/src/app/(dashboard)/auditoria/page.tsx`, `backend/app/api/v1/audit.py` | ADMIN, SÓCIO | Períodos anteriores ao corte deixariam de aparecer |
| Exportação CSV da auditoria (teto de 50 mil linhas) | `backend/app/api/v1/audit.py:83-132` | ADMIN, SÓCIO | Idem — não exporta o que foi expurgado |
| Painel interno cross-escritório | `backend/app/api/v1/system.py:1248-1304` | SUPERADMIN | Idem |
| Agente de auditoria (detecção de anomalias) | `backend/app/agents/audit/audit_agent.py:17-53` | Automático | **Não seria afetado** — só olha as últimas 24 horas |

**Viabilidade técnica de um expurgo por data**: alta. Já existem os índices
`idx_audit_timestamp` e `idx_audit_tenant (tenant_id, timestamp)`
(`backend/app/core/events.py:279`), que tornam eficiente selecionar e remover
linhas mais antigas que uma data.

---

## 7. Opções técnicas disponíveis — sem escolher nenhuma

Nenhuma delas está implementada hoje. Cada uma é apresentada com o que exigiria
e com o precedente existente no próprio sistema.

**A. Expurgo físico por data.** Uma rotina periódica apaga linhas anteriores a
um prazo. É o padrão mais simples. *Precedente no sistema*: das 14 rotinas
periódicas existentes (`backend/app/workers/worker.py:73-163`), **apenas uma faz
exclusão física** — a limpeza de sessões expiradas
(`backend/app/workers/tasks/session_cleanup.py:14-48`, semanal). As demais
apenas marcam ou escalam registros, nunca apagam. *Perde*: a possibilidade de
consultar o período expurgado, para qualquer finalidade.

**B. Arquivamento em armazenamento frio.** As linhas antigas saem do banco ativo
mas são preservadas em arquivo externo. O sistema **já tem armazenamento S3
configurável** (`backend/app/config.py:187-192`), hoje usado para documentos e
logotipos — mas nenhuma linha de código o usa para auditoria. *Preserva* o
histórico para eventual necessidade probatória; *não resolve* sozinho a questão
da LGPD, porque o dado pessoal continua guardado, só que em outro lugar — a
pergunta de prazo continua de pé, aplicada ao arquivo.

**C. Anonimização em vez de exclusão.** A linha continua existindo (preservando
a prova de que a ação ocorreu, quando ocorreu e o resultado), mas os campos
pessoais — `ip_address`, `user_agent`, `user_id` — são zerados depois de um
prazo. *Preserva* a trilha de auditoria como registro de eventos; *reduz* o dado
pessoal retido. *Exige* decidir se uma trilha sem autor ainda serve à
finalidade pela qual ela existe.

**D. Prazos diferentes por tipo de ação.** Os dados da seção 3 mostram que as
linhas não são todas iguais: ~88% são registros automáticos de operação
rotineira, enquanto ~11% são registros deliberados de eventos sensíveis
(operações de LGPD, decisões de aprovação humana, acesso a painel interno).
Seria possível guardar as primeiras por menos tempo que as segundas. *Custo*:
mais complexidade e uma regra a mais para justificar.

---

## 8. As perguntas que só o escritório responde

Cada uma pode ser respondida em uma linha.

1. **Qual o prazo de retenção** dos registros de auditoria? Há base legal ou
   norma profissional (OAB, regras contábeis, prazo prescricional aplicável às
   ações do escritório) que já determine um mínimo?

2. **O prazo vale igual para tudo?** Um registro de "cliente cadastrado" e um
   registro de "pedido de exclusão de dados atendido" devem ser guardados pelo
   mesmo tempo? (ver opção D)

3. **Arquivo frio conta como retenção?** Se as linhas saírem do banco ativo e
   forem para armazenamento externo, o escritório considera que o dado foi
   retido ou que foi eliminado? (define se a opção B resolve ou apenas adia)

4. **Anonimizar basta?** Manter a linha sem o autor (sem IP, sem navegador, sem
   usuário) atende à finalidade pela qual a auditoria existe? (define se a
   opção C é viável)

5. **O que prevalece no conflito da seção 5?** Quando um titular exerce o
   direito ao esquecimento, o registro de auditoria que prova o atendimento
   desse pedido — e que contém identificadores dele — deve ser preservado,
   anonimizado ou também eliminado?

6. **A imutabilidade é um requisito ou era uma suposição?** A seção 4 mostra que
   o log não está tecnicamente protegido contra alteração no banco verificado.
   O escritório precisa que ele seja imutável (o que exige corrigir isso), ou a
   imutabilidade nunca foi um requisito e sim uma característica que se acreditava
   existir? A resposta muda tanto o valor probatório do log quanto o texto exibido
   ao usuário na tela `/sobre`.

---

## 9. O que este levantamento **não** conseguiu verificar

- **O banco de produção.** Todas as medições e testes desta seção foram feitos
  no banco de desenvolvimento. Volume real, presença da trava e estado das
  migrações em produção precisam ser confirmados com as consultas somente-leitura
  fornecidas nas seções 3 e 4.
- **Se a falha do comando de migração se reproduz em produção.** A causa
  identificada é de configuração e independe do ambiente, mas isso não substitui
  a verificação direta.

---

## 10. Referências de código citadas

| Assunto | Arquivo |
|---|---|
| Definição da tabela | `backend/app/models/audit_log.py:17-38` |
| Componente que grava automaticamente | `backend/app/core/middleware.py:88-115` |
| Lista de caminhos não auditados | `backend/app/core/middleware.py:13-14` |
| Definição da trava de imutabilidade | `backend/alembic/versions/001_initial_schema.py:415-428` |
| Remoção da trava (no próprio arquivo) | `backend/alembic/versions/001_initial_schema.py:446-448` |
| Configuração de conexão com o defeito | `backend/alembic.ini:6` |
| Migração tolerante a falha no boot | `backend/start.sh:47-54` |
| Criação de tabelas pelo caminho alternativo | `backend/app/core/events.py:228` |
| Índices por data | `backend/app/core/events.py:274-279` |
| Rotina de exclusão de dados (LGPD) | `backend/app/api/v1/lgpd.py:50-434` |
| Registro da própria operação de exclusão | `backend/app/api/v1/lgpd.py:416-422` |
| Exclusão deliberada no teste de vestígios | `backend/tests/test_api/test_lgpd_sentinela.py:31-39` |
| Endpoints de leitura da auditoria | `backend/app/api/v1/audit.py` |
| Painel cross-escritório | `backend/app/api/v1/system.py:1248-1304` |
| Agente de auditoria (janela de 24h) | `backend/app/agents/audit/audit_agent.py:17-53` |
| Rotinas periódicas (única com exclusão física) | `backend/app/workers/worker.py:73-163`, `backend/app/workers/tasks/session_cleanup.py:14-48` |
| Armazenamento S3 configurável | `backend/app/config.py:187-192` |
| Pendência exibida ao usuário | `frontend/src/app/(dashboard)/sobre/page.tsx:106` |
