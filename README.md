# AFJ CORE SYSTEM

**Sistema Jurídico Inteligente — Almeida, Freire & Jucá Advogados**

ERP jurídico multiagente com IA, monitoramento processual, geração de petições, memória institucional e governança humana sobre todas as ações críticas.

---

## Stack

```
Backend:   Python 3.12 + FastAPI + SQLAlchemy + Alembic
Frontend:  Next.js 14 + TailwindCSS + Shadcn UI
Banco:     PostgreSQL 16 + Redis 7 + Qdrant (vetorial)
IA:        Claude (Anthropic) + OpenAI Embeddings
Agentes:   LangGraph + 19 agentes especializados
Infra:     Docker Compose (dev) + Railway + Vercel (prod)
```

## Quick Start

```bash
cp .env.example .env   # configure suas chaves
make up                # sobe todos os serviços
make migrate           # cria o schema
make seed              # dados iniciais

# Acesso:
# API:      http://localhost:8000/api/v1/docs
# Frontend: http://localhost:3000
```

## Princípios

- **IA sugere — humano aprova:** toda ação irreversível requer validação humana
- **Auditoria completa:** todo evento registrado em `audit_logs` (imutável, LGPD)
- **Jurisprudência verificável:** proibido citar sem fonte comprovada no Qdrant
- **Circuit breaker:** conectores de tribunal toleram falhas sem derrubar o sistema

## Governança

```
IA sugere → Humano revisa → Humano aprova → IA executa → Sistema registra
```
