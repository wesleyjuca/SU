"""Fase 93 — cliente LexML: parsing tolerante da resposta SRU (XML mockado).
Fase 138.3 — descoberta em lote + extração de texto (LexML → Planalto)."""
import pytest

from app.integrations.lexml.client import (
    _parsear_resposta, _parsear_registros, buscar_lei,
    buscar_lote_legislacao_federal, baixar_texto_norma, buscar_norma_completa,
)


def test_parsear_resposta_encontrada():
    xml = """<?xml version="1.0"?>
    <searchRetrieveResponse xmlns="http://www.loc.gov/zing/srw/">
      <numberOfRecords>1</numberOfRecords>
      <records>
        <record>
          <recordData>
            <title>Código de Defesa do Consumidor</title>
            <urn>urn:lex:br:federal:lei:1990-09-11;8078</urn>
          </recordData>
        </record>
      </records>
    </searchRetrieveResponse>"""
    r = _parsear_resposta(xml)
    assert r == {
        "encontrado": True,
        "titulo": "Código de Defesa do Consumidor",
        "urn": "urn:lex:br:federal:lei:1990-09-11;8078",
    }


def test_parsear_resposta_nao_encontrada():
    xml = '<searchRetrieveResponse><numberOfRecords>0</numberOfRecords></searchRetrieveResponse>'
    r = _parsear_resposta(xml)
    assert r == {"encontrado": False, "titulo": None, "urn": None}


def test_parsear_resposta_xml_quebrado_retorna_none():
    assert _parsear_resposta("isso não é XML <<<") is None
    assert _parsear_resposta("") is None


def test_parsear_resposta_sem_number_of_records_retorna_none():
    assert _parsear_resposta("<root><foo>bar</foo></root>") is None


@pytest.mark.asyncio
async def test_buscar_lei_rede_indisponivel_retorna_none(monkeypatch):
    import httpx

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            raise httpx.ConnectError("sem rede")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **k: _FakeClient())

    resultado = await buscar_lei("8078/1990")
    assert resultado is None


# ─── Fase 138.3 — _parsear_registros (multi-record, puro, sem rede) ───────────

def test_parsear_registros_multiplo_com_location():
    xml = """<?xml version="1.0"?>
    <searchRetrieveResponse xmlns="http://www.loc.gov/zing/srw/">
      <numberOfRecords>2</numberOfRecords>
      <records>
        <record>
          <recordData>
            <title>Lei nº 1</title>
            <urn>urn:lex:br:federal:lei:2026-01-01;1</urn>
            <location>https://www.planalto.gov.br/ccivil_03/leis/l1.htm</location>
          </recordData>
        </record>
        <record>
          <recordData>
            <title>Lei nº 2</title>
            <urn>urn:lex:br:federal:lei:2026-01-02;2</urn>
            <location>https://www.planalto.gov.br/ccivil_03/leis/l2.htm</location>
          </recordData>
        </record>
      </records>
    </searchRetrieveResponse>"""
    registros = _parsear_registros(xml)
    assert registros == [
        {"urn": "urn:lex:br:federal:lei:2026-01-01;1", "titulo": "Lei nº 1", "url": "https://www.planalto.gov.br/ccivil_03/leis/l1.htm"},
        {"urn": "urn:lex:br:federal:lei:2026-01-02;2", "titulo": "Lei nº 2", "url": "https://www.planalto.gov.br/ccivil_03/leis/l2.htm"},
    ]


def test_parsear_registros_sem_url_resolvivel():
    xml = """<searchRetrieveResponse>
      <records>
        <record>
          <recordData>
            <title>Lei sem URL</title>
            <urn>urn:lex:br:federal:lei:2026-01-01;1</urn>
          </recordData>
        </record>
      </records>
    </searchRetrieveResponse>"""
    registros = _parsear_registros(xml)
    assert registros == [{"urn": "urn:lex:br:federal:lei:2026-01-01;1", "titulo": "Lei sem URL", "url": None}]


def test_parsear_registros_identifier_dublin_core_com_namespace():
    xml = """<?xml version="1.0"?>
    <searchRetrieveResponse xmlns:dc="http://purl.org/dc/elements/1.1/">
      <records>
        <record>
          <recordData>
            <urn>urn:lex:br:federal:decreto:2026-01-01;1</urn>
            <dc:identifier>https://www.planalto.gov.br/ccivil_03/decreto/d1.htm</dc:identifier>
          </recordData>
        </record>
      </records>
    </searchRetrieveResponse>"""
    registros = _parsear_registros(xml)
    assert registros == [{
        "urn": "urn:lex:br:federal:decreto:2026-01-01;1", "titulo": None,
        "url": "https://www.planalto.gov.br/ccivil_03/decreto/d1.htm",
    }]


def test_parsear_registros_xml_quebrado_retorna_lista_vazia():
    assert _parsear_registros("isso não é XML <<<") == []
    assert _parsear_registros("") == []


def test_parsear_registros_record_sem_urn_e_pulado():
    xml = """<searchRetrieveResponse>
      <records>
        <record><recordData><title>Sem URN</title></recordData></record>
      </records>
    </searchRetrieveResponse>"""
    assert _parsear_registros(xml) == []


def test_parsear_registros_url_nao_http_e_ignorada():
    xml = """<searchRetrieveResponse>
      <records>
        <record>
          <recordData>
            <urn>urn:lex:br:federal:lei:2026-01-01;1</urn>
            <location>não é uma url</location>
          </recordData>
        </record>
      </records>
    </searchRetrieveResponse>"""
    registros = _parsear_registros(xml)
    assert registros == [{"urn": "urn:lex:br:federal:lei:2026-01-01;1", "titulo": None, "url": None}]


# ─── Fase 138.3 — buscar_lote_legislacao_federal (mock em nível de função,
# não toca a rede/breaker real) ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_buscar_lote_legislacao_federal_filtra_sem_url(monkeypatch):
    import app.integrations.lexml.client as mod

    async def _fake_buscar_lote(tipo, maximum_records=50):
        if tipo == "Lei":
            return [
                {"urn": "urn:lex:br:federal:lei:1", "titulo": "Com URL", "url": "https://planalto.gov.br/l1.htm"},
                {"urn": "urn:lex:br:federal:lei:2", "titulo": "Sem URL", "url": None},
            ]
        return [{"urn": "urn:lex:br:federal:decreto:1", "titulo": "Decreto", "url": "https://planalto.gov.br/d1.htm"}]

    monkeypatch.setattr(mod, "buscar_lote_legislacao", _fake_buscar_lote)

    resultado = await buscar_lote_legislacao_federal()
    assert resultado == [
        {"urn": "urn:lex:br:federal:lei:1", "titulo": "Com URL", "url": "https://planalto.gov.br/l1.htm", "tipo_norma": "Lei"},
        {"urn": "urn:lex:br:federal:decreto:1", "titulo": "Decreto", "url": "https://planalto.gov.br/d1.htm", "tipo_norma": "Decreto"},
    ]


# ─── Fase 138.3 — baixar_texto_norma / buscar_norma_completa (mock de rede) ──
#
# Nota: estes 2 testes de rede usam o `_breaker` module-level real (mesmo
# singleton usado por `buscar_lei`) — o teste de sucesso vem primeiro pra
# garantir `record_success()` (zera falhas acumuladas) antes do teste de
# falha, evitando que o circuito abra e mascare o `default=None` de uma
# falha real com o `default=None` de um circuito já aberto.

@pytest.mark.asyncio
async def test_baixar_texto_norma_extrai_texto_de_html_simples(monkeypatch):
    import httpx

    html = (
        "<html><head><style>.x{color:red}</style></head><body>"
        "<script>var MARCADOR_SCRIPT = 1;</script>"
        "<p>Art. 1º Texto da lei.</p></body></html>"
    )

    class _FakeResponse:
        status_code = 200
        text = html

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return _FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **k: _FakeClient())

    texto = await baixar_texto_norma("https://www.planalto.gov.br/ccivil_03/leis/l1.htm")
    assert texto is not None
    assert "Art. 1º Texto da lei." in texto
    assert "MARCADOR_SCRIPT" not in texto


@pytest.mark.asyncio
async def test_baixar_texto_norma_rede_indisponivel_retorna_none(monkeypatch):
    import httpx

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            raise httpx.ConnectError("sem rede")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **k: _FakeClient())

    assert await baixar_texto_norma("https://www.planalto.gov.br/ccivil_03/leis/l1.htm") is None


@pytest.mark.asyncio
async def test_buscar_norma_completa_sem_url_retorna_none():
    assert await buscar_norma_completa({"urn": "urn:x", "titulo": "X", "url": None}) is None


@pytest.mark.asyncio
async def test_buscar_norma_completa_texto_vazio_retorna_none(monkeypatch):
    import app.integrations.lexml.client as mod

    async def _fake_baixar(url):
        return ""

    monkeypatch.setattr(mod, "baixar_texto_norma", _fake_baixar)

    registro = {"urn": "urn:x", "titulo": "X", "url": "https://planalto.gov.br/x.htm", "tipo_norma": "Lei"}
    assert await buscar_norma_completa(registro) is None


@pytest.mark.asyncio
async def test_buscar_norma_completa_sucesso(monkeypatch):
    import app.integrations.lexml.client as mod

    async def _fake_baixar(url):
        return "Art. 1º Texto integral."

    monkeypatch.setattr(mod, "baixar_texto_norma", _fake_baixar)

    registro = {"urn": "urn:x", "titulo": "Lei X", "url": "https://planalto.gov.br/x.htm", "tipo_norma": "Lei"}
    resultado = await buscar_norma_completa(registro)
    assert resultado == {
        "fonte_documento_id": "urn:x", "titulo": "Lei X", "tipo_norma": "Lei",
        "urn": "urn:x", "texto": "Art. 1º Texto integral.",
    }
