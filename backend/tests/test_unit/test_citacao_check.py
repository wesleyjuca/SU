"""Fase 93 — extração e verificação de citações de legislação."""
import pytest

from app.services.citacao_check import extrair_referencias_lei, verificar_citacoes


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
    assert por_ref["9999/1999"]["status"] == "nao_encontrada"
    assert por_ref["1234/2000"]["status"] == "nao_verificavel"
