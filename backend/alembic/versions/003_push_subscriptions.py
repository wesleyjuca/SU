"""Migration 003: push_subscriptions table para Web Push (VAPID)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "push_subscriptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=True),
        sa.Column("endpoint", sa.Text(), unique=True, nullable=False),
        sa.Column("p256dh", sa.Text(), nullable=False),
        sa.Column("auth", sa.Text(), nullable=False),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_push_sub_user", "push_subscriptions", ["user_id"])
    op.create_index("idx_push_sub_tenant", "push_subscriptions", ["tenant_id"])


def downgrade():
    op.drop_index("idx_push_sub_tenant", table_name="push_subscriptions")
    op.drop_index("idx_push_sub_user", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
