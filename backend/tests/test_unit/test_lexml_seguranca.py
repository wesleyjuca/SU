"""Integração LexML — as 3 correções de segurança/robustez do cliente.

Contexto medido (não suposto) durante a auditoria, com Python 3.11.15:

- **XXE não se aplica**: `xml.etree.ElementTree` recusa entidade externa
  (`ParseError: undefined entity`). A preocupação clássica não era o risco aqui.
- **Expansão de entidade interna PASSA** no ElementTree — esse é o vetor real
  (DoS de memória). `defusedxml` fecha.
- **SSRF era real**: `baixar_texto_norma()` faz GET numa URL que veio da
  RESPOSTA EXTERNA. Sem allowlist, o portal (ou quem o comprometesse) escolhia
  o alvo — incluindo `169.254.169.254` (metadata de nuvem) e rede interna.
"""
import pytest

from app.integrations.lexml.client import (
    _fromstring_seguro,
    _parsear_registros,
    _parsear_resposta,
    url_permitida,
)

# ─── Parsing seguro ──────────────────────────────────────────────────────────

_BILLION_LAUGHS = """<?xml version="1.0"?>
<!DOCTYPE r [
  <!ENTITY a "AAAAAAAAAA">
  <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">
  <!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">
]>
<r>&c;</r>"""

_XXE = """<?xml version="1.0"?>
<!DOCTYPE r [ <!ENTITY x SYSTEM "file:///etc/passwd"> ]>
<r>&x;</r>"""


def test_expansao_de_entidade_e_recusada():
    """O vetor que de fato existia. Com `ET.fromstring` isto parseava."""
    assert _fromstring_seguro(_BILLION_LAUGHS) is None


def test_entidade_externa_e_recusada():
    """Já era recusado antes; a troca de parser não pode ter regredido isso."""
    assert _fromstring_seguro(_XXE) is None


def test_xml_acima_do_teto_nao_chega_ao_parser():
    gigante = "<r>" + ("x" * (9 * 1024 * 1024)) + "</r>"
    assert _fromstring_seguro(gigante) is None


def test_xml_legitimo_continua_parseando():
    """Regressão: o XML real do LexML (com namespace SRU) segue funcionando."""
    xml = """<?xml version="1.0"?>
    <srw:searchRetrieveResponse xmlns:srw="http://www.loc.gov/zing/srw/">
      <srw:numberOfRecords>1</srw:numberOfRecords>
      <srw:records><srw:record><srw:recordData>
        <urn>urn:lex:br:federal:lei:1990-09-11;8078</urn>
        <title>Código de Defesa do Consumidor</title>
        <location>https://www.planalto.gov.br/ccivil_03/leis/l8078.htm</location>
      </srw:recordData></srw:record></srw:records>
    </srw:searchRetrieveResponse>"""
    resposta = _parsear_resposta(xml)
    assert resposta is not None
    assert resposta["encontrado"] is True
    assert resposta["urn"] == "urn:lex:br:federal:lei:1990-09-11;8078"

    registros = _parsear_registros(xml)
    assert len(registros) == 1
    assert registros[0]["url"].startswith("https://www.planalto.gov.br/")


def test_xml_malformado_nao_lanca():
    assert _fromstring_seguro("<r><naofecha>") is None
    assert _parsear_resposta("<r><naofecha>") is None
    assert _parsear_registros("<r><naofecha>") == []


# ─── Allowlist de domínio (SSRF) ─────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "https://www.planalto.gov.br/ccivil_03/leis/l8078.htm",
    "https://www25.senado.leg.br/web/atividade/norma/x",
    "https://www.camara.leg.br/proposicoesWeb/x",
    "https://www.stj.jus.br/algum/caminho",
    "http://www.mpf.mp.br/norma",
])
def test_portais_oficiais_sao_permitidos(url):
    assert url_permitida(url) is True


@pytest.mark.parametrize("url, motivo", [
    ("http://169.254.169.254/latest/meta-data/", "metadata de nuvem por IP"),
    ("http://127.0.0.1:8000/api/v1/users", "loopback"),
    ("http://10.0.0.5/interno", "rede privada por IP"),
    ("http://[::1]/interno", "loopback IPv6"),
    ("https://evil.example.com/payload", "domínio arbitrário"),
    ("https://planalto.gov.br.evil.com/x", "sufixo falsificado"),
    ("file:///etc/passwd", "esquema não-HTTP"),
    ("ftp://ftp.planalto.gov.br/x", "esquema não-HTTP"),
    ("", "vazio"),
    ("não é url", "lixo"),
])
def test_alvos_perigosos_sao_bloqueados(url, motivo):
    assert url_permitida(url) is False, f"deveria bloquear: {motivo}"


@pytest.mark.asyncio
async def test_baixar_texto_norma_recusa_url_fora_da_allowlist(monkeypatch):
    """Prova de que o guard roda ANTES de qualquer I/O.

    Nota de desenho, aprendida na própria verificação: a 1ª versão deste teste
    fazia o fake de `AsyncClient` LEVANTAR se fosse chamado — e passava mesmo
    com o guard removido, porque `CircuitBreaker.run()` captura toda exceção e
    devolve o `default`. É a armadilha já catalogada no CLAUDE.md ("fail-soft
    pode engolir o sinal"). Agora registramos a tentativa num flag e afirmamos
    sobre ele, que o breaker não tem como mascarar.
    """
    import app.integrations.lexml.client as mod

    tentativas: list[str] = []

    class _ClientEspiao:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **k):
            tentativas.append(url)
            raise AssertionError("não deveria ter chegado aqui")

    monkeypatch.setattr(mod.httpx, "AsyncClient", _ClientEspiao)

    assert await mod.baixar_texto_norma("http://169.254.169.254/latest/") is None
    assert tentativas == [], f"o guard não bloqueou — houve requisição a {tentativas}"


@pytest.mark.asyncio
async def test_baixar_texto_norma_segue_url_permitida(monkeypatch):
    """Regressão: uma URL legítima continua sendo buscada normalmente."""
    import app.integrations.lexml.client as mod

    tentativas: list[str] = []

    class _Resp:
        status_code = 200
        is_redirect = False
        text = "<html><body><p>Art. 1º Texto da norma.</p></body></html>"

    class _ClientOk:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **k):
            tentativas.append(url)
            return _Resp()

    monkeypatch.setattr(mod.httpx, "AsyncClient", _ClientOk)

    texto = await mod.baixar_texto_norma("https://www.planalto.gov.br/ccivil_03/leis/l8078.htm")
    assert texto is not None and "Art. 1º" in texto
    assert len(tentativas) == 1


@pytest.mark.asyncio
async def test_redirect_para_fora_da_allowlist_e_bloqueado(monkeypatch):
    """O ponto que um `follow_redirects=True` simples deixaria passar: a URL
    inicial é legítima, o redirect não."""
    import app.integrations.lexml.client as mod

    tentativas: list[str] = []

    class _RespRedirect:
        status_code = 302
        is_redirect = True

        class next_request:  # noqa: N801 — imita o atributo do httpx
            url = "http://169.254.169.254/latest/meta-data/"

    class _ClientRedirecionador:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **k):
            tentativas.append(url)
            return _RespRedirect()

    monkeypatch.setattr(mod.httpx, "AsyncClient", _ClientRedirecionador)

    assert await mod.baixar_texto_norma("https://www.planalto.gov.br/x") is None
    # buscou só a URL original; nunca seguiu para o destino do redirect
    assert tentativas == ["https://www.planalto.gov.br/x"]
