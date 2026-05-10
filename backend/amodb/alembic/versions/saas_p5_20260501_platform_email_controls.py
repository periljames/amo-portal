"""platform email settings and merge SaaS/QMS heads

Revision ID: saas_p5_20260501
Revises: f4a5b6c7d8e9, qms_p4_20260501, amo_20260501_gsu_scope
Create Date: 2026-05-01
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "saas_p5_20260501"
down_revision: Union[str, Sequence[str], None] = ("f4a5b6c7d8e9", "qms_p4_20260501", "amo_20260501_gsu_scope")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMAIL_COLUMNS: list[sa.Column] = [
    sa.Column("email_provider", sa.String(length=64), nullable=True),
    sa.Column("email_from_name", sa.String(length=255), nullable=True),
    sa.Column("email_from_email", sa.String(length=255), nullable=True),
    sa.Column("email_reply_to", sa.String(length=255), nullable=True),
    sa.Column("smtp_host", sa.String(length=255), nullable=True),
    sa.Column("smtp_port", sa.Integer(), nullable=True),
    sa.Column("smtp_username", sa.String(length=255), nullable=True),
    sa.Column("smtp_password_secret", sa.Text(), nullable=True),
    sa.Column("smtp_use_tls", sa.Boolean(), nullable=True),
    sa.Column("smtp_allow_self_signed", sa.Boolean(), nullable=True),
    sa.Column("smtp_test_recipient", sa.String(length=255), nullable=True),
    sa.Column("support_email", sa.String(length=255), nullable=True),
    sa.Column("ops_alert_email", sa.String(length=255), nullable=True),
]


def _table_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    existing = _table_columns("platform_settings")
    if not existing:
        return
    for column in EMAIL_COLUMNS:
        if column.name not in existing:
            op.add_column("platform_settings", column.copy())


def downgrade() -> None:
    existing = _table_columns("platform_settings")
    if not existing:
        return
    for column in reversed(EMAIL_COLUMNS):
        if column.name in existing:
            op.drop_column("platform_settings", column.name)
