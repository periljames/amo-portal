"""durable replay commands and item claims

Revision ID: resilience_260816_commands
Revises: resilience_260816_sessions
"""
from alembic import op
import sqlalchemy as sa

revision = "resilience_260816_commands"
down_revision = "resilience_260816_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portal_replay_commands",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("amo_id", sa.String(36), sa.ForeignKey("amos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("method", sa.String(12), nullable=False),
        sa.Column("route_key", sa.String(200), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("expected_revision", sa.String(128)),
        sa.Column("status", sa.String(24), nullable=False, server_default="PROCESSING"),
        sa.Column("response_status", sa.Integer()),
        sa.Column("response_json", sa.JSON()),
        sa.Column("error_code", sa.String(96)),
        sa.Column("error_detail", sa.Text()),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("lease_owner", sa.String(128)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("amo_id", "actor_user_id", "method", "route_key", "idempotency_key", name="uq_portal_replay_command_scope"),
    )
    op.create_index("ix_portal_replay_command_status", "portal_replay_commands", ["status", "lease_expires_at"])
    op.create_index("ix_portal_replay_command_tenant_created", "portal_replay_commands", ["amo_id", "created_at"])
    op.add_column("workforce_bulk_operation_items", sa.Column("claim_token", sa.String(64)))
    op.add_column("workforce_bulk_operation_items", sa.Column("claimed_by", sa.String(128)))
    op.add_column("workforce_bulk_operation_items", sa.Column("claim_expires_at", sa.DateTime(timezone=True)))
    op.create_index("ix_workforce_bulk_item_claim", "workforce_bulk_operation_items", ["status", "claim_expires_at", "sequence"])


def downgrade() -> None:
    op.drop_index("ix_workforce_bulk_item_claim", table_name="workforce_bulk_operation_items")
    op.drop_column("workforce_bulk_operation_items", "claim_expires_at")
    op.drop_column("workforce_bulk_operation_items", "claimed_by")
    op.drop_column("workforce_bulk_operation_items", "claim_token")
    op.drop_index("ix_portal_replay_command_tenant_created", table_name="portal_replay_commands")
    op.drop_index("ix_portal_replay_command_status", table_name="portal_replay_commands")
    op.drop_table("portal_replay_commands")
