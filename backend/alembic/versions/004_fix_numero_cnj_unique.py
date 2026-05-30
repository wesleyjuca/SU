"""fix numero_cnj unique constraint — tenant-scoped instead of global

Revision ID: 004
Revises: 003
Create Date: 2026-05-30
"""
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade():
    # Remove a constraint global única em numero_cnj (se existir)
    op.execute("""
        ALTER TABLE legal_processes
        DROP CONSTRAINT IF EXISTS legal_processes_numero_cnj_key
    """)

    # Adicionar índice único composto (tenant_id, numero_cnj) excluindo NULLs
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_tenant_processo_cnj
        ON legal_processes (tenant_id, numero_cnj)
        WHERE numero_cnj IS NOT NULL
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_tenant_processo_cnj")
    op.execute("""
        ALTER TABLE legal_processes
        ADD CONSTRAINT legal_processes_numero_cnj_key UNIQUE (numero_cnj)
    """)
