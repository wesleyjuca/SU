"""Fase pós-262 — achado real (usuário reportou "busca por OAB/UF não
funciona"): `capturar_por_oab` só consultava o Comunica público, mesmo já
existindo 2 fontes credenciadas (Escavador/Judit) com suporte oficial a
descoberta por OAB. Confirma que, quando configuradas, elas contribuem com
achados que o Comunica sozinho não teria (mesclados, sem duplicar), e que
`fontes_utilizadas` reflete corretamente quem achou o quê."""
import uuid

import pytest

from app.integrations.fontes.base import ProcessoDescoberto


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def all(self):
        return self._value if self._value is not None else []


class _FakeDB:
    def __init__(self, queue):
        self._queue = list(queue)

    async def execute(self, query):
        return self._queue.pop(0)

    def add(self, obj):
        pass

    async def flush(self):
        pass

    async def commit(self):
        pass


class _FakeFonteComunicaVazia:
    """Simula o cenário relatado: o Comunica público não acha nada (WAF/
    fonte fora do ar) — sem fonte alternativa, a captura terminaria em 0."""
    async def descobrir_por_oab(self, numero, uf, inicio, hoje, max_paginas=20, stats=None):
        if stats is not None:
            stats["itens"] = 0
            stats["ok"] = False
            stats["error"] = "HTTP 403 da Comunica/DJEN em todos os perfis testados contra o WAF"
        return []


class _FakeFonteCredenciada:
    def __init__(self, nome, cnjs):
        self.nome = nome
        self._cnjs = cnjs

    async def descobrir_por_oab(self, numero, uf, inicio, hoje, **kwargs):
        return [ProcessoDescoberto(numero_cnj=cnj, tribunal="TJSP", uf=uf, fonte=self.nome, raw={})
                for cnj in self._cnjs]


async def _ok():
    return None


async def _ok_partes():
    return {"total": 0, "fonte_configurada": False}


async def _fake_iniciar_sync(db, t_id, fonte, tipo):
    return object()


async def _fake_finalizar_sync(db, run, status, stats):
    return None


@pytest.mark.asyncio
async def test_fonte_credenciada_acha_processo_que_comunica_nao_achou(monkeypatch):
    import app.services.oab_capture as mod

    tenant_id = uuid.uuid4()

    async def _com_escavador(db, t):
        return [_FakeFonteCredenciada("escavador", ["00098765420268260100"])]

    monkeypatch.setattr("app.services.movements_import.iniciar_sync", _fake_iniciar_sync)
    monkeypatch.setattr("app.services.movements_import.finalizar_sync", _fake_finalizar_sync)
    monkeypatch.setattr("app.integrations.fontes.registry.obter_fonte", lambda nome: _FakeFonteComunicaVazia())
    monkeypatch.setattr("app.integrations.fontes.credenciadas.fontes_descoberta_credenciadas",
                        _com_escavador)
    monkeypatch.setattr(mod, "_enriquecer_via_datajud", lambda db, novos: _ok())
    monkeypatch.setattr(mod, "_enriquecer_partes", lambda db, tenant_id, novos: _ok_partes())

    db = _FakeDB([_FakeScalarResult([]), _FakeScalarResult([])])
    resultado = await mod.capturar_por_oab(db, tenant_id, apenas_oab=("12345", "SP"))

    assert resultado["processos_criados"] == 1
    assert resultado["fontes_utilizadas"] == ["escavador"]
    # Achado real: sem a fonte alternativa, isso seria 0 (fonte_respondeu
    # False, mesmo comportamento do sintoma relatado pelo usuário).
    assert resultado["fonte_respondeu"] is False


@pytest.mark.asyncio
async def test_mesmo_cnj_de_2_fontes_nao_duplica(monkeypatch):
    import app.services.oab_capture as mod

    tenant_id = uuid.uuid4()
    cnj = "00012345620268260100"

    class _FakeFonteComunicaComAchado:
        async def descobrir_por_oab(self, numero, uf, inicio, hoje, max_paginas=20, stats=None):
            if stats is not None:
                stats["itens"] = 1
                stats["ok"] = True
            return [ProcessoDescoberto(numero_cnj=cnj, tribunal="TJSP", uf=uf, fonte="comunica", raw={})]

    async def _com_escavador_mesmo_cnj(db, t):
        return [_FakeFonteCredenciada("escavador", [cnj])]

    monkeypatch.setattr("app.services.movements_import.iniciar_sync", _fake_iniciar_sync)
    monkeypatch.setattr("app.services.movements_import.finalizar_sync", _fake_finalizar_sync)
    monkeypatch.setattr("app.integrations.fontes.registry.obter_fonte",
                        lambda nome: _FakeFonteComunicaComAchado())
    monkeypatch.setattr("app.integrations.fontes.credenciadas.fontes_descoberta_credenciadas",
                        _com_escavador_mesmo_cnj)
    monkeypatch.setattr(mod, "_enriquecer_via_datajud", lambda db, novos: _ok())
    monkeypatch.setattr(mod, "_enriquecer_partes", lambda db, tenant_id, novos: _ok_partes())

    db = _FakeDB([_FakeScalarResult([]), _FakeScalarResult([])])
    resultado = await mod.capturar_por_oab(db, tenant_id, apenas_oab=("12345", "SP"))

    assert resultado["processos_criados"] == 1  # não duplicou
    assert resultado["fontes_utilizadas"] == ["comunica", "escavador"]
