"""Fase 140.1 — resolve_system_prompt() fail-soft, CRUD de prompt/anexos dos
agentes nativos (SUPERADMIN), versionamento (snapshot do valor ANTERIOR)."""
import datetime
import uuid

import pytest
from fastapi import HTTPException

from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.prompt_registry import AGENT_PROMPT_SLOTS, resolve_default_prompt
from app.api.v1.agent_prompts import (
    get_prompt_slots, get_agent_prompt, update_agent_prompt, list_prompt_versions,
    list_attachments, upload_attachment, delete_attachment,
    PromptUpdateRequest,
)


class _FakeUser:
    def __init__(self, id="u1", role="SUPERADMIN"):
        self.id = id
        self.role = role


class _FakeScalars:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _FakeResult:
    def __init__(self, items=None, scalar=None):
        self._items = items or []
        self._scalar = scalar

    def scalars(self):
        return _FakeScalars(self._items)

    def scalar_one_or_none(self):
        return self._scalar


class _FakeDB:
    def __init__(self, execute_results=None, raise_on_execute=False):
        self._results = list(execute_results or [])
        self._raise = raise_on_execute
        self.added = []
        self.deleted = []
        self.flushed = False

    async def execute(self, query):
        if self._raise:
            raise RuntimeError("db indisponível (simulado)")
        if self._results:
            return self._results.pop(0)
        return _FakeResult()

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def flush(self):
        for obj in self.added:
            if getattr(obj, "created_at", "unset") is None:
                obj.created_at = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
            if getattr(obj, "updated_at", "unset") is None:
                obj.updated_at = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()
        self.flushed = True


class _FakeConfig:
    def __init__(self, prompt_text=None, versao=1, updated_by=None):
        self.id = uuid.uuid4()
        self.agent_name = "petition_agent"
        self.prompt_slot = "primary"
        self.prompt_text = prompt_text
        self.versao = versao
        self.updated_by = updated_by
        self.created_at = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
        self.updated_at = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)


class _EchoAgent(BaseAgent):
    """Agente mínimo só pra exercitar resolve_system_prompt()."""
    name = "petition_agent"
    description = "teste"

    async def execute(self, ctx):
        return AgentResult(status=AgentStatus.SUCCESS, agent_name=self.name, output={})


# ─── resolve_system_prompt() — fail-soft ────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_system_prompt_sem_db_retorna_default():
    agent = _EchoAgent(db=None)
    assert await agent.resolve_system_prompt("DEFAULT") == "DEFAULT"


@pytest.mark.asyncio
async def test_resolve_system_prompt_sem_row_retorna_default():
    db = _FakeDB(execute_results=[_FakeResult(scalar=None), _FakeResult(items=[])])
    agent = _EchoAgent(db=db)
    assert await agent.resolve_system_prompt("DEFAULT") == "DEFAULT"


@pytest.mark.asyncio
async def test_resolve_system_prompt_com_override_retorna_override():
    db = _FakeDB(execute_results=[_FakeResult(scalar="CUSTOM"), _FakeResult(items=[])])
    agent = _EchoAgent(db=db)
    assert await agent.resolve_system_prompt("DEFAULT") == "CUSTOM"


@pytest.mark.asyncio
async def test_resolve_system_prompt_erro_de_db_retorna_default():
    db = _FakeDB(raise_on_execute=True)
    agent = _EchoAgent(db=db)
    assert await agent.resolve_system_prompt("DEFAULT") == "DEFAULT"


@pytest.mark.asyncio
async def test_resolve_system_prompt_concatena_anexos():
    db = _FakeDB(execute_results=[_FakeResult(scalar=None), _FakeResult(items=["contexto extra do anexo"])])
    agent = _EchoAgent(db=db)
    resultado = await agent.resolve_system_prompt("DEFAULT")
    assert resultado.startswith("DEFAULT")
    assert "contexto extra do anexo" in resultado


# ─── Endpoints — validação de agente/slot ──────────────────────────────────

@pytest.mark.asyncio
async def test_get_prompt_slots_agente_desconhecido_404():
    with pytest.raises(HTTPException) as exc_info:
        await get_prompt_slots("agente_inexistente", current_user=_FakeUser())
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_prompt_slots_agente_sem_llm_lista_vazia():
    resp = await get_prompt_slots("orchestration_agent", current_user=_FakeUser())
    assert resp["slots"] == []


@pytest.mark.asyncio
async def test_get_agent_prompt_slot_invalido_404():
    with pytest.raises(HTTPException) as exc_info:
        await get_agent_prompt("crm_agent", slot="primary", current_user=_FakeUser(), db=_FakeDB())
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_agent_prompt_sem_row_devolve_prompt_none():
    db = _FakeDB(execute_results=[_FakeResult(scalar=None)])
    resp = await get_agent_prompt("petition_agent", slot="primary", current_user=_FakeUser(), db=db)
    assert resp.prompt_text is None
    assert resp.versao == 0


# ─── PUT — versionamento (snapshot do valor ANTERIOR) ──────────────────────

@pytest.mark.asyncio
async def test_update_agent_prompt_grava_snapshot_do_valor_anterior():
    config = _FakeConfig(prompt_text="prompt original", versao=1)
    db = _FakeDB(execute_results=[_FakeResult(scalar=config)])
    resp = await update_agent_prompt(
        "petition_agent",
        PromptUpdateRequest(prompt_text="prompt novo", change_summary="melhorei o tom"),
        slot="primary",
        current_user=_FakeUser(id="admin-1"),
        db=db,
    )
    assert resp.prompt_text == "prompt novo"
    assert resp.versao == 2
    # snapshot gravado é do valor ANTERIOR (original), não do novo
    versoes = [o for o in db.added if type(o).__name__ == "AgentPromptVersion"]
    assert len(versoes) == 1
    assert versoes[0].prompt_text == "prompt original"
    assert versoes[0].versao == 1
    assert config.prompt_text == "prompt novo"


@pytest.mark.asyncio
async def test_update_agent_prompt_cria_config_quando_nao_existe():
    db = _FakeDB(execute_results=[_FakeResult(scalar=None)])
    resp = await update_agent_prompt(
        "petition_agent",
        PromptUpdateRequest(prompt_text="primeiro prompt"),
        slot="primary",
        current_user=_FakeUser(),
        db=db,
    )
    assert resp.prompt_text == "primeiro prompt"
    assert resp.versao == 2  # 1 (criação) + 1 (update)


@pytest.mark.asyncio
async def test_update_agent_prompt_restaurar_padrao_grava_none():
    config = _FakeConfig(prompt_text="algo customizado", versao=3)
    db = _FakeDB(execute_results=[_FakeResult(scalar=config)])
    resp = await update_agent_prompt(
        "petition_agent", PromptUpdateRequest(prompt_text=None),
        slot="primary", current_user=_FakeUser(), db=db,
    )
    assert resp.prompt_text is None
    assert config.prompt_text is None


# ─── Histórico de versões ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_prompt_versions_sem_config_retorna_vazio():
    db = _FakeDB(execute_results=[_FakeResult(scalar=None)])
    resp = await list_prompt_versions("petition_agent", slot="primary", current_user=_FakeUser(), db=db)
    assert resp == []


# ─── Anexos ─────────────────────────────────────────────────────────────────

class _FakeUploadFile:
    def __init__(self, filename, content_type, content: bytes):
        self.filename = filename
        self.content_type = content_type
        self._content = content

    async def read(self):
        return self._content


@pytest.mark.asyncio
async def test_upload_attachment_texto_extrai_conteudo():
    db = _FakeDB()
    file = _FakeUploadFile("notas.txt", "text/plain", b"contexto adicional do agente")
    resp = await upload_attachment("petition_agent", file=file, current_user=_FakeUser(), db=db)
    assert resp.filename == "notas.txt"
    assert resp.has_extracted_text is True
    anexo = db.added[0]
    assert anexo.extracted_text == "contexto adicional do agente"


@pytest.mark.asyncio
async def test_upload_attachment_pdf_sem_extracao():
    db = _FakeDB()
    file = _FakeUploadFile("peca.pdf", "application/pdf", b"%PDF-1.4 conteudo binario simulado")
    resp = await upload_attachment("petition_agent", file=file, current_user=_FakeUser(), db=db)
    assert resp.has_extracted_text is False


@pytest.mark.asyncio
async def test_upload_attachment_arquivo_vazio_400():
    db = _FakeDB()
    file = _FakeUploadFile("vazio.txt", "text/plain", b"")
    with pytest.raises(HTTPException) as exc_info:
        await upload_attachment("petition_agent", file=file, current_user=_FakeUser(), db=db)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_attachment_muito_grande_400():
    db = _FakeDB()
    file = _FakeUploadFile("grande.txt", "text/plain", b"x" * (10 * 1024 * 1024 + 1))
    with pytest.raises(HTTPException) as exc_info:
        await upload_attachment("petition_agent", file=file, current_user=_FakeUser(), db=db)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_attachment_com_s3_configurado_usa_storage_key_sem_base64(monkeypatch):
    """Fase 190 — com object storage configurado, o binário vai pro S3
    (storage_key setado) e `data_url` fica None, em vez do caminho legado
    de base64 inline em Text."""
    from app.api.v1 import agent_prompts as mod

    async def _fake_is_configured():
        return True

    async def _fake_upload_bytes(tenant_id, document_id, filename, content_type, data):
        assert tenant_id == "agents"
        return f"documents/agents/{document_id}/{filename}"

    monkeypatch.setattr(mod.object_storage, "is_configured", lambda: True)
    monkeypatch.setattr(mod.object_storage, "upload_bytes", _fake_upload_bytes)

    db = _FakeDB()
    file = _FakeUploadFile("contrato.pdf", "application/pdf", b"conteudo binario do anexo")
    resp = await upload_attachment("petition_agent", file=file, current_user=_FakeUser(), db=db)

    anexo = db.added[0]
    assert anexo.data_url is None
    assert anexo.storage_key is not None
    assert anexo.storage_key.startswith("documents/agents/")
    assert resp.filename == "contrato.pdf"


@pytest.mark.asyncio
async def test_upload_attachment_falha_no_s3_devolve_502(monkeypatch):
    from app.api.v1 import agent_prompts as mod

    async def _fake_upload_bytes_falha(**kwargs):
        raise mod.object_storage.ObjectStorageError("falha simulada")

    monkeypatch.setattr(mod.object_storage, "is_configured", lambda: True)
    monkeypatch.setattr(mod.object_storage, "upload_bytes", _fake_upload_bytes_falha)

    db = _FakeDB()
    file = _FakeUploadFile("contrato.pdf", "application/pdf", b"conteudo binario do anexo")
    with pytest.raises(HTTPException) as exc_info:
        await upload_attachment("petition_agent", file=file, current_user=_FakeUser(), db=db)
    assert exc_info.value.status_code == 502
    assert db.added == []


@pytest.mark.asyncio
async def test_list_attachments_agente_desconhecido_404():
    with pytest.raises(HTTPException) as exc_info:
        await list_attachments("agente_inexistente", current_user=_FakeUser(), db=_FakeDB())
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_attachment_inexistente_404():
    db = _FakeDB(execute_results=[_FakeResult(scalar=None)])
    with pytest.raises(HTTPException) as exc_info:
        await delete_attachment("petition_agent", str(uuid.uuid4()), current_user=_FakeUser(), db=db)
    assert exc_info.value.status_code == 404


# ─── Registro cobre exatamente os 19 agentes ───────────────────────────────

def test_agent_prompt_slots_cobre_os_19_agentes():
    assert len(AGENT_PROMPT_SLOTS) == 19


@pytest.mark.asyncio
async def test_require_role_superadmin_bloqueia_admin_comum():
    from app.dependencies import require_role
    from app.core.exceptions import ForbiddenError

    checker = require_role("SUPERADMIN")
    with pytest.raises(ForbiddenError):
        await checker(current_user=_FakeUser(role="ADMIN"))


@pytest.mark.asyncio
async def test_require_role_superadmin_passa_pro_superadmin():
    from app.dependencies import require_role

    checker = require_role("SUPERADMIN")
    user = _FakeUser(role="SUPERADMIN")
    assert await checker(current_user=user) is user


# ─── Fase 140.1.1 — expor o prompt padrão (default_text) ───────────────────

def test_resolve_default_prompt_caminho_valido():
    texto = resolve_default_prompt("app.agents.petition.petition_agent.PETITION_SYSTEM_PROMPT")
    assert texto is not None
    assert "PETIÇÕES" in texto or "petição" in texto.lower()


def test_resolve_default_prompt_modulo_inexistente_retorna_none():
    assert resolve_default_prompt("app.agents.inexistente.modulo_fake.CONST") is None


def test_resolve_default_prompt_constante_inexistente_retorna_none():
    assert resolve_default_prompt("app.agents.petition.petition_agent.CONST_QUE_NAO_EXISTE") is None


def test_resolve_default_prompt_sem_ponto_retorna_none():
    assert resolve_default_prompt("nada_com_ponto") is None


def test_resolve_default_prompt_todos_os_12_agentes_com_llm_resolvem():
    for name, slots in AGENT_PROMPT_SLOTS.items():
        for slot in slots:
            default_ref = slot.get("default_ref")
            assert default_ref, f"{name}/{slot['slot']} deveria ter default_ref (agente com LLM)"
            texto = resolve_default_prompt(default_ref)
            assert texto and len(texto) > 0, f"{name}/{slot['slot']} ({default_ref}) não resolveu"


@pytest.mark.asyncio
async def test_get_agent_prompt_sem_override_devolve_default_text():
    db = _FakeDB(execute_results=[_FakeResult(scalar=None)])
    resp = await get_agent_prompt("petition_agent", slot="primary", current_user=_FakeUser(), db=db)
    assert resp.prompt_text is None
    assert resp.default_text is not None
    assert "PETIÇÕES" in resp.default_text or "petição" in resp.default_text.lower()


@pytest.mark.asyncio
async def test_get_agent_prompt_com_override_ainda_devolve_default_text():
    config = _FakeConfig(prompt_text="override customizado", versao=2)
    db = _FakeDB(execute_results=[_FakeResult(scalar=config)])
    resp = await get_agent_prompt("petition_agent", slot="primary", current_user=_FakeUser(), db=db)
    assert resp.prompt_text == "override customizado"
    assert resp.default_text is not None  # default continua visível mesmo com override ativo


def test_agent_prompt_slots_7_agentes_sem_llm():
    sem_llm = [name for name, slots in AGENT_PROMPT_SLOTS.items() if not slots]
    assert sorted(sem_llm) == sorted([
        "orchestration_agent", "court_monitor_agent", "financial_agent",
        "audit_agent", "analytics_agent", "ocr_agent", "publication_monitor_agent",
    ])
