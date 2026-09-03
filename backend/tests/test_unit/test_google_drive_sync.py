"""Fase 167 — `google_drive_sync.py` tem loop ANINHADO (por tenant → por
arquivo). Uma exceção no meio dos arquivos de UM tenant não pode: (a)
deixar o SyncRun daquele tenant preso em RUNNING, nem (b) abortar a
sincronização dos DEMAIS tenants — o próprio docstring do módulo já
promete fail-soft por tenant ("um tenant sem token válido é pulado sem
derrubar os demais"), então o fix aqui usa `continue` pro próximo tenant
em vez de re-lançar (diferente do padrão usado em jurisprudencia_sync.py/
legislacao_sync.py, que são fontes globais sem esse conceito)."""
import uuid

import pytest


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _RaiseNoExecute:
    def __init__(self, exc):
        self.exc = exc


class _FakeDB:
    def __init__(self, queue):
        self._queue = list(queue)
        self.commits = 0

    async def execute(self, query):
        item = self._queue.pop(0)
        if isinstance(item, _RaiseNoExecute):
            raise item.exc
        return item

    def add(self, obj):
        pass

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1


class _FakeInteg:
    def __init__(self, tenant_id, folder_id):
        self.tenant_id = tenant_id
        self.extra_data = {"folder_id": folder_id}


class _FakeCfg:
    def __init__(self):
        self.modules_enabled = {"google_drive_doutrina": True}


@pytest.mark.asyncio
async def test_falha_no_meio_dos_arquivos_de_um_tenant_nao_aborta_os_demais(monkeypatch):
    import app.workers.tasks.google_drive_sync as mod

    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    integ_a = _FakeInteg(tenant_a, "folder_a")
    integ_b = _FakeInteg(tenant_b, "folder_b")

    chamadas_finalizar = []

    async def _fake_iniciar_sync(db, tenant_id, fonte, tipo):
        return type("Run", (), {"tenant_id": tenant_id})()

    async def _fake_finalizar_sync(db, run, status, stats):
        chamadas_finalizar.append((run.tenant_id, status, stats))

    monkeypatch.setattr("app.services.movements_import.iniciar_sync", _fake_iniciar_sync)
    monkeypatch.setattr("app.services.movements_import.finalizar_sync", _fake_finalizar_sync)

    async def _fake_get_credentials(db, tenant_id, provider):
        return {"access_token": "tok"}

    monkeypatch.setattr("app.services.integration_hub.get_credentials", _fake_get_credentials)

    async def _fake_listar_arquivos(access_token, folder_id):
        if folder_id == "folder_a":
            return [{"id": "fa1", "name": "a1.pdf", "mimeType": "application/pdf"},
                    {"id": "fa2", "name": "a2.pdf", "mimeType": "application/pdf"}]
        return [{"id": "fb1", "name": "b1.pdf", "mimeType": "application/pdf"}]

    async def _fake_baixar_conteudo(access_token, file_id, mime_type):
        return b"bytes"

    async def _fake_extrair_texto(mimetype, conteudo):
        return "texto extraido"

    monkeypatch.setattr("app.integrations.google_drive.client.listar_arquivos", _fake_listar_arquivos)
    monkeypatch.setattr("app.integrations.google_drive.client.baixar_conteudo", _fake_baixar_conteudo)
    monkeypatch.setattr("app.integrations.google_drive.client.extrair_texto", _fake_extrair_texto)

    async def _fake_ingest(**kwargs):
        return None

    async def _fake_delete_chunks(**kwargs):
        return None

    monkeypatch.setattr("app.rag.ingestion.ingest_document", _fake_ingest)
    monkeypatch.setattr("app.rag.ingestion.delete_document_chunks", _fake_delete_chunks)

    # Ordem de execute(): [integracoes] [cfgA] [dedup fa1 -> None] [dedup fa2 -> RAISES]
    #                      [cfgB] [dedup fb1 -> None]
    db = _FakeDB([
        _FakeScalarsResult([integ_a, integ_b]),
        _FakeScalarResult(_FakeCfg()),
        _FakeScalarResult(None),
        _RaiseNoExecute(RuntimeError("DB caiu no meio dos arquivos do tenant A")),
        _FakeScalarResult(_FakeCfg()),
        _FakeScalarResult(None),
    ])

    resultado = await mod.executar_sync_drive_doutrina(db)

    # Tenant B foi processado normalmente mesmo com a falha no tenant A. O
    # agregado `resultado["processados"]` só soma tenants cujo sync
    # terminou OK (mesmo comportamento de antes desta fase) — o progresso
    # parcial do tenant A que falhou fica registrado no `SyncRun` DELE
    # (asserção abaixo), não no agregado da execução inteira.
    assert resultado["tenants_sincronizados"] == 2
    assert resultado["processados"] == 1  # só fb1 (tenant B, único que terminou OK)

    por_tenant = {t: (status, stats) for t, status, stats in chamadas_finalizar}
    assert por_tenant[tenant_a][0] == "ERRO"
    assert por_tenant[tenant_a][1]["processados"] == 1
    assert "erro" in por_tenant[tenant_a][1]
    assert por_tenant[tenant_b][0] == "OK"
    assert por_tenant[tenant_b][1]["processados"] == 1


class _FakeEntradaFalhou:
    """Simula uma JurisprudenciaIngerida já existente com status FALHOU —
    o cenário real da Fase 185: um Google Doc nativo falhou antes do fix
    de `baixar_conteudo`/`extrair_texto`, e deveria voltar a ser tentado
    (não ficar marcado FALHOU pra sempre)."""
    def __init__(self):
        self.status = "FALHOU"
        self.erro = "tipo de arquivo não suportado ou sem texto extraível"
        self.metadata_extraida = {"nome_arquivo": "antigo.gdoc", "google_file_id": "f1"}
        self.processed_at = None


@pytest.mark.asyncio
async def test_arquivo_falhou_e_reprocessado_na_proxima_sincronizacao(monkeypatch):
    """Fase 185 — achado real: a checagem de idempotência só olhava se a
    linha existia (`fonte`+`fonte_documento_id`), nunca o `status` —
    qualquer arquivo que falhou uma vez (ex.: tipo não suportado antes do
    fix) ficava pulado pra sempre em toda sincronização seguinte, mesmo
    depois da causa da falha ser corrigida."""
    import app.workers.tasks.google_drive_sync as mod

    tenant = uuid.uuid4()
    integ = _FakeInteg(tenant, "folder_x")

    async def _fake_iniciar_sync(db, tenant_id, fonte, tipo):
        return type("Run", (), {"tenant_id": tenant_id})()

    async def _fake_finalizar_sync(db, run, status, stats):
        pass

    monkeypatch.setattr("app.services.movements_import.iniciar_sync", _fake_iniciar_sync)
    monkeypatch.setattr("app.services.movements_import.finalizar_sync", _fake_finalizar_sync)

    async def _fake_get_credentials(db, tenant_id, provider):
        return {"access_token": "tok"}

    monkeypatch.setattr("app.services.integration_hub.get_credentials", _fake_get_credentials)

    async def _fake_listar_arquivos(access_token, folder_id):
        return [{"id": "f1", "name": "doutrina.gdoc", "mimeType": "application/vnd.google-apps.document"}]

    async def _fake_baixar_conteudo(access_token, file_id, mime_type):
        return "agora funciona".encode("utf-8")

    async def _fake_extrair_texto(mimetype, conteudo):
        return "agora funciona"

    monkeypatch.setattr("app.integrations.google_drive.client.listar_arquivos", _fake_listar_arquivos)
    monkeypatch.setattr("app.integrations.google_drive.client.baixar_conteudo", _fake_baixar_conteudo)
    monkeypatch.setattr("app.integrations.google_drive.client.extrair_texto", _fake_extrair_texto)

    async def _fake_ingest(**kwargs):
        return None

    chamadas_delete = []

    async def _fake_delete_chunks(**kwargs):
        chamadas_delete.append(kwargs)

    monkeypatch.setattr("app.rag.ingestion.ingest_document", _fake_ingest)
    monkeypatch.setattr("app.rag.ingestion.delete_document_chunks", _fake_delete_chunks)

    entrada_falhou = _FakeEntradaFalhou()
    db = _FakeDB([
        _FakeScalarsResult([integ]),
        _FakeScalarResult(_FakeCfg()),
        _FakeScalarResult(entrada_falhou),  # dedup: já existe, mas FALHOU
    ])

    resultado = await mod.executar_sync_drive_doutrina(db)

    assert resultado["processados"] == 1
    assert resultado["pulados"] == 0
    assert entrada_falhou.status == "EMBEDDED"
    assert entrada_falhou.erro is None
    # Fase 188.1 — reprocessar um FALHOU tem que limpar os chunks antigos
    # antes de re-ingerir, senão duplica no Qdrant (achado da Fase 186).
    assert chamadas_delete == [{"collection": "doutrina_privada", "document_id": "f1"}]


@pytest.mark.asyncio
async def test_arquivo_ja_embedded_continua_sendo_pulado(monkeypatch):
    """O fix não deve fazer a sincronização reprocessar tudo de novo —
    só arquivos que ainda não terminaram EMBEDDED."""
    import app.workers.tasks.google_drive_sync as mod

    tenant = uuid.uuid4()
    integ = _FakeInteg(tenant, "folder_x")

    async def _fake_iniciar_sync(db, tenant_id, fonte, tipo):
        return type("Run", (), {"tenant_id": tenant_id})()

    async def _fake_finalizar_sync(db, run, status, stats):
        pass

    monkeypatch.setattr("app.services.movements_import.iniciar_sync", _fake_iniciar_sync)
    monkeypatch.setattr("app.services.movements_import.finalizar_sync", _fake_finalizar_sync)

    async def _fake_get_credentials(db, tenant_id, provider):
        return {"access_token": "tok"}

    monkeypatch.setattr("app.services.integration_hub.get_credentials", _fake_get_credentials)

    async def _fake_listar_arquivos(access_token, folder_id):
        return [{"id": "f1", "name": "ja-processado.pdf", "mimeType": "application/pdf"}]

    monkeypatch.setattr("app.integrations.google_drive.client.listar_arquivos", _fake_listar_arquivos)

    entrada_embedded = _FakeEntradaFalhou()
    entrada_embedded.status = "EMBEDDED"
    entrada_embedded.erro = None

    db = _FakeDB([
        _FakeScalarsResult([integ]),
        _FakeScalarResult(_FakeCfg()),
        _FakeScalarResult(entrada_embedded),  # dedup: já existe e já terminou
    ])

    resultado = await mod.executar_sync_drive_doutrina(db)

    assert resultado["processados"] == 0
    assert resultado["pulados"] == 1


@pytest.mark.asyncio
async def test_tipo_nativo_do_google_nao_suportado_falha_sem_tentar_download(monkeypatch):
    """Achado real (validação da pasta Doutrina): antes desta fase, um
    Google Sheet/Slides caía em `baixar_conteudo` (que a Drive API rejeita
    pra tipos nativos fora de Docs) e virava um erro genérico de "download
    do arquivo falhou" — a checagem nova (`tipo_suportado`) intercepta
    ANTES, com mensagem precisa, sem sequer tentar baixar."""
    import app.workers.tasks.google_drive_sync as mod

    tenant = uuid.uuid4()
    integ = _FakeInteg(tenant, "folder_x")

    async def _fake_iniciar_sync(db, tenant_id, fonte, tipo):
        return type("Run", (), {"tenant_id": tenant_id})()

    async def _fake_finalizar_sync(db, run, status, stats):
        pass

    monkeypatch.setattr("app.services.movements_import.iniciar_sync", _fake_iniciar_sync)
    monkeypatch.setattr("app.services.movements_import.finalizar_sync", _fake_finalizar_sync)

    async def _fake_get_credentials(db, tenant_id, provider):
        return {"access_token": "tok"}

    monkeypatch.setattr("app.services.integration_hub.get_credentials", _fake_get_credentials)

    async def _fake_listar_arquivos(access_token, folder_id):
        return [{"id": "sheet1", "name": "planilha.xlsx", "mimeType": "application/vnd.google-apps.spreadsheet"}]

    monkeypatch.setattr("app.integrations.google_drive.client.listar_arquivos", _fake_listar_arquivos)

    chamou_download = False

    async def _fake_baixar_conteudo(access_token, file_id, mime_type):
        nonlocal chamou_download
        chamou_download = True
        return b"nao deveria chegar aqui"

    monkeypatch.setattr("app.integrations.google_drive.client.baixar_conteudo", _fake_baixar_conteudo)

    class _FakeDBCapturaAdd(_FakeDB):
        """Registra a instância real de `JurisprudenciaIngerida` que
        `google_drive_sync.py` cria e passa pra `db.add()`, sem alterá-la —
        a base `_FakeDB.add()` descarta o objeto, aqui só observamos."""
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._entrada_real = None

        def add(self, obj):
            self._entrada_real = obj

    db = _FakeDBCapturaAdd([
        _FakeScalarsResult([integ]),
        _FakeScalarResult(_FakeCfg()),
        _FakeScalarResult(None),  # dedup: arquivo novo
    ])

    resultado = await mod.executar_sync_drive_doutrina(db)

    assert not chamou_download
    assert resultado["processados"] == 0
    assert resultado["falhas"] == 1
    assert db._entrada_real.status == "FALHOU"
    assert "Formato não suportado" in db._entrada_real.erro
    assert "application/vnd.google-apps.spreadsheet" in db._entrada_real.erro
