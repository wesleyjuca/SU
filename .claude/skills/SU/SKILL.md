```markdown
# SU Development Patterns

> Corrigido manualmente (Fase 108) — a versão anterior era auto-gerada por
> uma ferramenta de terceiro a partir de 1 único commit e descrevia
> convenções erradas (camelCase/JS) para este repositório, que é Python
> (backend, snake_case/PEP 8) + TypeScript/React (frontend, PascalCase para
> componentes).

## Overview
AFJ CORE SYSTEM: backend FastAPI 3.12 (Python) em `backend/app/`, frontend
Next.js 14 App Router (TypeScript/React) em `frontend/src/`. Ver `/CLAUDE.md`
na raiz do repo para a arquitetura completa.

## Coding Conventions

### File Naming
- **Backend (Python)**: `snake_case.py` — ex.: `coding_agent.py`,
  `repo_context.py`, `oab_capture.py`.
- **Frontend (React/TSX)**: `PascalCase.tsx` para componentes (ex.:
  `AgentStatusCard.tsx`), `camelCase.ts` para hooks/lib (ex.: `useVoice.ts`,
  `websocket.ts`), rotas do App Router seguem a convenção do Next
  (`page.tsx`, `layout.tsx` dentro de pastas em `kebab-case` ou
  `(grupo)`).

### Import Style
- Backend: imports absolutos a partir de `app.` (ex.:
  `from app.agents.base.agent import BaseAgent`).
- Frontend: alias `@/` para `src/` (ex.: `import { useToast } from
  "@/components/ui/Toast"`).

### Commit Messages
Este repositório **não** usa Conventional Commits (`fix:`/`feat:`). O padrão
real, visto em todo o histórico, é:

```
Fase N (área): descrição curta do que mudou (#PR)
```

Exemplo real: `Fase 107 (agentes): scoring estruturado, persistência do CRM, validate() hooks (#131)`.

## Testing Patterns
- Backend: `pytest`/`pytest-asyncio`, arquivos em `backend/tests/test_unit/test_*.py`.
  Padrão comum: `_FakeDB`/mocks leves em vez de banco real para testes de
  lógica isolada (ver qualquer arquivo `test_*_tenant_isolation.py` como
  referência).
- Frontend: `vitest`, arquivos `*.test.tsx`/`*.test.ts` próximos ao que testam.

## Multi-tenant e HITL (invariantes do projeto)
Todo model tem `tenant_id`; toda query deve filtrar por
`current_user.tenant_id`. Ações críticas de agente (protocolar petição,
assinar contrato, enviar comunicação) criam um registro `Approval`
(`status=PENDENTE`) — a ação só executa após aprovação humana. Nunca
contornar esses dois invariantes.

## Workflow real de mudança (observado no histórico do repo)
1. Implementar a mudança num arquivo/conjunto pequeno e coeso.
2. Rodar verificação: `ruff check` + `py_compile` (backend), `tsc --noEmit`
   + `npm run build` (frontend), testes de lógica isolados quando aplicável.
3. Commit com a mensagem no formato `Fase N (área): descrição`.
4. Abrir PR (draft), aguardar CI (`✅ CI — Validate`) ficar verde, marcar
   pronto e mesclar (squash).
```
