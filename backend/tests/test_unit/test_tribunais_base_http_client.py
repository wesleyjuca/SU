"""Fase 123 — httpx exigia que valores de header fossem ASCII/latin-1
(RFC 7230); o `User-Agent` de `BaseTribunalClient.http` tinha um acento
("escritório"), fazendo QUALQUER chamada real explodir com
`UnicodeEncodeError` na primeira construção do client.

Rodada pós-260.10 (correção do catálogo de integrações .jus.br) tornou
esse teste obsoleto por completo: o header manual de `User-Agent` foi
REMOVIDO (era exatamente o tipo de string autoidentificada — "AFJ-Core/1.0
(...)" — que causou o 403 confirmado do Comunica/DJEN), e o cliente HTTP
trocou de `httpx.AsyncClient` para `curl_cffi.requests.AsyncSession` com
`impersonate="chrome124"`. Sem User-Agent manual, o problema de encoding
não pode mais existir — este teste passa a confirmar o novo contrato."""
from curl_cffi.requests import AsyncSession

from app.integrations.tribunais.cnj import CNJDataJudClient


def test_http_client_constroi_sem_levantar():
    client = CNJDataJudClient(tribunal="TJSP")
    # Regressão: a construção do client não pode levantar por nenhum motivo
    # (nem o UnicodeEncodeError original, nem nada novo introduzido pela
    # troca de biblioteca).
    http_client = client.http
    assert isinstance(http_client, AsyncSession)


def test_http_client_usa_tls_impersonation_sem_user_agent_manual():
    """Prova nos dois sentidos: reverter pra httpx.AsyncClient sem
    impersonate faria este teste falhar (AttributeError/assert False)."""
    client = CNJDataJudClient(tribunal="TJSP")
    http_client = client.http
    assert http_client.impersonate == "chrome124"
    # Nenhum header próprio setado na construção — o Chrome-UA/Accept/
    # Accept-Language vêm todos do impersonate, nunca de um dict manual
    # (misturar os dois seria, ele mesmo, um sinal que um WAF pega).
    assert not dict(http_client.headers)
