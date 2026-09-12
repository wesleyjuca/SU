"""Fase 114 — a mensagem "fonte não respondeu" da captura por OAB descartava
a causa real (exceção de rede vs. HTTP não-200 da própria Comunica). Confirma
que buscar_comunicacoes agora preenche stats['status_code']/stats['error']
nos dois casos, permitindo diagnosticar sem adivinhar.

Fase pós-260.10 — o cliente HTTP trocou de `httpx` para `curl_cffi`
(`impersonate="chrome124"`, ver `comunica.py`), então os mocks aqui trocam de
`httpx.MockTransport` para uma fake `AsyncSession` monkeypatchada no lugar
onde `comunica.py` a usa (`app.integrations.dje.comunica.AsyncSession`)."""
from datetime import date

import pytest

import app.integrations.dje.comunica as comunica_mod
from app.integrations.dje.comunica import buscar_comunicacoes


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.text = text
        self.headers = {}

    def json(self):
        return self._json_data


class _FakeAsyncSession:
    """Fake curl_cffi.requests.AsyncSession — captura os kwargs de construção
    (headers/impersonate/timeout/...) e da chamada `.get()` (url/params),
    e devolve uma resposta ou lança uma exceção já roteirizadas."""

    def __init__(self, *, response=None, exception=None, captured=None, **kwargs):
        self._response = response
        self._exception = exception
        self._captured = captured if captured is not None else {}
        self._captured["session_kwargs"] = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, **kwargs):
        self._captured["url"] = url
        self._captured["get_kwargs"] = kwargs
        if self._exception is not None:
            raise self._exception
        return self._response


def _patch_session(monkeypatch, *, response=None, exception=None):
    """Monkeypatcha AsyncSession no módulo comunica.py; devolve o dict onde
    cada chamada real de sessão/get vai gravar seus kwargs."""
    captured: dict = {}

    def _factory(*a, **kwargs):
        return _FakeAsyncSession(response=response, exception=exception, captured=captured, **kwargs)

    monkeypatch.setattr(comunica_mod, "AsyncSession", _factory)
    return captured


@pytest.mark.asyncio
async def test_http_nao_200_preenche_status_code_e_error(monkeypatch):
    _patch_session(monkeypatch, response=_FakeResponse(500, text='{"erro": "interno"}'))

    stats: dict = {}
    resultado = await buscar_comunicacoes("123456", "CE", date(2026, 1, 1), date(2026, 7, 1), stats=stats)

    assert resultado == []
    assert stats.get("ok") is None  # nunca setado — não houve 200
    assert stats["status_code"] == 500
    assert "500" in stats["error"]


@pytest.mark.asyncio
async def test_excecao_de_rede_preenche_error(monkeypatch):
    _patch_session(monkeypatch, exception=ConnectionError("Connection refused"))

    stats: dict = {}
    resultado = await buscar_comunicacoes("123456", "CE", date(2026, 1, 1), date(2026, 7, 1), stats=stats)

    assert resultado == []
    assert stats.get("ok") is None
    assert "status_code" not in stats  # exceção antes de qualquer resposta HTTP
    assert "Connection refused" in stats["error"]


@pytest.mark.asyncio
async def test_http_403_preenche_status_code_e_error(monkeypatch):
    """Achado real em produção: a Comunica/DJEN devolveu 403 — a mensagem
    honesta da Fase 114 ("fonte não respondeu... verifique egress") saiu
    correta, mas a causa real (403, não falta de rede) só ficava visível no
    stats. Confirma o mesmo comportamento de captura de status_code/error
    para 403 especificamente."""
    _patch_session(monkeypatch, response=_FakeResponse(403, text="Forbidden"))

    stats: dict = {}
    resultado = await buscar_comunicacoes("123456", "CE", date(2026, 1, 1), date(2026, 7, 1), stats=stats)

    assert resultado == []
    assert stats["status_code"] == 403
    assert "403" in stats["error"]


@pytest.mark.asyncio
async def test_requisicao_usa_impersonate_chrome_e_headers_de_contexto(monkeypatch):
    """Fase 114 trocou o User-Agent genérico do httpx por um identificador
    próprio ("AFJ-Core/1.0 (...)") — resolveu a rejeição da época. A Fase 250
    achou um 403 real em produção mesmo com um UA de navegador manual, e a
    Fase 252 confirmou que o 403 persistiu — headers HTTP sozinhos não
    bastam contra um WAF que faz fingerprint na camada TLS. Fase pós-260.10:
    o cliente trocou pra `curl_cffi` com `impersonate="chrome124"`, que faz a
    libcurl reproduzir o aperto de mão TLS real de um Chrome — User-Agent/
    Accept/Accept-Language deixam de ser setados manualmente (o
    `default_headers=True` padrão do curl_cffi já gera esse conjunto,
    consistente com o fingerprint escolhido); Referer/Origin continuam
    manuais, por serem específicos deste contexto de chamada."""
    captured = _patch_session(monkeypatch, response=_FakeResponse(200, json_data={"items": []}))

    await buscar_comunicacoes("123456", "CE", date(2026, 1, 1), date(2026, 7, 1))

    session_kwargs = captured["session_kwargs"]
    assert session_kwargs["impersonate"] == "chrome124"
    headers = session_kwargs["headers"]
    assert headers["Referer"] == "https://comunica.pje.jus.br/consulta"
    assert headers["Origin"] == "https://comunica.pje.jus.br"
    # Não setamos mais manualmente — curl_cffi gera a partir de impersonate,
    # e misturar um UA manual com um fingerprint TLS diferente seria, ele
    # mesmo, um sinal que um WAF mais sofisticado pega.
    assert "User-Agent" not in headers
    assert "Accept" not in headers
    assert "Accept-Language" not in headers


@pytest.mark.asyncio
async def test_falha_captura_corpo_bruto_da_resposta(monkeypatch):
    """Fase 252 — o 403 persistiu em produção mesmo depois do fix de headers
    da Fase 250, indício de um bloqueio mais fundo (fingerprint TLS, IP na
    lista negra do WAF) — mas até aqui só o status code era capturado,
    nunca o CORPO da resposta (que revelaria, por exemplo, uma página de
    desafio Cloudflare/Akamai em vez de um 403 seco). Confirma que
    `stats["body_snippet"]` chega preenchido e truncado."""
    corpo_desafio = "<html><body>Access denied — Cloudflare Ray ID: abc123</body></html>" + ("x" * 600)
    _patch_session(monkeypatch, response=_FakeResponse(403, text=corpo_desafio))

    stats: dict = {}
    resultado = await buscar_comunicacoes("123456", "CE", date(2026, 1, 1), date(2026, 7, 1), stats=stats)

    assert resultado == []
    assert stats["status_code"] == 403
    assert "Cloudflare Ray ID" in stats["body_snippet"]
    assert len(stats["body_snippet"]) <= 500


@pytest.mark.asyncio
async def test_sucesso_200_nao_seta_status_code_nem_error(monkeypatch):
    _patch_session(monkeypatch, response=_FakeResponse(200, json_data={"items": []}))

    stats: dict = {}
    await buscar_comunicacoes("123456", "CE", date(2026, 1, 1), date(2026, 7, 1), stats=stats)

    assert stats.get("ok") is True
    assert "error" not in stats
    assert "status_code" not in stats


# ─── Fase pós-262 — cadeia de fallback de impersonation ───────────────────────

def _patch_session_sequence(monkeypatch, respostas: list):
    """Cada item de `respostas` é usado numa sessão (perfil) por vez, na
    ordem de construção — simula "o 1º perfil falha, o 2º funciona" etc.
    Devolve a lista de `session_kwargs` capturados, um por sessão criada."""
    todas_kwargs: list = []
    chamadas = {"n": 0}

    def _factory(*a, **kwargs):
        i = chamadas["n"]
        chamadas["n"] += 1
        item = respostas[min(i, len(respostas) - 1)]
        todas_kwargs.append(kwargs)
        if isinstance(item, Exception):
            return _FakeAsyncSession(exception=item, captured={}, **kwargs)
        return _FakeAsyncSession(response=item, captured={}, **kwargs)

    monkeypatch.setattr(comunica_mod, "AsyncSession", _factory)
    return todas_kwargs


@pytest.mark.asyncio
async def test_1o_perfil_falha_2o_funciona(monkeypatch):
    """Prova nos 2 sentidos: sem a cadeia de fallback, 1 perfil falhando
    (403) devolveria [] direto — com ela, o 2º perfil (safari184) é
    tentado e o resultado real aparece."""
    kwargs_por_sessao = _patch_session_sequence(monkeypatch, [
        _FakeResponse(403, text="Forbidden"),
        _FakeResponse(200, json_data={"items": [{"id": "1", "texto": "intimação real"}]}),
    ])

    stats: dict = {}
    resultado = await buscar_comunicacoes("123456", "CE", date(2026, 1, 1), date(2026, 7, 1), stats=stats)

    assert len(resultado) == 1
    assert resultado[0].texto == "intimação real"
    assert stats["ok"] is True
    assert stats["impersonate"] == "safari184"
    # confirma que o 1º perfil tentado foi chrome124, o 2º safari184 — a
    # ordem declarada em `_IMPERSONATE_PROFILES`.
    assert kwargs_por_sessao[0]["impersonate"] == "chrome124"
    assert kwargs_por_sessao[1]["impersonate"] == "safari184"


@pytest.mark.asyncio
async def test_todos_os_perfis_falham_diagnostico_do_ultimo(monkeypatch):
    kwargs_por_sessao = _patch_session_sequence(monkeypatch, [
        _FakeResponse(403, text="Forbidden 1"),
        _FakeResponse(403, text="Forbidden 2"),
        _FakeResponse(403, text="Forbidden 3"),
    ])

    stats: dict = {}
    resultado = await buscar_comunicacoes("123456", "CE", date(2026, 1, 1), date(2026, 7, 1), stats=stats)

    assert resultado == []
    assert stats.get("ok") is None
    assert stats["impersonate"] == "firefox135"  # o último tentado
    assert stats["status_code"] == 403
    assert "testados contra o WAF" in stats["error"]
    assert "chrome124" in stats["error"] and "safari184" in stats["error"] and "firefox135" in stats["error"]
    assert len(kwargs_por_sessao) == 3  # os 3 perfis foram de fato tentados


class _RaiseNaConstrucao(Exception):
    """Simula `curl_cffi.requests.impersonate.ImpersonateError` — levantada
    dentro de `AsyncSession.__init__`, ANTES de qualquer requisição de
    rede. Achado real desta fase: o valor antigo `"safari17"` (inválido na
    lib instalada) causava exatamente isso, e o diagnóstico antigo
    afirmava incorretamente que esse perfil tinha sido "tentado" contra o
    WAF."""


def _patch_session_com_falha_de_construcao(monkeypatch, perfis_que_falham_na_construcao: set):
    """Perfis em `perfis_que_falham_na_construcao` levantam ao CONSTRUIR a
    sessão (nunca chegam a `.get()`); os demais usam `_FakeResponse(403)`."""
    todas_kwargs: list = []

    def _factory(*a, **kwargs):
        todas_kwargs.append(kwargs)
        if kwargs.get("impersonate") in perfis_que_falham_na_construcao:
            raise _RaiseNaConstrucao(f"Impersonating {kwargs.get('impersonate')} is not supported")
        return _FakeAsyncSession(response=_FakeResponse(403, text="Forbidden"), captured={}, **kwargs)

    monkeypatch.setattr(comunica_mod, "AsyncSession", _factory)
    return todas_kwargs


@pytest.mark.asyncio
async def test_perfil_invalido_nao_e_contado_como_tentado_contra_o_waf(monkeypatch):
    """Achado real desta fase (bug no próprio fallback da fase anterior):
    um perfil rejeitado na CONSTRUÇÃO da sessão (nunca tocou rede) não
    pode aparecer na mensagem final como "testado contra o WAF" — só quem
    de fato fez uma requisição e foi recusado entra nessa lista. Prova nos
    2 sentidos: com o bug antigo (sem a distinção), este teste falharia
    porque o perfil inválido apareceria em `stats["error"]`."""
    _patch_session_com_falha_de_construcao(monkeypatch, {"safari184"})

    stats: dict = {}
    resultado = await buscar_comunicacoes("123456", "CE", date(2026, 1, 1), date(2026, 7, 1), stats=stats)

    assert resultado == []
    assert stats["perfis_rejeitados_localmente"] == ["safari184"]
    assert "safari184" not in stats["error"]
    assert "chrome124" in stats["error"] and "firefox135" in stats["error"]
    assert stats["impersonate"] == "firefox135"  # o último tentado (mesmo rejeitado)


@pytest.mark.asyncio
async def test_todos_os_perfis_rejeitados_na_construcao_nao_afirma_teste_contra_waf(monkeypatch):
    """Se NENHUM perfil chegar a tocar a rede, a mensagem de erro não pode
    citar "testados contra o WAF" (seria falso) — cai no ramo de exceção
    pura, sem status_code."""
    _patch_session_com_falha_de_construcao(monkeypatch, {"chrome124", "safari184", "firefox135"})

    stats: dict = {}
    resultado = await buscar_comunicacoes("123456", "CE", date(2026, 1, 1), date(2026, 7, 1), stats=stats)

    assert resultado == []
    assert set(stats["perfis_rejeitados_localmente"]) == {"chrome124", "safari184", "firefox135"}
    assert "status_code" not in stats
    assert "testados contra o WAF" not in stats["error"]
