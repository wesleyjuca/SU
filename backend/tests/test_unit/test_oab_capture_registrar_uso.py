"""Fase 165 — `_enriquecer_partes()` (captura por OAB) passa a registrar uso
real da fonte de partes credenciada (PDPJ/Escavador/Judit/Jusbrasil): sucesso
se alguma parte nova foi importada, falha só se `fonte.partes()` de fato
lançou (resposta vazia sem exceção não é necessariamente erro — o processo
pode legitimamente não ter partes cadastradas ainda)."""
import asyncio
import sys
import types


def setup_module(module):
    if "cryptography" in sys.modules:
        return
    fake_crypto = types.ModuleType("cryptography")
    fake_fernet_mod = types.ModuleType("cryptography.fernet")

    class InvalidToken(Exception):
        pass

    class Fernet:
        def __init__(self, key):
            self.key = key

        @staticmethod
        def generate_key():
            return b"0" * 32

        def encrypt(self, data):
            return b"ENC:" + data

        def decrypt(self, token):
            if not token.startswith(b"ENC:"):
                raise InvalidToken()
            return token[4:]

    fake_fernet_mod.Fernet = Fernet
    fake_fernet_mod.InvalidToken = InvalidToken
    fake_crypto.fernet = fake_fernet_mod
    sys.modules["cryptography"] = fake_crypto
    sys.modules["cryptography.fernet"] = fake_fernet_mod


class _FakeFonte:
    nome = "pdpj"

    def __init__(self, respostas):
        self._respostas = list(respostas)

    async def partes(self, numero_cnj, tribunal):
        resp = self._respostas.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


class _FakeProc:
    def __init__(self, numero_cnj):
        self.numero_cnj = numero_cnj
        self.id = numero_cnj


def _patch_credenciadas(monkeypatch, fonte):
    import app.integrations.fontes.credenciadas as credenciadas_mod

    async def _fake(db, tenant_id):
        return fonte

    monkeypatch.setattr(credenciadas_mod, "fonte_partes_credenciada", _fake)


def test_partes_importadas_com_sucesso_registra_sucesso(monkeypatch):
    from app.services import oab_capture
    from app.services import integration_hub

    fonte = _FakeFonte(respostas=[[{"nome": "Fulano", "tipo": "AUTOR"}]])
    _patch_credenciadas(monkeypatch, fonte)

    chamadas = []

    async def _fake_registrar_uso(db, tenant_id, provider, sucesso, detalhe=None):
        chamadas.append({"provider": provider, "sucesso": sucesso})

    async def _fake_importar_partes(db, proc, partes):
        return {"novas": 1, "total": 1}

    monkeypatch.setattr(integration_hub, "registrar_uso", _fake_registrar_uso)
    import app.services.partes_import as partes_import_mod
    monkeypatch.setattr(partes_import_mod, "importar_partes", _fake_importar_partes)

    procs = [(_FakeProc("0001"), "TJSP")]
    total = asyncio.run(oab_capture._enriquecer_partes(None, "t1", procs))

    assert total == 1
    assert chamadas == [{"provider": "pdpj", "sucesso": True}]


def test_excecao_sem_nenhuma_parte_importada_registra_falha(monkeypatch):
    from app.services import oab_capture
    from app.services import integration_hub

    fonte = _FakeFonte(respostas=[RuntimeError("401 token expirado")])
    _patch_credenciadas(monkeypatch, fonte)

    chamadas = []

    async def _fake_registrar_uso(db, tenant_id, provider, sucesso, detalhe=None):
        chamadas.append({"sucesso": sucesso, "detalhe": detalhe})

    monkeypatch.setattr(integration_hub, "registrar_uso", _fake_registrar_uso)

    procs = [(_FakeProc("0001"), "TJSP")]
    total = asyncio.run(oab_capture._enriquecer_partes(None, "t1", procs))

    assert total == 0
    assert chamadas == [{"sucesso": False, "detalhe": "401 token expirado"}]


def test_resposta_vazia_sem_excecao_nao_registra_nada(monkeypatch):
    """Ambíguo (pode ser processo sem partes cadastradas) — não deve marcar
    ERRO nem CONECTADA à toa."""
    from app.services import oab_capture
    from app.services import integration_hub

    fonte = _FakeFonte(respostas=[[]])
    _patch_credenciadas(monkeypatch, fonte)

    chamado = {"registrar_uso": False}

    async def _fake_registrar_uso(*a, **kw):
        chamado["registrar_uso"] = True

    monkeypatch.setattr(integration_hub, "registrar_uso", _fake_registrar_uso)

    procs = [(_FakeProc("0001"), "TJSP")]
    total = asyncio.run(oab_capture._enriquecer_partes(None, "t1", procs))

    assert total == 0
    assert chamado["registrar_uso"] is False
