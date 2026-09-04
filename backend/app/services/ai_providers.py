"""Registro de provedores de IA suportados em "Minhas IAs" (Fase 137.1).

Mesmo padrão de `app.services.integration_hub.PROVIDERS` — um dict estático
descrevendo cada provedor, consultado tanto pelo backend (validação,
resolução de base_url) quanto exposto ao frontend via API.

Todos os provedores exceto Anthropic usam o mesmo endpoint compatível com a
API da OpenAI (só muda `base_url`/se exige chave) — ver
`app.integrations.llm_client._call_openai_compatible`.
"""

AI_PROVIDERS: dict[str, dict] = {
    "anthropic": {
        "nome": "Anthropic Claude",
        "auth_methods": ["api_key"],
        "base_url": None,  # SDK oficial, não é OpenAI-compatível
        "requires_key": True,
        "oauth_disponivel": False,  # proibido pelos termos da Anthropic p/ apps de terceiro
        "modelo_sugerido": "claude-sonnet-5",
        "obter": "console.anthropic.com → API Keys.",
        "embedding_model": None,  # sem API pública de embeddings, confirmado
        "embedding_dimensions": None,
    },
    "openai": {
        "nome": "OpenAI (ChatGPT)",
        "auth_methods": ["api_key"],
        "base_url": "https://api.openai.com/v1",
        "requires_key": True,
        "oauth_disponivel": False,
        "modelo_sugerido": "gpt-4.1",
        "obter": "platform.openai.com → API keys.",
        "embedding_model": "text-embedding-3-large",
        "embedding_dimensions": 3072,
    },
    "gemini": {
        "nome": "Google Gemini",
        "auth_methods": ["api_key"],
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "requires_key": True,
        "oauth_disponivel": False,  # Vertex AI tem OAuth, mas exige projeto GCP/billing/IAM — fora de escopo
        "modelo_sugerido": "gemini-2.5-flash",
        "obter": "aistudio.google.com/apikey.",
        # gemini-embedding-001 via endpoint OpenAI-compatível — dimensão
        # padrão 3072 (Matryoshka Representation Learning), igual à da OpenAI.
        "embedding_model": "gemini-embedding-001",
        "embedding_dimensions": 3072,
    },
    "grok": {
        "nome": "xAI Grok",
        "auth_methods": ["api_key"],
        "base_url": "https://api.x.ai/v1",
        "requires_key": True,
        "oauth_disponivel": False,  # OAuth da xAI existe mas é imaturo/instável, não recomendado
        "modelo_sugerido": "grok-4",
        "obter": "console.x.ai → API Keys.",
        "embedding_model": None,  # sem API pública de embeddings, confirmado
        "embedding_dimensions": None,
    },
    "deepseek": {
        "nome": "DeepSeek",
        "auth_methods": ["api_key"],
        "base_url": "https://api.deepseek.com/v1",
        "requires_key": True,
        "oauth_disponivel": False,
        "modelo_sugerido": "deepseek-chat",
        "obter": "platform.deepseek.com → API keys.",
        # Suporte a embeddings não confirmado com confiança (fontes
        # encontradas não são documentação oficial) — tratado como
        # indisponível nesta fase, não assumido.
        "embedding_model": None,
        "embedding_dimensions": None,
    },
    "openrouter": {
        "nome": "OpenRouter",
        "auth_methods": ["api_key", "oauth"],  # OAuth PKCE genuíno desde a Fase 137.2
        "base_url": "https://openrouter.ai/api/v1",
        "requires_key": True,
        "oauth_disponivel": True,  # GET /me/ai-configs/oauth/openrouter/connect (Fase 137.2)
        "modelo_sugerido": "openai/gpt-4.1",
        "obter": "openrouter.ai/keys.",
        # Não confirmado nesta fase — fica de fora até validação futura.
        "embedding_model": None,
        "embedding_dimensions": None,
    },
    "ollama": {
        "nome": "Ollama (modelo local)",
        "auth_methods": ["none"],
        "base_url": None,  # usuário informa a URL do próprio servidor (ex.: http://localhost:11434/v1)
        "requires_key": False,
        "oauth_disponivel": False,
        "modelo_sugerido": "llama3.1",
        "obter": "Instale o Ollama e rode `ollama pull <modelo>` — sem chave, só a URL do servidor.",
        # Self-hosted — depende do modelo que o usuário baixou localmente,
        # sem default seguro pra assumir. Extensão futura, não bloqueada
        # pela arquitetura.
        "embedding_model": None,
        "embedding_dimensions": None,
    },
    # Fase 195 — diferente do Gemini (chave simples via AI Studio), Vertex AI
    # é o mesmo modelo Gemini servido pela infra do projeto GCP do PRÓPRIO
    # escritório (BYOK), autenticado por conta de serviço — não é
    # OpenAI-compatível, tem branch dedicado em app/integrations/llm_client.py
    # (_call_vertex_ai). `base_url` aqui é reaproveitado como a REGIÃO do GCP
    # (ex.: "us-central1"), não uma URL — opcional, tem default no código.
    "vertex_ai": {
        "nome": "Google Vertex AI",
        "auth_methods": ["service_account_json"],
        "base_url": None,
        "requires_key": True,
        "oauth_disponivel": False,  # exige projeto GCP com billing/IAM do próprio escritório — BYOK via conta de serviço, não OAuth
        "modelo_sugerido": "gemini-2.5-flash",
        "obter": "console.cloud.google.com → IAM e administrador → Contas de serviço → crie uma "
                 "chave JSON com o papel \"Vertex AI User\" — cole o JSON completo aqui.",
        # Autenticação/formato de chamada diferente (JWT de conta de
        # serviço, não o endpoint OpenAI-compatível) — fora de escopo da
        # generalização de embeddings desta fase.
        "embedding_model": None,
        "embedding_dimensions": None,
    },
}


def get_provider(name: str) -> dict | None:
    return AI_PROVIDERS.get((name or "").lower())


def resolve_base_url(provider: str, custom_base_url: str | None) -> str | None:
    """Ollama exige URL própria (self-hosted); os demais têm base_url fixa."""
    info = get_provider(provider)
    if info and info.get("base_url"):
        return info["base_url"]
    return custom_base_url


def embedding_capable_providers() -> set[str]:
    """Provedores cujo registro central declara suporte a embeddings.

    Fonte única de verdade pra "este provedor gera embedding hoje?" —
    reaproveitado tanto na resolução de credencial BYOK de embeddings
    (`rag/embeddings.py`) quanto na API que alimenta o frontend
    (`GET /users/me/ai-providers`), evitando duplicar essa lista.
    """
    return {name for name, info in AI_PROVIDERS.items() if info.get("embedding_model")}
