"""Fase 138.1 — cliente do portal de dados abertos do STJ. Testa as funções
puras (`parsear_pacote`, `resource_mais_recente`) sem rede — o shape exato da
API/dataset não é verificável neste ambiente (ver docstring do módulo), então
o parser precisa ser tolerante: nunca lança, degrada pra lista vazia."""
import io
import json
import zipfile

import pytest

from app.integrations.jurisprudencia.stj_client import (
    parsear_pacote, resource_mais_recente, listar_recursos, buscar_lote_recente,
)


def _zip_com_entradas(entradas: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for nome, conteudo in entradas.items():
            zf.writestr(nome, conteudo)
    return buf.getvalue()


def test_parsear_pacote_formato_esperado():
    decisao = {
        "numero_processo": "1234567-89.2025.3.00.0000",
        "relator": "Min. Fulano de Tal",
        "data": "2026-01-15",
        "orgao_julgador": "3ª Turma",
        "ementa": "EMENTA: direito civil...",
    }
    pacote = _zip_com_entradas({"decisao_1.json": json.dumps(decisao).encode()})
    registros = parsear_pacote(pacote)

    assert len(registros) == 1
    r = registros[0]
    assert r["numero_processo"] == "1234567-89.2025.3.00.0000"
    assert r["relator"] == "Min. Fulano de Tal"
    assert r["orgao_julgador"] == "3ª Turma"
    assert "EMENTA" in r["texto"]
    assert r["fonte_documento_id"] == "1234567-89.2025.3.00.0000"


def test_parsear_pacote_aliases_alternativos_de_campo():
    """Nomes de campo alternativos plausíveis (camelCase, sinônimos) também
    devem ser reconhecidos — o shape real do dataset não é 100% conhecido."""
    decisao = {
        "numeroProcesso": "9999999-11.2025.3.00.0000",
        "ministro_relator": "Min. Ciclana",
        "inteiro_teor": "Texto completo da decisão aqui.",
    }
    pacote = _zip_com_entradas({"x.json": json.dumps(decisao).encode()})
    registros = parsear_pacote(pacote)

    assert len(registros) == 1
    assert registros[0]["numero_processo"] == "9999999-11.2025.3.00.0000"
    assert registros[0]["relator"] == "Min. Ciclana"
    assert registros[0]["texto"] == "Texto completo da decisão aqui."


def test_parsear_pacote_sem_texto_e_pulada():
    decisao_sem_texto = {"numero_processo": "111", "relator": "X"}
    pacote = _zip_com_entradas({"sem_texto.json": json.dumps(decisao_sem_texto).encode()})
    assert parsear_pacote(pacote) == []


def test_parsear_pacote_entrada_json_invalida_nao_quebra_as_outras():
    boa = {"numero_processo": "222", "ementa": "texto válido"}
    pacote = _zip_com_entradas({
        "quebrada.json": b"{isso nao e json valido",
        "boa.json": json.dumps(boa).encode(),
        "irrelevante.txt": b"arquivo que nao e .json, ignorado",
    })
    registros = parsear_pacote(pacote)
    assert len(registros) == 1
    assert registros[0]["numero_processo"] == "222"


def test_parsear_pacote_zip_invalido_nao_lanca():
    assert parsear_pacote(b"isso nao e um zip de verdade") == []


def test_parsear_pacote_zip_vazio():
    assert parsear_pacote(_zip_com_entradas({})) == []


def test_parsear_pacote_entrada_json_nao_e_objeto():
    pacote = _zip_com_entradas({"lista.json": json.dumps(["a", "b"]).encode()})
    assert parsear_pacote(pacote) == []


def test_parsear_pacote_fonte_documento_id_cai_pro_nome_do_arquivo_sem_numero_processo():
    decisao = {"ementa": "sem numero de processo neste registro"}
    pacote = _zip_com_entradas({"decisao_especial.json": json.dumps(decisao).encode()})
    registros = parsear_pacote(pacote)
    assert len(registros) == 1
    assert registros[0]["fonte_documento_id"] == "decisao_especial.json"


def test_resource_mais_recente_escolhe_por_last_modified():
    resources = [
        {"name": "202501", "last_modified": "2025-01-31T00:00:00", "url": "http://x/1"},
        {"name": "202503", "last_modified": "2025-03-31T00:00:00", "url": "http://x/3"},
        {"name": "202502", "last_modified": "2025-02-28T00:00:00", "url": "http://x/2"},
    ]
    escolhido = resource_mais_recente(resources)
    assert escolhido["name"] == "202503"


def test_resource_mais_recente_lista_vazia():
    assert resource_mais_recente([]) is None


def test_resource_mais_recente_fallback_pro_nome_sem_last_modified():
    resources = [
        {"name": "202501", "url": "http://x/1"},
        {"name": "202503", "url": "http://x/3"},
    ]
    escolhido = resource_mais_recente(resources)
    assert escolhido["name"] == "202503"


@pytest.mark.asyncio
async def test_listar_recursos_rede_indisponivel_retorna_none(monkeypatch):
    import httpx

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            raise httpx.ConnectError("sem rede")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **k: _FakeClient())

    assert await listar_recursos() is None


@pytest.mark.asyncio
async def test_listar_recursos_resposta_success_false_retorna_none(monkeypatch):
    import httpx

    class _FakeResp:
        status_code = 200

        def json(self):
            return {"success": False, "error": {"message": "not found"}}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            return _FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **k: _FakeClient())

    assert await listar_recursos() is None


@pytest.mark.asyncio
async def test_buscar_lote_recente_degrada_pra_lista_vazia_sem_recursos(monkeypatch):
    import app.integrations.jurisprudencia.stj_client as stj_mod

    monkeypatch.setattr(stj_mod, "listar_recursos", lambda: _async_none())

    assert await buscar_lote_recente() == []


async def _async_none():
    return None
