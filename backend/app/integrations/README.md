# `integrations/`

Clientes de API externa que **buscam ou enviam dado sem persistir nada por
conta própria** — o chamador (normalmente algo em `services/`) decide o que
fazer com o resultado. Se o módulo é essencialmente "monta a requisição HTTP,
faz parsing tolerante da resposta, devolve", é `integrations/`.

Exemplos: `llm_client.py`/`anthropic_client.py` (chamam o LLM, não gravam
nada), `dje/`, `tribunais/`, `fontes/`, `lexml/` (clientes de fontes
processuais/jurídicas públicas ou credenciadas).

Ver também `services/README.md`. A distinção é um guia, não uma regra
rígida — alguns módulos de `services/` fazem chamada HTTP direta quando o
fluxo é simples o bastante para não valer a pena separar; nenhum arquivo
hoje está genuinamente no lugar errado (auditado na Fase 115).
