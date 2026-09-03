"""Fase 117 — OAuth genérico do hub de integrações (Stripe Connect / Mercado Pago).

`app.core.crypto` importa `cryptography.fernet`, que neste sandbox derruba o
interpretador (bug conhecido `cryptography`/PyO3 — mesma classe de problema que já
bloqueia `pytest` direto neste ambiente, via `conftest.py` -> `app.main` -> ...
-> `cryptography`). Injeta um `cryptography.fernet.Fernet` fake em `sys.modules`
antes do import — testa a lógica real de OAuth (build_oauth_url/exchange/refresh/
get_credentials) sem depender do pacote real, que segue instalado e funcional em
produção/CI (só este sandbox tem o bug de import)."""
import asyncio
import sys
import types
from datetime import datetime, timedelta, timezone


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


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


class _FakeAsyncClient:
    calls = []
    next_response = None

    def __init__(self, timeout=None):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, data=None):
        _FakeAsyncClient.calls.append((url, data))
        return _FakeAsyncClient.next_response


def _limpar_settings_oauth():
    from app.config import settings
    for prefix in ("STRIPE_OAUTH_", "MERCADOPAGO_OAUTH_"):
        for suffix in ("CLIENT_ID", "CLIENT_SECRET", "REDIRECT_URI"):
            setattr(settings, f"{prefix}{suffix}", "")
    settings.GOOGLE_CLIENT_ID = ""
    settings.GOOGLE_CLIENT_SECRET = ""
    settings.GOOGLE_DRIVE_OAUTH_REDIRECT_URI = ""
    settings.GOOGLE_WORKSPACE_OAUTH_REDIRECT_URI = ""
    settings.PDPJ_OAUTH_CLIENT_ID = ""
    settings.PDPJ_OAUTH_CLIENT_SECRET = ""


def test_is_oauth_configured_falso_sem_settings():
    from app.services import integration_hub as ih
    _limpar_settings_oauth()
    assert ih.is_oauth_configured("stripe") is False
    assert ih.is_oauth_configured("mercadopago") is False
    assert ih.is_oauth_configured("provedor_inexistente") is False


def test_is_oauth_configured_true_com_settings():
    from app.services import integration_hub as ih
    from app.config import settings
    _limpar_settings_oauth()
    settings.STRIPE_OAUTH_CLIENT_ID = "cid"
    settings.STRIPE_OAUTH_CLIENT_SECRET = "csecret"
    settings.STRIPE_OAUTH_REDIRECT_URI = "https://api.example.com/cb"
    assert ih.is_oauth_configured("stripe") is True
    _limpar_settings_oauth()


def test_build_oauth_url_stripe():
    from app.services import integration_hub as ih
    from app.config import settings
    _limpar_settings_oauth()
    settings.STRIPE_OAUTH_CLIENT_ID = "cid123"
    settings.STRIPE_OAUTH_REDIRECT_URI = "https://api.example.com/cb"
    url = ih.build_oauth_url("stripe", "signed-state")
    assert url.startswith("https://connect.stripe.com/oauth/authorize?")
    assert "client_id=cid123" in url
    assert "state=signed-state" in url
    assert "scope=read_write" in url
    _limpar_settings_oauth()


def test_build_oauth_url_mercadopago_inclui_platform_id():
    from app.services import integration_hub as ih
    from app.config import settings
    _limpar_settings_oauth()
    settings.MERCADOPAGO_OAUTH_CLIENT_ID = "mpid"
    settings.MERCADOPAGO_OAUTH_REDIRECT_URI = "https://api.example.com/cb"
    url = ih.build_oauth_url("mercadopago", "state2")
    assert "platform_id=mp" in url
    assert "client_id=mpid" in url
    _limpar_settings_oauth()


def test_build_oauth_url_google_drive_doutrina_inclui_access_type_offline_e_consent():
    """Sem access_type=offline+prompt=consent o Google só devolve refresh_token
    na 1ª conexão de todas — precisa forçar em toda URL de autorização."""
    from app.services import integration_hub as ih
    from app.config import settings
    _limpar_settings_oauth()
    settings.GOOGLE_CLIENT_ID = "gcid"
    settings.GOOGLE_DRIVE_OAUTH_REDIRECT_URI = "https://api.example.com/drive-cb"
    url = ih.build_oauth_url("google_drive_doutrina", "state3")
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=gcid" in url
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    assert "drive.readonly" in url
    _limpar_settings_oauth()


def test_build_oauth_url_google_workspace_inclui_5_escopos_consolidados():
    """Fase 139 — antes eram 4 fluxos por usuário (1 escopo por vez, na
    prática sempre os mesmos 4); agora é 1 tela só com os escopos juntos.
    Fase 258 — `drive.metadata.readonly` somado aos 4 originais: permite
    listar pastas pré-existentes do Drive (`drive.file` sozinho só vê
    arquivos que a própria app criou) — necessário pro seletor real de
    pasta de salvamento, sem exigir pasta pública/compartilhada por link."""
    from app.services import integration_hub as ih
    from app.config import settings
    _limpar_settings_oauth()
    settings.GOOGLE_CLIENT_ID = "gcid"
    settings.GOOGLE_WORKSPACE_OAUTH_REDIRECT_URI = "https://api.example.com/workspace-cb"
    url = ih.build_oauth_url("google_workspace", "state4")
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=gcid" in url
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    from urllib.parse import unquote
    url_decoded = unquote(url)
    for escopo in ("calendar.events", "drive.file", "drive.metadata.readonly", "gmail.send", "userinfo.email"):
        assert escopo in url_decoded
    _limpar_settings_oauth()


def test_build_oauth_url_mercadopago_nao_inclui_access_type_offline():
    """O branch access_type=offline é específico do Google — não deve vazar
    pros demais providers."""
    from app.services import integration_hub as ih
    from app.config import settings
    _limpar_settings_oauth()
    settings.MERCADOPAGO_OAUTH_CLIENT_ID = "mpid"
    settings.MERCADOPAGO_OAUTH_REDIRECT_URI = "https://api.example.com/cb"
    url = ih.build_oauth_url("mercadopago", "state2b")
    assert "access_type" not in url
    assert "prompt=consent" not in url
    _limpar_settings_oauth()


def test_exchange_oauth_code_chama_token_url_correto():
    from app.services import integration_hub as ih
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.next_response = _FakeResponse({"access_token": "tok_abc", "refresh_token": "ref_abc"})
    original_client = ih.httpx.AsyncClient
    ih.httpx.AsyncClient = _FakeAsyncClient
    try:
        result = asyncio.run(ih.exchange_oauth_code("stripe", "auth_code_1"))
    finally:
        ih.httpx.AsyncClient = original_client

    assert result["access_token"] == "tok_abc"
    url, data = _FakeAsyncClient.calls[0]
    assert url == "https://connect.stripe.com/oauth/token"
    assert data["code"] == "auth_code_1"
    assert data["grant_type"] == "authorization_code"


def test_exchange_oauth_code_google_drive_doutrina_inclui_client_id_e_redirect_uri():
    """Google exige client_id+redirect_uri na troca do code (não só no refresh)."""
    from app.services import integration_hub as ih
    from app.config import settings
    _limpar_settings_oauth()
    settings.GOOGLE_CLIENT_ID = "gcid"
    settings.GOOGLE_CLIENT_SECRET = "gsecret"
    settings.GOOGLE_DRIVE_OAUTH_REDIRECT_URI = "https://api.example.com/drive-cb"

    _FakeAsyncClient.calls = []
    _FakeAsyncClient.next_response = _FakeResponse({"access_token": "tok_drive", "refresh_token": "ref_drive", "expires_in": 3600})
    original_client = ih.httpx.AsyncClient
    ih.httpx.AsyncClient = _FakeAsyncClient
    try:
        result = asyncio.run(ih.exchange_oauth_code("google_drive_doutrina", "auth_code_drive"))
    finally:
        ih.httpx.AsyncClient = original_client
        _limpar_settings_oauth()

    assert result["access_token"] == "tok_drive"
    url, data = _FakeAsyncClient.calls[0]
    assert url == "https://oauth2.googleapis.com/token"
    assert data["code"] == "auth_code_drive"
    assert data["client_id"] == "gcid"
    assert data["redirect_uri"] == "https://api.example.com/drive-cb"


def test_exchange_oauth_code_google_workspace_inclui_client_id_e_redirect_uri():
    from app.services import integration_hub as ih
    from app.config import settings
    _limpar_settings_oauth()
    settings.GOOGLE_CLIENT_ID = "gcid"
    settings.GOOGLE_CLIENT_SECRET = "gsecret"
    settings.GOOGLE_WORKSPACE_OAUTH_REDIRECT_URI = "https://api.example.com/workspace-cb"

    _FakeAsyncClient.calls = []
    _FakeAsyncClient.next_response = _FakeResponse({"access_token": "tok_ws", "refresh_token": "ref_ws", "expires_in": 3600})
    original_client = ih.httpx.AsyncClient
    ih.httpx.AsyncClient = _FakeAsyncClient
    try:
        result = asyncio.run(ih.exchange_oauth_code("google_workspace", "auth_code_ws"))
    finally:
        ih.httpx.AsyncClient = original_client
        _limpar_settings_oauth()

    assert result["access_token"] == "tok_ws"
    url, data = _FakeAsyncClient.calls[0]
    assert url == "https://oauth2.googleapis.com/token"
    assert data["code"] == "auth_code_ws"
    assert data["client_id"] == "gcid"
    assert data["redirect_uri"] == "https://api.example.com/workspace-cb"


def test_oauth_tokens_to_credentials_marca_oauth_e_usa_token_field_certo():
    from app.services import integration_hub as ih
    creds_stripe = ih._oauth_tokens_to_credentials("stripe", {"access_token": "sk_live_x"})
    assert creds_stripe == {"__oauth__": True, "secret_key": "sk_live_x", "oauth_refresh_token": None}

    creds_mp = ih._oauth_tokens_to_credentials(
        "mercadopago", {"access_token": "APP_USR-x", "refresh_token": "r1", "expires_in": 3600},
    )
    assert creds_mp["__oauth__"] is True
    assert creds_mp["access_token"] == "APP_USR-x"
    assert creds_mp["oauth_refresh_token"] == "r1"
    assert "oauth_expires_at" in creds_mp

    creds_drive = ih._oauth_tokens_to_credentials(
        "google_drive_doutrina", {"access_token": "ya29.x", "refresh_token": "r_drive", "expires_in": 3600},
    )
    assert creds_drive["__oauth__"] is True
    assert creds_drive["access_token"] == "ya29.x"
    assert creds_drive["oauth_refresh_token"] == "r_drive"
    assert "oauth_expires_at" in creds_drive


def test_refresh_oauth_if_needed_sem_expires_at_e_noop_stripe():
    """Stripe nunca expõe oauth_expires_at (token não expira) — refresh vira no-op."""
    from app.services import integration_hub as ih

    class _FakeInteg:
        tenant_id = "t1"

    creds = {"__oauth__": True, "secret_key": "sk_x", "oauth_refresh_token": None}
    result = asyncio.run(ih._refresh_oauth_if_needed(None, _FakeInteg(), "stripe", creds))
    assert result == creds


def test_refresh_oauth_if_needed_token_ainda_valido_nao_renova():
    from app.services import integration_hub as ih

    class _FakeInteg:
        tenant_id = "t1"

    futuro = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    creds = {"__oauth__": True, "access_token": "tok_atual", "oauth_refresh_token": "r1", "oauth_expires_at": futuro}
    result = asyncio.run(ih._refresh_oauth_if_needed(None, _FakeInteg(), "mercadopago", creds))
    assert result["access_token"] == "tok_atual"


def test_refresh_oauth_if_needed_expirado_renova_e_recifra():
    from app.services import integration_hub as ih

    async def fake_refresh(provider, refresh_token):
        assert refresh_token == "r1"
        return {"access_token": "tok_novo", "refresh_token": "r2", "expires_in": 3600}

    original = ih._exchange_oauth_refresh
    ih._exchange_oauth_refresh = fake_refresh
    try:
        flushed = []

        class _FakeDB:
            async def flush(self):
                flushed.append(True)

        class _FakeInteg:
            tenant_id = "t1"
            credentials_enc = None
            status = None

        passado = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        creds = {"__oauth__": True, "access_token": "tok_velho", "oauth_refresh_token": "r1", "oauth_expires_at": passado}
        integ = _FakeInteg()
        result = asyncio.run(ih._refresh_oauth_if_needed(_FakeDB(), integ, "mercadopago", creds))
    finally:
        ih._exchange_oauth_refresh = original

    assert result["access_token"] == "tok_novo"
    assert integ.status == "CONECTADA"
    assert integ.credentials_enc is not None
    assert flushed == [True]


def test_refresh_oauth_if_needed_falha_de_rede_devolve_creds_antigas_fail_soft():
    from app.services import integration_hub as ih

    async def fake_refresh_falha(provider, refresh_token):
        raise RuntimeError("timeout")

    original = ih._exchange_oauth_refresh
    ih._exchange_oauth_refresh = fake_refresh_falha
    try:
        class _FakeInteg:
            tenant_id = "t1"

        passado = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        creds = {"__oauth__": True, "access_token": "tok_velho", "oauth_refresh_token": "r1", "oauth_expires_at": passado}
        result = asyncio.run(ih._refresh_oauth_if_needed(None, _FakeInteg(), "mercadopago", creds))
    finally:
        ih._exchange_oauth_refresh = original

    assert result == creds


def test_get_credentials_marcador_oauth_ausente_cai_no_legado_sem_chamar_refresh():
    """Chave colada manualmente (sem __oauth__) nunca aciona _refresh_oauth_if_needed."""
    from app.services import integration_hub as ih

    class _FakeScalarResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    encrypted = ih.encrypt('{"secret_key": "sk_manual"}')

    class _FakeIntegRow:
        credentials_enc = encrypted

    class _FakeDB:
        async def execute(self, query):
            return _FakeScalarResult(_FakeIntegRow())

    called = {"refresh": False}

    async def fake_refresh(*a, **kw):
        called["refresh"] = True
        return {}

    original = ih._refresh_oauth_if_needed
    ih._refresh_oauth_if_needed = fake_refresh
    try:
        creds = asyncio.run(ih.get_credentials(_FakeDB(), "tenant1", "stripe"))
    finally:
        ih._refresh_oauth_if_needed = original

    assert creds == {"secret_key": "sk_manual"}
    assert called["refresh"] is False


def test_get_credentials_marcador_oauth_presente_aciona_refresh():
    from app.services import integration_hub as ih

    class _FakeScalarResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    encrypted = ih.encrypt('{"__oauth__": true, "secret_key": "sk_oauth"}')

    class _FakeIntegRow:
        credentials_enc = encrypted

    class _FakeDB:
        async def execute(self, query):
            return _FakeScalarResult(_FakeIntegRow())

    called = {"refresh": False}

    async def fake_refresh(db, integ, provider, creds):
        called["refresh"] = True
        return {**creds, "renovado": True}

    original = ih._refresh_oauth_if_needed
    ih._refresh_oauth_if_needed = fake_refresh
    try:
        creds = asyncio.run(ih.get_credentials(_FakeDB(), "tenant1", "stripe"))
    finally:
        ih._refresh_oauth_if_needed = original

    assert called["refresh"] is True
    assert creds["renovado"] is True


def test_is_oauth_configured_pdpj_falso_sem_settings():
    """PDPJ não tem redirect_uri_setting (grant_type=password, sem redirect) —
    is_oauth_configured não pode exigir uma chave que o provider não declara."""
    from app.services import integration_hub as ih
    _limpar_settings_oauth()
    assert ih.is_oauth_configured("pdpj") is False


def test_is_oauth_configured_pdpj_true_com_settings_sem_redirect_uri():
    from app.services import integration_hub as ih
    from app.config import settings
    _limpar_settings_oauth()
    settings.PDPJ_OAUTH_CLIENT_ID = "cnj-client"
    settings.PDPJ_OAUTH_CLIENT_SECRET = "cnj-secret"
    assert ih.is_oauth_configured("pdpj") is True
    _limpar_settings_oauth()


def test_exchange_oauth_password_pdpj_grant_type_e_token_url_corretos():
    """Fase 177.1 — login direto do PDPJ via Keycloak (grant_type=password)."""
    from app.services import integration_hub as ih
    from app.config import settings
    _limpar_settings_oauth()
    settings.PDPJ_OAUTH_CLIENT_ID = "cnj-client"
    settings.PDPJ_OAUTH_CLIENT_SECRET = "cnj-secret"

    _FakeAsyncClient.calls = []
    _FakeAsyncClient.next_response = _FakeResponse({"access_token": "tok_pdpj", "refresh_token": "ref_pdpj", "expires_in": 300})
    original_client = ih.httpx.AsyncClient
    ih.httpx.AsyncClient = _FakeAsyncClient
    try:
        result = asyncio.run(ih.exchange_oauth_password("pdpj", "usuario.cnj", "senha123"))
    finally:
        ih.httpx.AsyncClient = original_client
        _limpar_settings_oauth()

    assert result["access_token"] == "tok_pdpj"
    url, data = _FakeAsyncClient.calls[0]
    assert url == "https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/token"
    assert data["grant_type"] == "password"
    assert data["username"] == "usuario.cnj"
    assert data["password"] == "senha123"
    assert data["client_id"] == "cnj-client"
    assert data["client_secret"] == "cnj-secret"


def test_exchange_oauth_password_propaga_erro_http(monkeypatch):
    """Credencial inválida (401 do Keycloak) deve propagar — quem trata e
    traduz pra mensagem amigável é o endpoint (integrations_hub.py)."""
    from app.services import integration_hub as ih
    from app.config import settings
    _limpar_settings_oauth()
    settings.PDPJ_OAUTH_CLIENT_ID = "cnj-client"
    settings.PDPJ_OAUTH_CLIENT_SECRET = "cnj-secret"

    _FakeAsyncClient.calls = []
    _FakeAsyncClient.next_response = _FakeResponse({"error": "invalid_grant"}, status_code=401)
    original_client = ih.httpx.AsyncClient
    ih.httpx.AsyncClient = _FakeAsyncClient
    try:
        with __import__("pytest").raises(RuntimeError):
            asyncio.run(ih.exchange_oauth_password("pdpj", "usuario.cnj", "senha-errada"))
    finally:
        ih.httpx.AsyncClient = original_client
        _limpar_settings_oauth()


def test_oauth_tokens_to_credentials_pdpj_usa_sso_token_como_token_field():
    from app.services import integration_hub as ih
    creds = ih._oauth_tokens_to_credentials("pdpj", {"access_token": "tok_pdpj", "refresh_token": "ref_pdpj", "expires_in": 300})
    assert creds["__oauth__"] is True
    assert creds["sso_token"] == "tok_pdpj"
    assert creds["oauth_refresh_token"] == "ref_pdpj"
    assert "oauth_expires_at" in creds


def test_refresh_oauth_if_needed_pdpj_usa_token_url_configuravel():
    """O refresh do PDPJ reaproveita _exchange_oauth_refresh (já genérico) —
    só precisa resolver o token_url via settings (token_url_setting), não
    um literal fixo como os demais provedores."""
    from app.services import integration_hub as ih
    from app.config import settings
    _limpar_settings_oauth()
    settings.PDPJ_OAUTH_CLIENT_ID = "cnj-client"
    settings.PDPJ_OAUTH_CLIENT_SECRET = "cnj-secret"

    _FakeAsyncClient.calls = []
    _FakeAsyncClient.next_response = _FakeResponse({"access_token": "tok_novo", "refresh_token": "ref_novo", "expires_in": 300})
    original_client = ih.httpx.AsyncClient
    ih.httpx.AsyncClient = _FakeAsyncClient
    try:
        result = asyncio.run(ih._exchange_oauth_refresh("pdpj", "ref_velho"))
    finally:
        ih.httpx.AsyncClient = original_client
        _limpar_settings_oauth()

    assert result["access_token"] == "tok_novo"
    url, data = _FakeAsyncClient.calls[0]
    assert url == settings.PDPJ_OAUTH_TOKEN_URL
    assert data["grant_type"] == "refresh_token"
    assert data["refresh_token"] == "ref_velho"


def test_list_status_oauth_disponivel_false_sem_settings_configuradas():
    """oauth_disponivel só fica True se a flag do provider E as settings existirem."""
    from app.services import integration_hub as ih
    _limpar_settings_oauth()

    class _FakeScalarsResult:
        def all(self):
            return []

    class _FakeResult:
        def scalars(self):
            return _FakeScalarsResult()

    class _FakeDB:
        async def execute(self, query):
            return _FakeResult()

    status = asyncio.run(ih.list_status(_FakeDB(), "tenant1"))
    por_provider = {s["provider"]: s for s in status}
    assert por_provider["stripe"]["oauth_disponivel"] is False
    assert por_provider["mercadopago"]["oauth_disponivel"] is False
    assert por_provider["clicksign"]["oauth_disponivel"] is False
