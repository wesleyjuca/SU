"""Fase 80 — conectores credenciados Escavador/Judit + parser compartilhado."""
import pytest

from app.integrations.fontes._partes import extrair_partes
from app.integrations.fontes.escavador_fonte import EscavadorFonte
from app.integrations.fontes.judit_fonte import JuditFonte
from app.integrations.fontes.base import Capability


# ─── parser compartilhado (PDPJ + Escavador shapes) ──────────────────────────
def test_extrai_partes_estilo_pdpj():
    dados = {
        "poloAtivo": [{"nome": "Autor X", "documento": "111",
                       "advogados": [{"nome": "Adv A", "numeroOab": "1", "ufOab": "CE"}]}],
        "poloPassivo": [{"nome": "Reu Y", "cpfCnpj": "222"}],
    }
    ps = {(p.tipo, p.nome, p.polo, p.oab) for p in extrair_partes(dados)}
    assert ("AUTOR", "Autor X", "ATIVO", None) in ps
    assert ("ADVOGADO", "Adv A", "ATIVO", "1/CE") in ps
    assert ("REU", "Reu Y", "PASSIVO", None) in ps


def test_extrai_partes_estilo_escavador_envolvidos():
    # Escavador: lista plana `envolvidos`, advogado como item próprio (tipo)
    dados = {"envolvidos": [
        {"nome": "Fulano", "tipo": "AUTOR", "polo": "ATIVO", "cpf": "123"},
        {"nome": "Empresa", "tipo": "REU", "polo": "PASSIVO"},
        {"nome": "Dra. Beltrana", "tipo": "ADVOGADO", "oab": "999", "uf": "SP"},
    ]}
    m = {p.nome: (p.tipo, p.polo, p.oab) for p in extrair_partes(dados)}
    assert m["Fulano"] == ("AUTOR", "ATIVO", None)
    assert m["Empresa"] == ("REU", "PASSIVO", None)
    # advogado como item plano sem polo → polo None
    assert m["Dra. Beltrana"] == ("ADVOGADO", None, "999/SP")


def test_extrai_partes_vazio():
    assert extrair_partes({}) == []
    assert extrair_partes({"envolvidos": [None, 1, {"semNome": 1}]}) == []


# ─── capabilities + gating sem token ─────────────────────────────────────────
def test_capabilities():
    assert EscavadorFonte("t").suporta(Capability.DESCOBRIR_OAB)
    assert EscavadorFonte("t").suporta(Capability.PARTES)
    assert JuditFonte("t").suporta(Capability.PARTES)
    assert not JuditFonte("t").suporta(Capability.DESCOBRIR_OAB)


@pytest.mark.asyncio
async def test_gating_sem_token():
    assert await EscavadorFonte("").partes("0001234-56.2026.8.06.0001") == []
    assert await EscavadorFonte("").descobrir_por_oab("123", "CE", None, None) == []
    assert await JuditFonte("").partes("0001234-56.2026.8.06.0001") == []
    assert await JuditFonte("tok").partes("sem-digitos") == []


# ─── ordem de fallback pdpj → escavador → judit ──────────────────────────────
@pytest.mark.asyncio
async def test_fallback_ordem(monkeypatch):
    from app.integrations.fontes import pdpj_fonte, escavador_fonte, judit_fonte
    from app.integrations.fontes.credenciadas import fonte_partes_credenciada

    chamadas = []
    async def _none(mod):
        chamadas.append(mod)
        return None

    # nenhuma conectada → None
    monkeypatch.setattr(pdpj_fonte, "para_tenant", lambda db, t: _none("pdpj"))
    monkeypatch.setattr(escavador_fonte, "para_tenant", lambda db, t: _none("escavador"))
    monkeypatch.setattr(judit_fonte, "para_tenant", lambda db, t: _none("judit"))
    assert await fonte_partes_credenciada(db=None, tenant_id="t") is None
    assert chamadas == ["pdpj", "escavador", "judit"]  # ordem respeitada

    # escavador conectado → vence antes de judit (e depois de pdpj falhar)
    async def _esc(db, t): return EscavadorFonte("tok")
    monkeypatch.setattr(escavador_fonte, "para_tenant", _esc)
    f = await fonte_partes_credenciada(db=None, tenant_id="t")
    assert isinstance(f, EscavadorFonte)
