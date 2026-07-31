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
    },
    "openai": {
        "nome": "OpenAI (ChatGPT)",
        "auth_methods": ["api_key"],
        "base_url": "https://api.openai.com/v1",
        "requires_key": True,
        "oauth_disponivel": False,
        "modelo_sugerido": "gpt-4.1",
        "obter": "platform.openai.com → API keys.",
    },
    "gemini": {
        "nome": "Google Gemini",
        "auth_methods": ["api_key"],
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "requires_key": True,
        "oauth_disponivel": False,  # Vertex AI tem OAuth, mas exige projeto GCP/billing/IAM — fora de escopo
        "modelo_sugerido": "gemini-2.5-flash",
        "obter": "aistudio.google.com/apikey.",
    },
    "grok": {
        "nome": "xAI Grok",
        "auth_methods": ["api_key"],
        "base_url": "https://api.x.ai/v1",
        "requires_key": True,
        "oauth_disponivel": False,  # OAuth da xAI existe mas é imaturo/instável, não recomendado
        "modelo_sugerido": "grok-4",
        "obter": "console.x.ai → API Keys.",
    },
    "deepseek": {
        "nome": "DeepSeek",
        "auth_methods": ["api_key"],
        "base_url": "https://api.deepseek.com/v1",
        "requires_key": True,
        "oauth_disponivel": False,
        "modelo_sugerido": "deepseek-chat",
        "obter": "platform.deepseek.com → API keys.",
    },
    "openrouter": {
        "nome": "OpenRouter",
        "auth_methods": ["api_key", "oauth"],  # OAuth PKCE genuíno desde a Fase 137.2
        "base_url": "https://openrouter.ai/api/v1",
        "requires_key": True,
        "oauth_disponivel": True,  # GET /me/ai-configs/oauth/openrouter/connect (Fase 137.2)
        "modelo_sugerido": "openai/gpt-4.1",
        "obter": "openrouter.ai/keys.",
    },
    "ollama": {
        "nome": "Ollama (modelo local)",
        "auth_methods": ["none"],
        "base_url": None,  # usuário informa a URL do próprio servidor (ex.: http://localhost:11434/v1)
        "requires_key": False,
        "oauth_disponivel": False,
        "modelo_sugerido": "llama3.1",
        "obter": "Instale o Ollama e rode `ollama pull <modelo>` — sem chave, só a URL do servidor.",
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
