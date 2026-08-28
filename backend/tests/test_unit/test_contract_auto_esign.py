"""Fase 192 — contrato aprovado dispara a assinatura eletrônica (Clicksign)
automaticamente quando dá pra fazer isso com segurança (cliente vinculado
com e-mail, Clicksign conectado). Fail-soft em todo o resto: qualquer
motivo pra não conseguir deixa o contrato "aprovado, aguardando envio
manual" — igual ao comportamento de antes desta fase — nunca bloqueia a
aprovação em si (invariante HITL do CLAUDE.md)."""
import uuid

import pytest

from app.services.approval import execute_approved_action


class _Doc:
    def __init__(self, tid, com_conteudo=True):
        self.id = uuid.uuid4()
        self.tenant_id = tid
        self.status = "RASCUNHO"
        self.conteudo_texto = "conteúdo do contrato" if com_conteudo else None
        self.conteudo_html = None


class _Con:
    def __init__(self, client_id=None):
        self.status = "RASCUNHO"
        self.client_id = client_id


class _Client:
    def __init__(self, email="cliente@exemplo.com", nome="Fulano Cliente"):
        self.email = email
        self.nome_completo = nome


class _Appr:
    def __init__(self, tid, doc_id, tipo="CONTRACT_REVIEW"):
        self.tipo = tipo
        self.tenant_id = tid
        self.ai_suggestion = {"document_id": doc_id}


class _FakeDB:
    def __init__(self, doc, con, client=None):
        self._doc = doc
        self._con = con
        self._client = client

    async def get(self, model, pk):
        from app.models.document import Document
        from app.models.client import Client
        if model is Document:
            return self._doc
        if model is Client:
            return self._client
        return None

    async def execute(self, stmt):
        con = self._con

        class _R:
            def scalar_one_or_none(self_inner):
                return con
        return _R()

    async def flush(self):
        pass


def _patch_integration(monkeypatch, conectado: bool):
    import app.services.integration_hub as ih_mod

    async def _fake_get_credentials(db, tenant_id, provider):
        return {"api_token": "tok"} if conectado else None

    monkeypatch.setattr(ih_mod, "get_credentials", _fake_get_credentials)


def _patch_esign_sucesso(monkeypatch):
    import app.services.esign as esign_mod

    async def _fake_enviar(db, tenant_id, doc, con, signatarios):
        con.status = "AGUARDANDO_ASSINATURA"
        return {"document_key": "dk_123", "signatarios": [{**s, "signer_key": "sk_123"} for s in signatarios]}

    monkeypatch.setattr(esign_mod, "enviar_para_assinatura", _fake_enviar)


def _patch_esign_falha(monkeypatch):
    import app.services.esign as esign_mod

    async def _fake_enviar_falha(db, tenant_id, doc, con, signatarios):
        raise RuntimeError("Clicksign inalcançável")

    monkeypatch.setattr(esign_mod, "enviar_para_assinatura", _fake_enviar_falha)


@pytest.mark.asyncio
async def test_dispara_assinatura_automatica_quando_cliente_tem_email_e_clicksign_conectado(monkeypatch):
    tid = uuid.uuid4()
    client_id = uuid.uuid4()
    doc = _Doc(tid)
    con = _Con(client_id=client_id)
    client = _Client(email="cliente@exemplo.com")

    _patch_integration(monkeypatch, conectado=True)
    _patch_esign_sucesso(monkeypatch)

    result = await execute_approved_action(_FakeDB(doc, con, client), _Appr(tid, str(doc.id)))

    assert result["auto_enviado_assinatura"] is True
    assert "cliente@exemplo.com" in result["note"]
    assert con.status == "AGUARDANDO_ASSINATURA"


@pytest.mark.asyncio
async def test_sem_cliente_vinculado_nao_tenta_envio_automatico(monkeypatch):
    tid = uuid.uuid4()
    doc = _Doc(tid)
    con = _Con(client_id=None)  # contrato sem cliente vinculado

    async def _explode(*a, **kw):
        raise AssertionError("get_credentials não deveria ser chamado sem client_id")
    import app.services.integration_hub as ih_mod
    monkeypatch.setattr(ih_mod, "get_credentials", _explode)

    result = await execute_approved_action(_FakeDB(doc, con), _Appr(tid, str(doc.id)))

    assert result["auto_enviado_assinatura"] is False
    assert con.status == "APROVADO"  # nunca bloqueia a aprovação em si


@pytest.mark.asyncio
async def test_cliente_sem_email_fail_soft(monkeypatch):
    tid = uuid.uuid4()
    client_id = uuid.uuid4()
    doc = _Doc(tid)
    con = _Con(client_id=client_id)
    client = _Client(email=None)

    _patch_integration(monkeypatch, conectado=True)

    result = await execute_approved_action(_FakeDB(doc, con, client), _Appr(tid, str(doc.id)))

    assert result["auto_enviado_assinatura"] is False
    assert "e-mail" in result["note"]
    assert con.status == "APROVADO"


@pytest.mark.asyncio
async def test_clicksign_nao_conectado_fail_soft(monkeypatch):
    tid = uuid.uuid4()
    client_id = uuid.uuid4()
    doc = _Doc(tid)
    con = _Con(client_id=client_id)
    client = _Client()

    _patch_integration(monkeypatch, conectado=False)

    result = await execute_approved_action(_FakeDB(doc, con, client), _Appr(tid, str(doc.id)))

    assert result["auto_enviado_assinatura"] is False
    assert "Clicksign" in result["note"]
    assert con.status == "APROVADO"


@pytest.mark.asyncio
async def test_falha_no_envio_nunca_propaga_nem_bloqueia_aprovacao(monkeypatch):
    tid = uuid.uuid4()
    client_id = uuid.uuid4()
    doc = _Doc(tid)
    con = _Con(client_id=client_id)
    client = _Client()

    _patch_integration(monkeypatch, conectado=True)
    _patch_esign_falha(monkeypatch)

    result = await execute_approved_action(_FakeDB(doc, con, client), _Appr(tid, str(doc.id)))

    assert result["auto_enviado_assinatura"] is False
    assert result["executed"] == "contract_approved"
    assert doc.status == "APROVADO"
    assert con.status == "APROVADO"  # não mudou pra AGUARDANDO_ASSINATURA


@pytest.mark.asyncio
async def test_contrato_sem_conteudo_fail_soft(monkeypatch):
    tid = uuid.uuid4()
    client_id = uuid.uuid4()
    doc = _Doc(tid, com_conteudo=False)
    con = _Con(client_id=client_id)
    client = _Client()

    _patch_integration(monkeypatch, conectado=True)

    result = await execute_approved_action(_FakeDB(doc, con, client), _Appr(tid, str(doc.id)))

    assert result["auto_enviado_assinatura"] is False
    assert "conteúdo" in result["note"]
