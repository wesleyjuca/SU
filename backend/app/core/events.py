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
            # Fase 137.6 — "modo de uso" global (padrao/round_robin/performance):
            # escolhe automaticamente qual AIProviderConfig tentar primeiro a cada
            # chamada. NULL = padrao (ordem manual de sempre) — zero regressão pra
            # quem nunca abrir essa opção.
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_balance_mode VARCHAR(20)",
            # Fase 138.2 — jurisprudencia_ingerida (Fase 138.1) passa a servir
            # também fontes trazidas por um escritório específico (pasta de
            # doutrina do Drive), não só fontes globais como o STJ. NULL
            # continua significando "fonte global/sem dono" — zero regressão.
            "ALTER TABLE jurisprudencia_ingerida ADD COLUMN IF NOT EXISTS tenant_id UUID "
            "REFERENCES tenants(id) ON DELETE CASCADE",
            "CREATE INDEX IF NOT EXISTS ix_jurisprudencia_ingerida_tenant_id ON jurisprudencia_ingerida (tenant_id)",
            # Fase 138.2 — `fonte` nasceu VARCHAR(30) só pra caber
            # "stj_dados_abertos" (Fase 138.1); "google_drive:{tenant_id}"
            # sozinho já usa 49 chars e estourava na 1ª inserção real
            # (achado pela verificação empírica desta fase, antes do merge).
            "ALTER TABLE jurisprudencia_ingerida ALTER COLUMN fonte TYPE VARCHAR(80)",
            "ALTER TABLE sync_runs ALTER COLUMN fonte TYPE VARCHAR(80)",
            # Fase 138.4 — tese jurídica (tabela `teses`, nova, criada pelo
            # create_all acima) linkada ao processo — NULL continua
            # significando "sem tese definida", zero regressão.
            "ALTER TABLE legal_processes ADD COLUMN IF NOT EXISTS tese_id UUID "
            "REFERENCES teses(id) ON DELETE SET NULL",
            "CREATE INDEX IF NOT EXISTS ix_legal_processes_tese_id ON legal_processes (tese_id)",
            # Fase 141 — storage de documentos migra de base64-no-Postgres pra
            # object storage S3-compatível (ver CLAUDE.md "Storage de
            # documentos"). NULL nas 3 colunas = binário segue inline em
            # arquivo_url como sempre (caminho legado, sem backfill nesta
            # fase); setado = bytes vivem no S3 nessa key.
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS arquivo_storage_key VARCHAR(500)",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS arquivo_mimetype VARCHAR(150)",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS arquivo_size_bytes INTEGER",
            # Fase 143 — mesmo padrão, pro logo do timbrado do escritório
            # (TenantConfig.logo_url, achado adjacente da Fase 141).
            "ALTER TABLE tenant_configs ADD COLUMN IF NOT EXISTS logo_storage_key VARCHAR(500)",
            "ALTER TABLE tenant_configs ADD COLUMN IF NOT EXISTS logo_mimetype VARCHAR(150)",
            # Fase 146 — faixas de alerta de vencimento de contrato já enviadas
            # (mesmo padrão de process_deadlines.alertas_enviados, Fase 48)
            "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS alertas_enviados JSONB DEFAULT '[]'::jsonb",
            # Fase 151 — segmento de cliente (PLATINUM/GOLD/SILVER/REGULAR)
            # separado do status de lifecycle (PROSPECTO/ATIVO/INATIVO)
            "ALTER TABLE clients ADD COLUMN IF NOT EXISTS segmento VARCHAR(20)",
            # Fase 153 — endurecimento defensivo: client_interactions não tinha
            # tenant_id (só client_id), violando o invariante de filtro por
            # tenant em profundidade. Nullable pra não quebrar linhas antigas.
            "ALTER TABLE client_interactions ADD COLUMN IF NOT EXISTS tenant_id UUID "
            "REFERENCES tenants(id)",
            # Fase 165 — status de TenantIntegration só mudava no clique manual
            # de "Testar conexão"; estas colunas passam a ser atualizadas em
            # todo uso real da credencial (ver integration_hub.registrar_uso).
            "ALTER TABLE tenant_integrations ADD COLUMN IF NOT EXISTS last_success_at TIMESTAMPTZ",
            "ALTER TABLE tenant_integrations ADD COLUMN IF NOT EXISTS last_error_at TIMESTAMPTZ",
            "ALTER TABLE tenant_integrations ADD COLUMN IF NOT EXISTS last_error_detail VARCHAR(500)",
            # Fase 169.2 — sem task_type/process_id/client_id persistidos,
            # retomar uma chain após aprovação humana (request separado da
            # execução original) não tem como reconstruir o AgentContext.
            # Sem backfill possível (nunca existiu antes) — runs antigos
            # ficam NULL, tratado como "nada a retomar" pelo chain_resume.
            "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS task_type VARCHAR(100)",
            "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS process_id UUID "
            "REFERENCES legal_processes(id)",
            "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS client_id UUID "
            "REFERENCES clients(id)",
            # Fase 170 — coluna nova + backfill que roda em TODO boot (não só
            # na criação): é o que garante "o AFJ sempre tem plano Máximo e é
            # isento" mesmo que alguém edite a linha direto no Postgres — o
            # próximo restart da aplicação restaura o invariante.
            "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS isento BOOLEAN NOT NULL DEFAULT false",
            "UPDATE tenants SET plan = 'MAXIMO', isento = true WHERE slug = 'afj' "
            "AND (plan IS DISTINCT FROM 'MAXIMO' OR isento IS DISTINCT FROM true)",
            # Fase 179 — parte do processo (autor/réu/etc.) pode ser vinculada a
            # um Client já cadastrado, em vez de só texto livre. SET NULL ao
            # apagar o cliente (não CASCADE): a parte continua no histórico do
            # processo, só perde o vínculo.
            "ALTER TABLE process_parties ADD COLUMN IF NOT EXISTS client_id UUID "
            "REFERENCES clients(id) ON DELETE SET NULL",
            "CREATE INDEX IF NOT EXISTS ix_process_parties_client_id ON process_parties (client_id)",
            # Fase 180 — exclusão PERMANENTE de processo/usuário, restrita ao
            # SUPERADMIN (sistema ainda em construção, dado de teste). As FKs
            # abaixo nasceram sem ON DELETE (RESTRICT/NO ACTION), o que
            # bloquearia qualquer DELETE real enquanto existisse 1 linha
            # referenciando o processo/usuário. Reaplicado em TODO boot
            # (DROP+ADD do mesmo nome de constraint) pra garantir o invariante
            # mesmo que alguém rode uma migration manual divergente — mesmo
            # padrão de "roda em todo boot" já usado pelo backfill da Fase 170.
            #
            # Filhos diretos de legal_processes que ainda não cascateavam
            # (CASCADE — apaga o processo, apaga o filho junto):
            "ALTER TABLE agent_runs DROP CONSTRAINT IF EXISTS agent_runs_process_id_fkey",
            "ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_process_id_fkey "
            "FOREIGN KEY (process_id) REFERENCES legal_processes(id) ON DELETE CASCADE",
            "ALTER TABLE approvals DROP CONSTRAINT IF EXISTS approvals_run_id_fkey",
            "ALTER TABLE approvals ADD CONSTRAINT approvals_run_id_fkey "
            "FOREIGN KEY (run_id) REFERENCES agent_runs(id) ON DELETE CASCADE",
            "ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_process_id_fkey",
            "ALTER TABLE documents ADD CONSTRAINT documents_process_id_fkey "
            "FOREIGN KEY (process_id) REFERENCES legal_processes(id) ON DELETE CASCADE",
            "ALTER TABLE petitions DROP CONSTRAINT IF EXISTS petitions_process_id_fkey",
            "ALTER TABLE petitions ADD CONSTRAINT petitions_process_id_fkey "
            "FOREIGN KEY (process_id) REFERENCES legal_processes(id) ON DELETE CASCADE",
            "ALTER TABLE financial_entries DROP CONSTRAINT IF EXISTS financial_entries_process_id_fkey",
            "ALTER TABLE financial_entries ADD CONSTRAINT financial_entries_process_id_fkey "
            "FOREIGN KEY (process_id) REFERENCES legal_processes(id) ON DELETE CASCADE",
            "ALTER TABLE billing_invoices DROP CONSTRAINT IF EXISTS billing_invoices_process_id_fkey",
            "ALTER TABLE billing_invoices ADD CONSTRAINT billing_invoices_process_id_fkey "
            "FOREIGN KEY (process_id) REFERENCES legal_processes(id) ON DELETE CASCADE",
            #
            # Referências a `users` que hoje só "autoria"/"responsável" (SET
            # NULL — apagar o usuário não pode apagar processo/documento/
            # financeiro/etc. real, só desvincula a autoria):
            "ALTER TABLE legal_processes DROP CONSTRAINT IF EXISTS legal_processes_responsavel_id_fkey",
            "ALTER TABLE legal_processes ADD CONSTRAINT legal_processes_responsavel_id_fkey "
            "FOREIGN KEY (responsavel_id) REFERENCES users(id) ON DELETE SET NULL",
            "ALTER TABLE process_deadlines DROP CONSTRAINT IF EXISTS process_deadlines_responsavel_id_fkey",
            "ALTER TABLE process_deadlines ADD CONSTRAINT process_deadlines_responsavel_id_fkey "
            "FOREIGN KEY (responsavel_id) REFERENCES users(id) ON DELETE SET NULL",
            "ALTER TABLE agent_runs DROP CONSTRAINT IF EXISTS agent_runs_triggered_by_fkey",
            "ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_triggered_by_fkey "
            "FOREIGN KEY (triggered_by) REFERENCES users(id) ON DELETE SET NULL",
            "ALTER TABLE approvals DROP CONSTRAINT IF EXISTS approvals_assignee_id_fkey",
            "ALTER TABLE approvals ADD CONSTRAINT approvals_assignee_id_fkey "
            "FOREIGN KEY (assignee_id) REFERENCES users(id) ON DELETE SET NULL",
            "ALTER TABLE approvals DROP CONSTRAINT IF EXISTS approvals_approved_by_fkey",
            "ALTER TABLE approvals ADD CONSTRAINT approvals_approved_by_fkey "
            "FOREIGN KEY (approved_by) REFERENCES users(id) ON DELETE SET NULL",
            "ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_created_by_fkey",
            "ALTER TABLE documents ADD CONSTRAINT documents_created_by_fkey "
            "FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL",
            "ALTER TABLE document_versions DROP CONSTRAINT IF EXISTS document_versions_changed_by_fkey",
            "ALTER TABLE document_versions ADD CONSTRAINT document_versions_changed_by_fkey "
            "FOREIGN KEY (changed_by) REFERENCES users(id) ON DELETE SET NULL",
            "ALTER TABLE petitions DROP CONSTRAINT IF EXISTS petitions_reviewed_by_fkey",
            "ALTER TABLE petitions ADD CONSTRAINT petitions_reviewed_by_fkey "
            "FOREIGN KEY (reviewed_by) REFERENCES users(id) ON DELETE SET NULL",
            "ALTER TABLE petition_templates DROP CONSTRAINT IF EXISTS petition_templates_created_by_fkey",
            "ALTER TABLE petition_templates ADD CONSTRAINT petition_templates_created_by_fkey "
            "FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL",
            "ALTER TABLE financial_entries DROP CONSTRAINT IF EXISTS financial_entries_created_by_fkey",
            "ALTER TABLE financial_entries ADD CONSTRAINT financial_entries_created_by_fkey "
            "FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL",
            "ALTER TABLE billing_invoices DROP CONSTRAINT IF EXISTS billing_invoices_created_by_fkey",
            "ALTER TABLE billing_invoices ADD CONSTRAINT billing_invoices_created_by_fkey "
            "FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL",
            "ALTER TABLE clients DROP CONSTRAINT IF EXISTS clients_responsavel_id_fkey",
            "ALTER TABLE clients ADD CONSTRAINT clients_responsavel_id_fkey "
            "FOREIGN KEY (responsavel_id) REFERENCES users(id) ON DELETE SET NULL",
            "ALTER TABLE client_interactions DROP CONSTRAINT IF EXISTS client_interactions_user_id_fkey",
            "ALTER TABLE client_interactions ADD CONSTRAINT client_interactions_user_id_fkey "
            "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL",
            "ALTER TABLE opportunities DROP CONSTRAINT IF EXISTS opportunities_responsavel_id_fkey",
            "ALTER TABLE opportunities ADD CONSTRAINT opportunities_responsavel_id_fkey "
            "FOREIGN KEY (responsavel_id) REFERENCES users(id) ON DELETE SET NULL",
            # custom_agents.created_by nasceu NOT NULL — precisa aceitar NULL
            # antes da constraint SET NULL fazer sentido (senão o delete falha
            # com not-null violation em vez de suceder desvinculando).
            "ALTER TABLE custom_agents ALTER COLUMN created_by DROP NOT NULL",
            "ALTER TABLE custom_agents DROP CONSTRAINT IF EXISTS custom_agents_created_by_fkey",
            "ALTER TABLE custom_agents ADD CONSTRAINT custom_agents_created_by_fkey "
            "FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL",
            "ALTER TABLE custom_agents DROP CONSTRAINT IF EXISTS custom_agents_approved_by_fkey",
            "ALTER TABLE custom_agents ADD CONSTRAINT custom_agents_approved_by_fkey "
            "FOREIGN KEY (approved_by) REFERENCES users(id) ON DELETE SET NULL",
            "ALTER TABLE agent_prompt_configs DROP CONSTRAINT IF EXISTS agent_prompt_configs_updated_by_fkey",
            "ALTER TABLE agent_prompt_configs ADD CONSTRAINT agent_prompt_configs_updated_by_fkey "
            "FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL",
            "ALTER TABLE agent_prompt_versions DROP CONSTRAINT IF EXISTS agent_prompt_versions_changed_by_fkey",
            "ALTER TABLE agent_prompt_versions ADD CONSTRAINT agent_prompt_versions_changed_by_fkey "
            "FOREIGN KEY (changed_by) REFERENCES users(id) ON DELETE SET NULL",
            "ALTER TABLE agent_attachments DROP CONSTRAINT IF EXISTS agent_attachments_uploaded_by_fkey",
            "ALTER TABLE agent_attachments ADD CONSTRAINT agent_attachments_uploaded_by_fkey "
            "FOREIGN KEY (uploaded_by) REFERENCES users(id) ON DELETE SET NULL",
            "ALTER TABLE integrity_reports DROP CONSTRAINT IF EXISTS integrity_reports_created_by_fkey",
            "ALTER TABLE integrity_reports ADD CONSTRAINT integrity_reports_created_by_fkey "
            "FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL",
            "ALTER TABLE integrity_reports DROP CONSTRAINT IF EXISTS integrity_reports_resolved_by_fkey",
            "ALTER TABLE integrity_reports ADD CONSTRAINT integrity_reports_resolved_by_fkey "
            "FOREIGN KEY (resolved_by) REFERENCES users(id) ON DELETE SET NULL",
            "ALTER TABLE tenant_payments DROP CONSTRAINT IF EXISTS tenant_payments_registrado_por_fkey",
            "ALTER TABLE tenant_payments ADD CONSTRAINT tenant_payments_registrado_por_fkey "
            "FOREIGN KEY (registrado_por) REFERENCES users(id) ON DELETE SET NULL",
            # Trava de segurança: enquanto False, SUPERADMIN pode excluir de
            # verdade; True ("em produção") bloqueia os 2 endpoints de
            # exclusão permanente (ver processes.py/users.py).
            "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS em_producao BOOLEAN NOT NULL DEFAULT false",
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
