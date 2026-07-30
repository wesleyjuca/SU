"""Fase 123 — httpx exige que valores de header sejam ASCII/latin-1 por
padrão (RFC 7230); o `User-Agent` de `BaseTribunalClient.http` tinha um
acento ("escritório"), fazendo QUALQUER chamada real (`fetch_processo`/
`fetch_movements`) explodir com `UnicodeEncodeError` na primeira construção
do client — silenciosamente engolido pelo `except Exception` ao redor de
cada chamada em `cnj.py`, reportado só como um warning genérico no log.
Achado incidental ao investigar um 403 real na Comunica/DJEN (mesma classe
de bug: header sem cuidado com encoding). Confirma que o client constrói e
usa o header sem levantar, e que o valor é puro ASCII."""
from app.integrations.tribunais.cnj import CNJDataJudClient


def test_http_client_constroi_sem_levantar():
    client = CNJDataJudClient(tribunal="TJSP")
    # Regressão: antes da correção, acessar .http levantava UnicodeEncodeError.
    http_client = client.http
    assert http_client.headers["user-agent"].startswith("AFJ-Core/1.0")


def test_user_agent_e_ascii_puro():
    client = CNJDataJudClient(tribunal="TJSP")
    ua = client.http.headers["user-agent"]
    ua.encode("ascii")  # não deve levantar UnicodeEncodeError
