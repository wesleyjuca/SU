"""Add multi-tenant support: tenants table and tenant_id columns.

Revision ID: 002_add_tenant
Revises: 001_initial_schema
Create Date: 2026-05-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "002_add_tenant"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Tabela tenants ────────────────────────────────────────────────────────
    op.create_table(
        "tenants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True, index=True),
        sa.Column("subdomain", sa.String(100), unique=True, nullable=True),
        sa.Column("plan", sa.String(50), server_default="STANDARD"),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("max_users", sa.Integer, server_default="10"),
        sa.Column("max_storage_gb", sa.Integer, server_default="50"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ── Tabela tenant_configs ────────────────────────────────────────────────
    op.create_table(
        "tenant_configs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("primary_color", sa.String(20), server_default="#C9A84C"),
        sa.Column("secondary_color", sa.String(20), server_default="#1A1A1A"),
        sa.Column("accent_color", sa.String(20), server_default="#F5F0E8"),
        sa.Column("logo_url", sa.Text, nullable=True),
        sa.Column("logo_dark_url", sa.Text, nullable=True),
        sa.Column("favicon_url", sa.Text, nullable=True),
        sa.Column("app_name", sa.String(255), server_default="AFJ CORE"),
        sa.Column("nav_config", JSONB, server_default="[]"),
        sa.Column("dashboard_widgets", JSONB, server_default="[]"),
        sa.Column(
            "modules_enabled",
            JSONB,
            server_default='{"processos":true,"peticoes":true,"clientes":true,"financeiro":true,"agentes":true,"visual_law":true}',
        ),
        sa.Column("document_templates", JSONB, server_default="{}"),
        sa.Column("custom_css", sa.Text, nullable=True),
        sa.Column("metadata", JSONB, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ── Adicionar tenant_id nas tabelas existentes (nullable) ─────────────────
    for table in ("users", "clients", "legal_processes", "documents", "financial_entries", "agent_runs", "approvals", "notifications"):
        op.add_column(table, sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=True))

    # audit_logs sem FK (imutável)
    op.add_column("audit_logs", sa.Column("tenant_id", UUID(as_uuid=True), nullable=True))

    # ── Índices de performance ────────────────────────────────────────────────
    op.create_index("idx_users_tenant", "users", ["tenant_id"])
    op.create_index("idx_clients_tenant", "clients", ["tenant_id"])
    op.create_index("idx_processes_tenant", "legal_processes", ["tenant_id"])
    op.create_index("idx_documents_tenant", "documents", ["tenant_id"])
    op.create_index("idx_financial_tenant", "financial_entries", ["tenant_id"])
    op.create_index("idx_agent_runs_tenant", "agent_runs", ["tenant_id"])

    # ── Tenant padrão AFJ ─────────────────────────────────────────────────────
    op.execute(
        """
        INSERT INTO tenants (name, slug, plan)
        VALUES ('Almeida, Freire & Jucá Advogados', 'afj', 'ENTERPRISE')
        """
    )
    op.execute(
        """
        INSERT INTO tenant_configs (tenant_id, app_name)
        SELECT id, 'AFJ CORE' FROM tenants WHERE slug = 'afj'
        """
    )

    # ── Migrar dados existentes para o tenant AFJ ─────────────────────────────
    for table in ("users", "clients", "legal_processes", "documents", "financial_entries", "agent_runs", "approvals", "notifications", "audit_logs"):
        op.execute(
            f"""
            UPDATE {table}
            SET tenant_id = (SELECT id FROM tenants WHERE slug = 'afj')
            WHERE tenant_id IS NULL
            """
        )


def downgrade() -> None:
    for table in ("users", "clients", "legal_processes", "documents", "financial_entries", "agent_runs", "approvals", "notifications", "audit_logs"):
        op.drop_column(table, "tenant_id")

    op.drop_table("tenant_configs")
    op.drop_table("tenants")
