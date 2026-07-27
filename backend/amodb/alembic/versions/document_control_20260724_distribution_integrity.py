"""Enforce Document Control distribution recipient integrity.

Revision ID: document_control_20260724_distribution_integrity
Revises: document_control_20260724_scope_fk
Create Date: 2026-07-24
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "document_control_20260724_distribution_integrity"
down_revision = "document_control_20260724_scope_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = "document_distribution_campaign_recipients"
    if not inspector.has_table(table_name):
        return

    duplicate_count = int(
        bind.execute(
            text(
                """
                SELECT count(*)
                FROM (
                    SELECT campaign_id, recipient_user_id
                    FROM document_distribution_campaign_recipients
                    WHERE recipient_user_id IS NOT NULL
                    GROUP BY campaign_id, recipient_user_id
                    HAVING count(*) > 1
                ) duplicates
                """
            )
        ).scalar()
        or 0
    )
    if duplicate_count:
        raise RuntimeError(
            "Duplicate Document Control distribution recipients exist. "
            "Resolve them before rerunning Alembic."
        )

    op.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                uq_document_distribution_campaign_recipient_active
            ON document_distribution_campaign_recipients (campaign_id, recipient_user_id)
            WHERE recipient_user_id IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    op.execute(
        text(
            "DROP INDEX IF EXISTS uq_document_distribution_campaign_recipient_active"
        )
    )
