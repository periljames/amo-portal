"""Align Platform Operations incident lifecycle with NOC operating states.

Revision ID: platform_ops_20260809_incident_lifecycle
Revises: platform_ops_20260808_control_data
Create Date: 2026-08-09
"""

from alembic import op
import sqlalchemy as sa


revision = "platform_ops_20260809_incident_lifecycle"
down_revision = "platform_ops_20260808_control_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("platform_incidents", sa.Column("investigated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("platform_incidents", sa.Column("investigated_by", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_platform_incidents_investigated_by_users",
        "platform_incidents",
        "users",
        ["investigated_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute("UPDATE platform_incidents SET state = 'OPEN' WHERE state = 'DETECTED'")
    op.execute("UPDATE platform_incident_events SET event_type = 'OPEN' WHERE event_type = 'DETECTED'")
    op.alter_column(
        "platform_incidents",
        "state",
        existing_type=sa.String(length=32),
        existing_nullable=False,
        server_default="OPEN",
    )


def downgrade() -> None:
    op.execute("UPDATE platform_incidents SET state = 'DETECTED' WHERE state = 'OPEN'")
    op.execute("UPDATE platform_incident_events SET event_type = 'DETECTED' WHERE event_type = 'OPEN'")
    # INVESTIGATING has no exact legacy equivalent; preserve evidence by mapping it
    # to ACKNOWLEDGED rather than silently skipping the state transition.
    op.execute("UPDATE platform_incidents SET state = 'ACKNOWLEDGED' WHERE state = 'INVESTIGATING'")
    op.execute("UPDATE platform_incident_events SET event_type = 'ACKNOWLEDGED' WHERE event_type = 'INVESTIGATING'")
    op.alter_column(
        "platform_incidents",
        "state",
        existing_type=sa.String(length=32),
        existing_nullable=False,
        server_default="DETECTED",
    )
    op.drop_constraint("fk_platform_incidents_investigated_by_users", "platform_incidents", type_="foreignkey")
    op.drop_column("platform_incidents", "investigated_by")
    op.drop_column("platform_incidents", "investigated_at")
