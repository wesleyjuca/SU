# AFJ CORE SYSTEM

**Sistema Jurídico Inteligente — Almeida, Freire & Jucá Advogados**

Plataforma jurídica inteligente para gestão de processos, clientes e operações do escritório, combinando agentes de IA, memória institucional, automação processual e governança humana sobre ações críticas.

---

## Stack

```text
Backend:      Python 3.12 + FastAPI + SQLAlchemy + Alembic
Frontend:     Next.js 14 + TailwindCSS + Shadcn UI
Banco:        PostgreSQL 16 + Redis 7 + Qdrant (vetorial)
IA:           Claude (Anthropic) + OpenAI Embeddings
Agentes:      LangGraph + agentes especializados
Infra:        Docker Compose (dev) + Railway + Vercel (prod)
```

## Arquitetura

```text
                    ┌─────────────────────┐
                    │      Next.js        │
                    │     Frontend        │
                    └──────────┬──────────┘
                               │
                            REST / JWT
                               │
                    ┌──────────▼──────────┐
                    │       FastAPI       │
                    │       Backend       │
                    └────┬─────┬─────┬────┘
                         │     │     │
             ┌───────────┘     │     └────────────┐
             ▼                 ▼                  ▼
       ┌───────────┐     ┌───────────┐      ┌───────────┐
       │ PostgreSQL│     │   Redis   │      │  Qdrant   │
       │   Dados   │     │ Cache/Jobs│      │ Vetorial  │
       └───────────┘     └─────┬─────┘      └─────┬─────┘
                               │                   │
                               ▼                   │
                         ┌───────────┐             │
                         │  Celery   │             │
                         │  Workers  │             │
                         └─────┬─────┘             │
                               │                   │
                               └─────────┬─────────┘
                                         ▼
                                  ┌─────────────┐
                                  │  LangGraph  │
                                  │   Agentes   │
                                  └─────────────┘

## Princípios

- **IA sugere — humano aprova:** ações críticas ou irreversíveis exigem validação humana antes da execução.
- **Auditoria completa:** ações relevantes são registradas em `audit_logs` para rastreabilidade e governança.
- **Isolamento multi-tenant:** dados e operações devem respeitar o `tenant_id` do usuário autenticado.
- **Jurisprudência verificável:** fontes jurídicas devem possuir origem comprovável quando utilizadas como fundamento.
- **Resiliência:** falhas em conectores e serviços externos não devem derrubar o sistema.
- **Simplicidade:** reutilizar componentes e serviços existentes e evitar complexidade sem benefício claro.

## Governança

```
IA sugere → Humano revisa → Humano aprova → IA executa → Sistema registra
```
