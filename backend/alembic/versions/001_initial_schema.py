"""Esquema inicial completo AFJ CORE SYSTEM.

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── Extensões ────────────────────────────────────────────────────────────
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # ─── users ────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("oab_number", sa.String(20)),
        sa.Column("oab_uf", sa.String(2)),
        sa.Column("role", sa.String(50), nullable=False, server_default="ASSISTENTE"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("mfa_secret", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_users_email", "users", ["email"], unique=True)

    # ─── user_permissions ─────────────────────────────────────────────────────
    op.create_table(
        "user_permissions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource", sa.String(100), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "resource", "action", name="uq_user_permissions"),
    )

    # ─── sessions ─────────────────────────────────────────────────────────────
    op.create_table(
        "sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("user_agent", sa.String(500)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_sessions_token_hash", "sessions", ["token_hash"], unique=True)

    # ─── clients ──────────────────────────────────────────────────────────────
    op.create_table(
        "clients",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tipo", sa.String(2), nullable=False),  # PF, PJ
        sa.Column("cpf", sa.Text),   # encrypted at app layer
        sa.Column("cnpj", sa.Text),  # encrypted at app layer
        sa.Column("nome_completo", sa.String(500), nullable=False),
        sa.Column("razao_social", sa.String(500)),
        sa.Column("email", sa.String(255), index=True),
        sa.Column("telefone", sa.String(30)),
        sa.Column("whatsapp", sa.String(30)),
        sa.Column("responsavel_id", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("origem", sa.String(100)),
        sa.Column("status", sa.String(20), server_default="PROSPECTO"),  # PROSPECTO, ATIVO, INATIVO
        sa.Column("lgpd_consent", sa.Boolean, server_default="false"),
        sa.Column("lgpd_consent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_clients_email", "clients", ["email"])
    op.create_index("idx_clients_status", "clients", ["status"])

    # ─── client_contacts ──────────────────────────────────────────────────────
    op.create_table(
        "client_contacts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nome", sa.String(255), nullable=False),
        sa.Column("cargo", sa.String(100)),
        sa.Column("email", sa.String(255)),
        sa.Column("telefone", sa.String(30)),
        sa.Column("is_primary", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ─── client_interactions ──────────────────────────────────────────────────
    op.create_table(
        "client_interactions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("tipo", sa.String(50)),
        sa.Column("descricao", sa.Text),
        sa.Column("metadata_json", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_client_interactions_client", "client_interactions", ["client_id"])

    # ─── legal_processes ──────────────────────────────────────────────────────
    op.create_table(
        "legal_processes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("numero_cnj", sa.String(25), unique=True),
        sa.Column("numero_original", sa.String(50)),
        sa.Column("tribunal", sa.String(100), nullable=False),
        sa.Column("vara", sa.String(255)),
        sa.Column("comarca", sa.String(255)),
        sa.Column("uf", sa.String(2)),
        sa.Column("tipo_acao", sa.String(255)),
        sa.Column("area_direito", sa.String(50)),  # CIVIL, TRABALHISTA, etc.
        sa.Column("fase", sa.String(100)),
        sa.Column("situacao", sa.String(20), server_default="ATIVO"),  # ATIVO, SUSPENSO, ARQUIVADO, ENCERRADO
        sa.Column("valor_causa", sa.Numeric(15, 2)),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id")),
        sa.Column("responsavel_id", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("oab_responsavel", sa.String(30)),
        sa.Column("parte_contraria", sa.String(500)),
        sa.Column("polo", sa.String(10)),  # AUTOR, REU
        sa.Column("distribuicao_data", sa.Date),
        sa.Column("ultimo_andamento_at", sa.DateTime(timezone=True)),
        sa.Column("proximo_prazo_at", sa.DateTime(timezone=True)),
        sa.Column("monitoring_active", sa.Boolean, server_default="true"),
        sa.Column("last_polled_at", sa.DateTime(timezone=True)),
        sa.Column("metadata_json", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_processes_numero_cnj", "legal_processes", ["numero_cnj"], unique=True)
    op.create_index("idx_processes_monitoring", "legal_processes", ["monitoring_active", "proximo_prazo_at"])
    op.create_index("idx_processes_client", "legal_processes", ["client_id"])

    # ─── process_movements ────────────────────────────────────────────────────
    op.create_table(
        "process_movements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("process_id", UUID(as_uuid=True), sa.ForeignKey("legal_processes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("data_movimento", sa.DateTime(timezone=True), nullable=False),
        sa.Column("descricao", sa.Text, nullable=False),
        sa.Column("tipo", sa.String(100)),
        sa.Column("documento_url", sa.Text),
        sa.Column("raw_html", sa.Text),
        sa.Column("ai_summary", sa.Text),
        sa.Column("notified_users", ARRAY(UUID(as_uuid=True))),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_movements_process_date", "process_movements", ["process_id", "data_movimento"])

    # ─── process_deadlines ────────────────────────────────────────────────────
    op.create_table(
        "process_deadlines",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("process_id", UUID(as_uuid=True), sa.ForeignKey("legal_processes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("movement_id", UUID(as_uuid=True), sa.ForeignKey("process_movements.id")),
        sa.Column("descricao", sa.Text, nullable=False),
        sa.Column("data_prazo", sa.Date, nullable=False),
        sa.Column("data_fatal", sa.Date),
        sa.Column("tipo", sa.String(100)),
        sa.Column("status", sa.String(20), server_default="PENDENTE"),  # PENDENTE, CUMPRIDO, PERDIDO
        sa.Column("responsavel_id", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "idx_deadlines_date",
        "process_deadlines", ["data_prazo"],
        postgresql_where=sa.text("status = 'PENDENTE'"),
    )

    # ─── process_parties ──────────────────────────────────────────────────────
    op.create_table(
        "process_parties",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("process_id", UUID(as_uuid=True), sa.ForeignKey("legal_processes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tipo", sa.String(20)),  # AUTOR, REU, ADVOGADO, JUIZ
        sa.Column("nome", sa.String(500)),
        sa.Column("cpf_cnpj", sa.String(30)),
        sa.Column("oab", sa.String(30)),
        sa.Column("polo", sa.String(10)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ─── agent_runs ───────────────────────────────────────────────────────────
    op.create_table(
        "agent_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("agent_name", sa.String(100), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True)),
        sa.Column("trigger_type", sa.String(50)),  # MANUAL, SCHEDULED, WEBHOOK, CHAINED
        sa.Column("triggered_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("input_data", JSONB, nullable=False, server_default="{}"),
        sa.Column("output_data", JSONB),
        sa.Column("status", sa.String(30), server_default="RUNNING"),
        sa.Column("error_message", sa.Text),
        sa.Column("tokens_used", sa.Integer),
        sa.Column("cost_usd", sa.Numeric(10, 6)),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("requires_approval", sa.Boolean, server_default="false"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_agent_runs_name", "agent_runs", ["agent_name", "started_at"])
    op.create_index("idx_agent_runs_status", "agent_runs", ["status"])

    # ─── agent_steps ──────────────────────────────────────────────────────────
    op.create_table(
        "agent_steps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_number", sa.Integer, nullable=False),
        sa.Column("step_name", sa.String(100)),
        sa.Column("tool_used", sa.String(100)),
        sa.Column("input_json", JSONB),
        sa.Column("output_json", JSONB),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_agent_steps_run", "agent_steps", ["run_id"])

    # ─── approvals ────────────────────────────────────────────────────────────
    op.create_table(
        "approvals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("agent_runs.id")),
        sa.Column("tipo", sa.String(100)),
        sa.Column("titulo", sa.Text, nullable=False),
        sa.Column("descricao", sa.Text),
        sa.Column("ai_suggestion", JSONB),
        sa.Column("prioridade", sa.String(10), server_default="NORMAL"),  # LOW, NORMAL, HIGH, URGENT
        sa.Column("status", sa.String(20), server_default="PENDENTE"),    # PENDENTE, APROVADO, REJEITADO
        sa.Column("assignee_id", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("approved_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("rejection_reason", sa.Text),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "idx_approvals_status",
        "approvals", ["status", "assignee_id"],
        postgresql_where=sa.text("status = 'PENDENTE'"),
    )

    # ─── agent_memory ─────────────────────────────────────────────────────────
    op.create_table(
        "agent_memory",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("agent_name", sa.String(100)),
        sa.Column("memory_type", sa.String(50)),  # EPISODIC, SEMANTIC, PROCEDURAL
        sa.Column("key", sa.String(255)),
        sa.Column("value_json", JSONB),
        sa.Column("context_id", UUID(as_uuid=True)),
        sa.Column("relevance", sa.Numeric(3, 2), server_default="1.0"),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_agent_memory_key", "agent_memory", ["agent_name", "key"])

    # ─── documents ────────────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("process_id", UUID(as_uuid=True), sa.ForeignKey("legal_processes.id")),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id")),
        sa.Column("agent_run_id", UUID(as_uuid=True), sa.ForeignKey("agent_runs.id")),
        sa.Column("tipo", sa.String(50), nullable=False),
        sa.Column("titulo", sa.String(500), nullable=False),
        sa.Column("conteudo_texto", sa.Text),
        sa.Column("conteudo_html", sa.Text),
        sa.Column("arquivo_url", sa.Text),
        sa.Column("arquivo_hash", sa.String(64)),  # SHA-256
        sa.Column("versao", sa.Integer, server_default="1"),
        sa.Column("status", sa.String(20), server_default="RASCUNHO"),  # RASCUNHO, REVISAO, APROVADO, PROTOCOLADO
        sa.Column("gerado_por_ia", sa.Boolean, server_default="false"),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_documents_process", "documents", ["process_id"])
    op.create_index("idx_documents_client", "documents", ["client_id"])
    op.create_index("idx_documents_status", "documents", ["status"])

    # ─── document_versions ────────────────────────────────────────────────────
    op.create_table(
        "document_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("versao", sa.Integer, nullable=False),
        sa.Column("conteudo_html", sa.Text),
        sa.Column("changed_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("change_summary", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ─── petitions ────────────────────────────────────────────────────────────
    op.create_table(
        "petitions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("process_id", UUID(as_uuid=True), sa.ForeignKey("legal_processes.id")),
        sa.Column("tipo_peticao", sa.String(100)),
        sa.Column("template_used", sa.String(100)),
        sa.Column("ai_prompt", sa.Text),
        sa.Column("ai_model", sa.String(100)),
        sa.Column("ai_tokens_used", sa.Integer),
        sa.Column("review_status", sa.String(20)),  # PENDENTE, APROVADO, REJEITADO
        sa.Column("reviewed_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("review_notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ─── contracts ────────────────────────────────────────────────────────────
    op.create_table(
        "contracts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id")),
        sa.Column("tipo", sa.String(100)),
        sa.Column("valor_total", sa.Numeric(15, 2)),
        sa.Column("data_inicio", sa.Date),
        sa.Column("data_fim", sa.Date),
        sa.Column("status", sa.String(20), server_default="RASCUNHO"),
        sa.Column("assinaturas", JSONB, server_default="[]"),
        sa.Column("renovacao_auto", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ─── financial_entries ────────────────────────────────────────────────────
    op.create_table(
        "financial_entries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("tipo", sa.String(10), nullable=False),  # RECEITA, DESPESA
        sa.Column("categoria", sa.String(100)),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id")),
        sa.Column("process_id", UUID(as_uuid=True), sa.ForeignKey("legal_processes.id")),
        sa.Column("descricao", sa.String(500), nullable=False),
        sa.Column("valor", sa.Numeric(15, 2), nullable=False),
        sa.Column("data_vencimento", sa.Date),
        sa.Column("data_pagamento", sa.Date),
        sa.Column("status", sa.String(20), server_default="PENDENTE"),  # PENDENTE, PAGO, CANCELADO
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_financial_tipo_status", "financial_entries", ["tipo", "status"])
    op.create_index("idx_financial_vencimento", "financial_entries", ["data_vencimento"])

    # ─── billing_invoices ─────────────────────────────────────────────────────
    op.create_table(
        "billing_invoices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id")),
        sa.Column("process_id", UUID(as_uuid=True), sa.ForeignKey("legal_processes.id")),
        sa.Column("numero", sa.String(50), unique=True),
        sa.Column("periodo_inicio", sa.Date),
        sa.Column("periodo_fim", sa.Date),
        sa.Column("valor_total", sa.Numeric(15, 2), nullable=False),
        sa.Column("status", sa.String(20), server_default="ABERTO"),
        sa.Column("emitido_em", sa.DateTime(timezone=True)),
        sa.Column("pago_em", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ─── notifications ────────────────────────────────────────────────────────
    op.create_table(
        "notifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tipo", sa.String(50), nullable=False),
        sa.Column("titulo", sa.String(255), nullable=False),
        sa.Column("mensagem", sa.Text),
        sa.Column("link", sa.String(500)),
        sa.Column("lida", sa.Boolean, server_default="false"),
        sa.Column("priority", sa.String(10), server_default="NORMAL"),
        sa.Column("metadata_json", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_notifications_unread", "notifications", ["user_id", "lida"])

    # ─── audit_logs (IMUTÁVEL) ────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("event_id", UUID(as_uuid=True), nullable=False, unique=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True)),
        sa.Column("agent_name", sa.String(100)),
        sa.Column("run_id", UUID(as_uuid=True)),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100)),
        sa.Column("resource_id", sa.String(255)),
        sa.Column("old_value", JSONB),
        sa.Column("new_value", JSONB),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("success", sa.Boolean, server_default="true"),
        sa.Column("error_detail", sa.Text),
        sa.Column("contains_pii", sa.Boolean, server_default="false"),
        sa.Column("legal_basis", sa.String(255)),
    )
    op.create_index("idx_audit_timestamp", "audit_logs", ["timestamp"])
    op.create_index("idx_audit_user", "audit_logs", ["user_id", "timestamp"])
    op.create_index("idx_audit_resource", "audit_logs", ["resource_type", "resource_id"])

    # Trigger que impede UPDATE/DELETE em audit_logs (imutabilidade)
    op.execute("""
        CREATE OR REPLACE FUNCTION audit_logs_immutable()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs são imutáveis. Operação % não permitida.', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_audit_logs_immutable
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable();
    """)

    # ─── lgpd_consent_records ─────────────────────────────────────────────────
    op.create_table(
        "lgpd_consent_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("client_id", UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE")),
        sa.Column("tipo_dado", sa.String(100)),
        sa.Column("consentimento", sa.Boolean, nullable=False),
        sa.Column("base_legal", sa.String(255)),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("texto_versao", sa.Text),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_lgpd_client", "lgpd_consent_records", ["client_id", "timestamp"])


def downgrade() -> None:
    # Remover trigger primeiro
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_immutable ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS audit_logs_immutable()")

    tables = [
        "lgpd_consent_records",
        "audit_logs",
        "notifications",
        "billing_invoices",
        "financial_entries",
        "contracts",
        "petitions",
        "document_versions",
        "documents",
        "agent_memory",
        "approvals",
        "agent_steps",
        "agent_runs",
        "process_parties",
        "process_deadlines",
        "process_movements",
        "legal_processes",
        "client_interactions",
        "client_contacts",
        "clients",
        "sessions",
        "user_permissions",
        "users",
    ]
    for table in tables:
        op.drop_table(table)
