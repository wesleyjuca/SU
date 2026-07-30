# `services/`

Lógica de negócio que **orquestra e persiste estado** — lê/grava no Postgres,
decide regras (quem notificar, o que fica pendente de aprovação, como
calcular um prazo), e frequentemente chama código de `integrations/` como um
passo dentro de um fluxo maior. Se o módulo termina numa mudança de linha no
banco (ou dispara um efeito colateral como notificação/e-mail), é `services/`.

Exemplos: `oab_capture.py` (orquestra a captura, grava `LegalProcess`),
`notification_service.py`/`approval_service.py` (persistem e notificam),
`payment_gateway.py` (cria cobrança e atualiza a fatura).

Ver também `integrations/README.md` — a distinção não é rígida (alguns
módulos fazem as duas coisas), é só o critério usado para decidir onde um
arquivo novo deveria entrar.
