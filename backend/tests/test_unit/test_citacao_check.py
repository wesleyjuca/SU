"""Fases 93/126 — extração e verificação de citações de legislação e processo."""
import pytest

from app.services.citacao_check import (
    extrair_referencias_lei,
    extrair_referencias_processo,
    verificar_citacoes,
)


def test_extrai_referencia_simples():
    assert extrair_referencias_lei("Nos termos da Lei nº 8.078/1990...") == ["8078/1990"]


def test_extrai_varias_grafias():
    texto = "Lei 8.078/1990... na forma da Lei Complementar nº 123, 2006 e do art. 5 da Lei n. 13.105/2015."
    refs = extrair_referencias_lei(texto)
    assert "8078/1990" in refs
    assert "123/2006" in refs
    assert "13105/2015" in refs


def test_ano_com_2_digitos_nao_e_capturado_limitacao_conhecida():
    # Limitação conhecida desta fatia inicial (regex, não NLP): só reconhece
    # ano com 4 dígitos. "Lei 8.078/90" não é extraída — anotado como
    # "fora de escopo" no plano (extração mais robusta fica pra fase futura).
    assert extrair_referencias_lei("Lei 8.078/90") == []


def test_dedup_mantem_ordem_primeira_ocorrencia():
    texto = "Lei 8.078/1990 ... Lei 8.078/1990 ... Lei 10.406/2002"
    assert extrair_referencias_lei(texto) == ["8078/1990", "10406/2002"]


def test_numero_com_milhar_normaliza_sem_ponto():
    assert extrair_referencias_lei("Lei nº 13.105/2015") == ["13105/2015"]


def test_texto_sem_citacao_retorna_vazio():
    assert extrair_referencias_lei("Texto qualquer sem nenhuma referência legal.") == []
    assert extrair_referencias_lei("") == []


@pytest.mark.asyncio
async def test_verificar_citacoes_texto_sem_lei_nao_chama_lexml():
    assert await verificar_citacoes("nada aqui") == []


@pytest.mark.asyncio
async def test_verificar_citacoes_mistura_status(monkeypatch):
    import app.integrations.lexml.client as lexml_client

    async def _fake_buscar_lei(ref):
        if ref == "8078/1990":
            return {"encontrado": True, "titulo": "CDC", "urn": "urn:x"}
        if ref == "9999/1999":
            return {"encontrado": False, "titulo": None, "urn": None}
        raise RuntimeError("timeout")

    monkeypatch.setattr(lexml_client, "buscar_lei", _fake_buscar_lei)

    texto = "Lei nº 8.078/1990, Lei nº 9.999/1999 e Lei nº 1.234/2000."
    resultado = await verificar_citacoes(texto)

    por_ref = {c["referencia"]: c for c in resultado}
    assert por_ref["8078/1990"]["status"] == "confirmada"
    assert por_ref["8078/1990"]["titulo"] == "CDC"
    assert por_ref["8078/1990"]["tipo"] == "LEI"
    assert por_ref["9999/1999"]["status"] == "nao_encontrada"
    assert por_ref["1234/2000"]["status"] == "nao_verificavel"


# ─── Fase 126 — citações de PROCESSO (CNJ) via DataJud ─────────────────────


def test_extrai_numero_processo_cnj_formato_valido():
    texto = "Nos autos do processo 0001234-56.2023.8.06.0001, requer-se..."
    assert extrair_referencias_processo(texto) == ["0001234-56.2023.8.06.0001"]


def test_extrai_processo_dedup_mantem_ordem():
    texto = (
        "0001234-56.2023.8.06.0001 ... 0001234-56.2023.8.06.0001 ... "
        "0007654-32.2022.8.06.0001"
    )
    assert extrair_referencias_processo(texto) == [
        "0001234-56.2023.8.06.0001",
        "0007654-32.2022.8.06.0001",
    ]


def test_extrai_processo_formato_invalido_nao_captura():
    assert extrair_referencias_processo("processo nº 1234-56.2023.8.06.0001") == []
    assert extrair_referencias_processo("") == []


@pytest.mark.asyncio
async def test_verificar_citacoes_processo_sem_tribunal_nao_chama_datajud(monkeypatch):
    """Sem tribunal, DataJudFonte._client() cairia num fallback silencioso pra
    TJCE — melhor não verificar do que verificar no tribunal errado."""
    import app.integrations.fontes.registry as registry_mod

    chamado = False

    def _fake_obter_fonte(nome):
        nonlocal chamado
        chamado = True
        raise AssertionError("não deveria chamar obter_fonte sem tribunal")

    monkeypatch.setattr(registry_mod, "obter_fonte", _fake_obter_fonte)

    texto = "Processo 0001234-56.2023.8.06.0001 em trâmite."
    resultado = await verificar_citacoes(texto, tribunal=None)

    assert not chamado
    assert len(resultado) == 1
    assert resultado[0]["tipo"] == "PROCESSO"
    assert resultado[0]["status"] == "nao_verificavel"


@pytest.mark.asyncio
async def test_verificar_citacoes_processo_com_tribunal_confirmada_e_nao_verificavel(monkeypatch):
    import app.services.citacao_check as citacao_check_mod

    class _FakeFonte:
        async def detalhar(self, numero_cnj, tribunal):
            if numero_cnj == "0001234-56.2023.8.06.0001":
                return {"classe": "Procedimento Comum Cível", "tribunal": tribunal}
            return None  # não encontrado OU falha — mesmo contrato de fetch_processo

    async def _fake_obter_fonte(nome):
        return _FakeFonte()

    import app.integrations.fontes.registry as registry_mod
    monkeypatch.setattr(registry_mod, "obter_fonte", lambda nome: _FakeFonte())

    texto = (
        "Processo 0001234-56.2023.8.06.0001 e também o "
        "0007654-32.2022.8.06.0001."
    )
    resultado = await citacao_check_mod.verificar_citacoes(texto, tribunal="TJCE")

    por_ref = {c["referencia"]: c for c in resultado}
    assert por_ref["0001234-56.2023.8.06.0001"]["status"] == "confirmada"
    assert por_ref["0001234-56.2023.8.06.0001"]["titulo"] == "Procedimento Comum Cível"
    assert por_ref["0007654-32.2022.8.06.0001"]["status"] == "nao_verificavel"


@pytest.mark.asyncio
async def test_verificar_citacoes_mistura_lei_e_processo(monkeypatch):
    import app.integrations.lexml.client as lexml_client

    async def _fake_buscar_lei(ref):
        return {"encontrado": True, "titulo": "CDC", "urn": "urn:x"}

    monkeypatch.setattr(lexml_client, "buscar_lei", _fake_buscar_lei)

    class _FakeFonte:
        async def detalhar(self, numero_cnj, tribunal):
            return {"classe": "Execução Fiscal", "tribunal": tribunal}

    import app.integrations.fontes.registry as registry_mod
    monkeypatch.setattr(registry_mod, "obter_fonte", lambda nome: _FakeFonte())

    texto = "Lei nº 8.078/1990 aplicada ao processo 0001234-56.2023.8.06.0001."
    resultado = await verificar_citacoes(texto, tribunal="TJCE")

    tipos = {c["tipo"] for c in resultado}
    assert tipos == {"LEI", "PROCESSO"}
    assert len(resultado) == 2
