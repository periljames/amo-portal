"""Add immutable Procurement document linkage and retained evidence records.

Revision ID: procure_20260803_docs
Revises: 7d9e0a1b2c3d
Create Date: 2026-08-03
"""

from __future__ import annotations

from alembic import op

from amodb.apps.procurement import document_models


revision = "procure_20260803_docs"
down_revision = "7d9e0a1b2c3d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    document_models.ProcurementDocument.__table__.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    document_models.ProcurementDocument.__table__.drop(op.get_bind(), checkfirst=True)
