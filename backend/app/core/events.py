"""Eventos de startup e shutdown da aplicação FastAPI."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
from fastapi import FastAPI
import structlog

log = structlog.get_logger()

APP_START_TIME: Optional[datetime] = None


async def _seed_default_data(engine) -> None:
    """Cria tenant padrão e usuários iniciais se o banco estiver vazio."""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    from app.models.tenant import Tenant, TenantConfig
    from app.models.user import User
    from app.core.security import hash_password
    import uuid

    async with AsyncSession(engine) as session:
        result = await session.execute(select(Tenant).limit(1))
        tenant = result.scalar_one_or_none()
        if not tenant:
            tenant = Tenant(
                id=uuid.uuid4(), name="AFJ Advogados",
                slug="afj", plan="STANDARD", is_active=True,
            )
            session.add(tenant)
            session.add(TenantConfig(id=uuid.uuid4(), tenant_id=tenant.id))
            await session.flush()

        # Inclui os e-mails DOCUMENTADOS (CLAUDE.md e /ajuda usam @afj.com.br) —
        # a divergência @afjadvogados.com vs @afj.com.br causava
        # "E-mail ou senha incorretos" no login do admin.
        SEED = [
            ("admin@afj.com.br",          "Admin@123",    "Administrador", "ADMIN"),
            ("advogado@afj.com.br",       "Adv@123",      "Advogado",      "ADVOGADO"),
            ("admin@afjadvogados.com",    "Admin@123",    "Administrador", "ADMIN"),
            ("socio@afjadvogados.com",    "Socio@123",    "Sócio",         "SOCIO"),
            ("advogado@afjadvogados.com", "Advogado@123", "Advogado",      "ADVOGADO"),
            # SUPERADMIN — dono da plataforma SaaS (gerencia todos os escritórios).
            ("super@afj.com.br",          "Super@123",    "Super Admin",   "SUPERADMIN"),
        ]
        import os
        # Resetar senha/reativar conta a cada boot é destrutivo (desfaz trocas
        # de senha e reativa contas desativadas). Só com opt-in explícito.
        reset_passwords = os.environ.get("SEED_RESET_PASSWORDS", "").lower() == "true"
        for email, password, full_name, role in SEED:
            exists = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if not exists:
                session.add(User(
                    id=uuid.uuid4(), email=email,
                    hashed_password=hash_password(password),
                    full_name=full_name, role=role,
                    is_active=True, tenant_id=tenant.id,
                ))
            elif reset_passwords:
                exists.hashed_password = hash_password(password)
                exists.is_active = True
        await session.commit()
    log.info("seed_complete", reset_passwords=reset_passwords)


async def _seed_tribunais(engine) -> None:
    """Semeia a tabela de referência `tribunais` a partir do mapa canônico
    (TRIBUNAL_INDICES). Idempotente: insere só os códigos que ainda faltam."""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    from app.models.tribunal import Tribunal
    from app.services.tribunais_ref import linhas_seed

    async with AsyncSession(engine) as session:
        existentes = {c for (c,) in (await session.execute(select(Tribunal.codigo))).all()}
        novos = [Tribunal(**linha) for linha in linhas_seed() if linha["codigo"] not in existentes]
        if novos:
            session.add_all(novos)
            await session.commit()
    log.info("seed_tribunais_complete", inseridos=len(novos))


async def _carregar_cache_tribunais(engine) -> None:
    """Fase 87 — carrega o cache de leitura da tabela `tribunais` (não do dict
    hardcoded), tornando-a a fonte de verdade em runtime. Best-effort: falha
    aqui só significa que `CNJDataJudClient._index` cai no fallback hardcoded
    (comportamento idêntico ao de antes desta fase)."""
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.services.tribunais_ref import carregar_cache

    async with AsyncSession(engine) as session:
        cache = await carregar_cache(session)
    log.info("tribunais_cache_carregado", tribunais=len(cache))


async def _backfill_ai_provider_configs(engine) -> None:
    """Fase 137.1 — usuários com BYOK no desenho antigo (colunas
    User.ai_provider/ai_api_key_enc/ai_model/ai_enabled) ganham uma
    AIProviderConfig equivalente (is_default=True), sem perder o dado nem
    exigir reconfiguração. Idempotente: só cria pra quem ainda não tem
    nenhuma config; as colunas antigas do User continuam intactas (fallback
    em byok.py::user_ai_creds, caso este backfill não tenha rodado ainda)."""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    from app.models.user import User
    from app.models.ai_config import AIProviderConfig
    from app.core.crypto import decrypt, encrypt
    import json

    criados = 0
    async with AsyncSession(engine) as session:
        usuarios = (await session.execute(
            select(User).where(User.ai_provider.isnot(None), User.ai_api_key_enc.isnot(None))
        )).scalars().all()
        for user in usuarios:
            ja_tem = (await session.execute(
                select(AIProviderConfig.id).where(AIProviderConfig.user_id == user.id)
            )).scalar_one_or_none()
            if ja_tem:
                continue
            chave = decrypt(user.ai_api_key_enc)
            if not chave:
                continue  # indecifrável (ENCRYPTION_KEY mudou) — usuário precisa re-salvar, mesmo hoje
            creds_enc = encrypt(json.dumps({"api_key": chave}))
            session.add(AIProviderConfig(
                user_id=user.id, tenant_id=user.tenant_id,
                provider=user.ai_provider, display_name=f"{(user.ai_provider or '').title()} (migrado)",
                auth_method="api_key", credentials_enc=creds_enc,
                model=user.ai_model, enabled=bool(user.ai_enabled), is_default=True,
            ))
            criados += 1
        if criados:
            await session.commit()
    log.info("ai_provider_configs_backfill_complete", criados=criados)


async def _background_warmup() -> None:
    """Optional warmup that runs after the app is already serving requests."""
    await asyncio.sleep(2)

    try:
        from app.agents.brain.orchestrator import get_orchestrator_graph
        get_orchestrator_graph()
        log.info("orchestrator_ready")
    except Exception as exc:
        log.warning("orchestrator_warmup_failed", error=str(exc))

    from app.config import settings as _cfg
    _qdrant_configured = bool(
        _cfg.QDRANT_API_KEY or
        (_cfg.QDRANT_URL and _cfg.QDRANT_URL not in {"http://qdrant:6333", "http://localhost:6333"})
    )
    if _qdrant_configured:
        try:
            from app.db.qdrant import get_qdrant
            from app.rag.collections import ensure_collections
            qdrant = await get_qdrant()
            await asyncio.wait_for(ensure_collections(qdrant), timeout=15.0)
            log.info("qdrant_collections_ready")
        except Exception as exc:
            log.warning("qdrant_startup_warning", error=str(exc))
    else:
        log.info("qdrant_skipped", reason="QDRANT_URL is default placeholder — skipping init")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ─── STARTUP (fast — must complete before Railway health check) ───────────
    global APP_START_TIME
    from datetime import timezone
    APP_START_TIME = datetime.now(timezone.utc)
    log.info("afj_core_starting", version="1.0.0")

    from app.db.base import engine, Base, _has_real_db
    from sqlalchemy import text
    if _has_real_db:
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            log.info("database_ready")
        except Exception as exc:
            log.error("database_startup_failed", error=str(exc))

        for _sql in [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS linked_client_id UUID REFERENCES clients(id)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_provider VARCHAR(20)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_api_key_enc TEXT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_model VARCHAR(80)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_enabled BOOLEAN DEFAULT FALSE",
            # Fase 27 — unidades da mesma banca (create_all não adiciona colunas novas)
            "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS parent_tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL",
            "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS unit_label VARCHAR(120)",
            # Fase 34 — desfecho do processo (taxa de êxito nos relatórios de gestão)
            "ALTER TABLE legal_processes ADD COLUMN IF NOT EXISTS desfecho VARCHAR(20)",
            # Fase 35 — faturamento a cliente (BillingInvoice já existia sem estes campos)
            "ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id)",
            "ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS descricao TEXT",
            "ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS itens JSONB",
            "ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS data_vencimento DATE",
            "ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS created_by UUID REFERENCES users(id)",
            "ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now()",
            # Fase 48 — faixas de alerta de prazo já enviadas (janela resiliente a downtime)
            "ALTER TABLE process_deadlines ADD COLUMN IF NOT EXISTS alertas_enviados JSONB DEFAULT '[]'::jsonb",
            "ALTER TABLE document_versions ADD COLUMN IF NOT EXISTS conteudo_texto TEXT",
            "ALTER TABLE process_movements ADD COLUMN IF NOT EXISTS possivel_prazo BOOLEAN DEFAULT FALSE",
            # Fase 68 — pagamento online de faturas (link + provedor + id externo)
            "ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS payment_link TEXT",
            "ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS payment_provider VARCHAR(30)",
            "ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS payment_external_id VARCHAR(150)",
            # Fase 70 — WhatsApp do colaborador (notificações de prazo/intimação)
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS telefone VARCHAR(20)",
            # Fase 72 — dedup canônico de movimentos (importador único de captura)
            "ALTER TABLE process_movements ADD COLUMN IF NOT EXISTS dedup_hash VARCHAR(64)",
            "CREATE INDEX IF NOT EXISTS ix_process_movements_dedup_hash ON process_movements (dedup_hash)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_process_movements_dedup ON process_movements (process_id, dedup_hash) WHERE dedup_hash IS NOT NULL",
            # Fase 86 — origem do processo first-class (antes só em metadata_json,
            # nunca lida). Backfill idempotente (WHERE fonte IS NULL): só os 2
            # caminhos de criação existem hoje (OAB e cadastro manual), então
            # tudo que não veio da captura por OAB é seguro inferir como manual.
            "ALTER TABLE legal_processes ADD COLUMN IF NOT EXISTS fonte VARCHAR(30)",
            "CREATE INDEX IF NOT EXISTS ix_legal_processes_fonte ON legal_processes (fonte)",
            "UPDATE legal_processes SET fonte = 'OAB' WHERE fonte IS NULL AND metadata_json->>'fonte_captura' = 'OAB'",
            "UPDATE legal_processes SET fonte = 'MANUAL' WHERE fonte IS NULL",
            # Fase 116 — audit_logs cresce a cada request de escrita (bem mais
            # rápido que legal_processes) e só tinha índice em timestamp; toda
            # consulta tenant-scoped (GET /audit, /audit/summary) forçava Seq
            # Scan na tabela inteira. Validado empiricamente: ~25ms/query já
            # com 100k linhas (2 tenants), tendência a piorar linearmente.
            "CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_logs (tenant_id, timestamp)",
            # Fase 127 — origem da parte (MANUAL vs importada de PDPJ/Escavador/
            # Judit/Jusbrasil). Backfill idempotente: até aqui só existia o
            # caminho de sync automático (importar_partes via atualizar-partes),
            # então toda linha pré-existente veio de importação — não dá pra
            # saber de qual provedor especificamente sem mais contexto, por
            # isso o rótulo genérico pros dados antigos.
            "ALTER TABLE process_parties ADD COLUMN IF NOT EXISTS origem VARCHAR(20)",
            "UPDATE process_parties SET origem = 'IMPORTADO' WHERE origem IS NULL",
            # Fase 133 — a página de criar processo já tinha um textarea
            # "Descrição" sem coluna nenhuma por trás: o usuário digitava,
            # salvava, e o texto era descartado silenciosamente.
            "ALTER TABLE legal_processes ADD COLUMN IF NOT EXISTS descricao TEXT",
            # Fase 134 — audit_logs.action (VARCHAR 100) estourava em rotas com
            # 2 UUIDs no path (ex. PUT .../processes/{uuid}/partes/{uuid}),
            # derrubando silenciosamente aquela linha de auditoria. Aumentar o
            # VARCHAR não reescreve linhas nem dispara trg_audit_logs_immutable
            # (que só age em UPDATE/DELETE) — seguro mesmo com a tabela imutável.
            "ALTER TABLE audit_logs ALTER COLUMN action TYPE VARCHAR(255)",
            # Fase 137.4 — "ajuste por área" passa a poder referenciar uma
            # AIProviderConfig inteira (provider+chave+modelo próprios), não só
            # trocar a string do modelo. `model` vira opcional (fallback legado).
            "ALTER TABLE ai_task_overrides ALTER COLUMN model DROP NOT NULL",
            "ALTER TABLE ai_task_overrides ADD COLUMN IF NOT EXISTS provider_config_id UUID "
            "REFERENCES ai_provider_configs(id) ON DELETE SET NULL",
        ]:
            try:
                async with engine.begin() as conn:
                    await conn.execute(text(_sql))
            except Exception as exc:
                log.warning("migration_warning", sql=_sql[:60], error=str(exc))

        try:
            await _seed_default_data(engine)
        except Exception as exc:
            log.warning("seed_warning", error=str(exc))

        try:
            await _seed_tribunais(engine)
        except Exception as exc:
            log.warning("seed_tribunais_warning", error=str(exc))

        try:
            await _carregar_cache_tribunais(engine)
        except Exception as exc:
            log.warning("tribunais_cache_warning", error=str(exc))

        try:
            await _backfill_ai_provider_configs(engine)
        except Exception as exc:
            log.warning("ai_provider_configs_backfill_warning", error=str(exc))
    else:
        log.warning("database_skipped", reason="DATABASE_URL not configured — running in degraded mode")

    log.info("afj_core_ready", message="AFJ CORE SYSTEM iniciado com sucesso")
    asyncio.create_task(_background_warmup())

    yield

    # ─── SHUTDOWN ─────────────────────────────────────────────────────────────
    log.info("afj_core_shutting_down")

    try:
        from app.db.redis import close_redis
        await close_redis()
    except Exception:
        pass

    try:
        from app.db.qdrant import close_qdrant
        await close_qdrant()
    except Exception:
        pass

    log.info("afj_core_stopped")
