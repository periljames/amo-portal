"""sync quality_cars workflow columns with ORM model

Revision ID: d6e7f8a9b0c1
Revises: b7c8d9e0f1a3
Create Date: 2026-02-15 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, Sequence[str], None] = "b7c8d9e0f1a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table(table_name):
        return set()
    return {col["name"] for col in insp.get_columns(table_name)}


def _table_indexes(table_name: str) -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table(table_name):
        return set()
    return {idx["name"] for idx in insp.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("quality_cars"):
        return

    columns = _table_columns("quality_cars")

    if "root_cause_text" not in columns:
        op.add_column("quality_cars", sa.Column("root_cause_text", sa.Text(), nullable=True))
    if "root_cause_status" not in columns:
        op.add_column("quality_cars", sa.Column("root_cause_status", sa.String(length=32), nullable=True))
        op.execute(sa.text("UPDATE quality_cars SET root_cause_status = 'PENDING' WHERE root_cause_status IS NULL"))
        op.alter_column("quality_cars", "root_cause_status", nullable=False)
    if "root_cause_review_note" not in columns:
        op.add_column("quality_cars", sa.Column("root_cause_review_note", sa.Text(), nullable=True))

    if "capa_text" not in columns:
        op.add_column("quality_cars", sa.Column("capa_text", sa.Text(), nullable=True))
    if "capa_status" not in columns:
        op.add_column("quality_cars", sa.Column("capa_status", sa.String(length=32), nullable=True))
        op.execute(sa.text("UPDATE quality_cars SET capa_status = 'PENDING' WHERE capa_status IS NULL"))
        op.alter_column("quality_cars", "capa_status", nullable=False)
    if "capa_review_note" not in columns:
        op.add_column("quality_cars", sa.Column("capa_review_note", sa.Text(), nullable=True))

    if "evidence_required" not in columns:
        op.add_column("quality_cars", sa.Column("evidence_required", sa.Boolean(), nullable=True))
        op.execute(sa.text("UPDATE quality_cars SET evidence_required = true WHERE evidence_required IS NULL"))
        op.alter_column("quality_cars", "evidence_required", nullable=False)
    if "evidence_received_at" not in columns:
        op.add_column("quality_cars", sa.Column("evidence_received_at", sa.DateTime(timezone=True), nullable=True))
    if "evidence_verified_at" not in columns:
        op.add_column("quality_cars", sa.Column("evidence_verified_at", sa.DateTime(timezone=True), nullable=True))

    indexes = _table_indexes("quality_cars")
    if "ix_quality_cars_root_cause_status" not in indexes:
        op.create_index("ix_quality_cars_root_cause_status", "quality_cars", ["root_cause_status"], unique=False)
    if "ix_quality_cars_capa_status" not in indexes:
        op.create_index("ix_quality_cars_capa_status", "quality_cars", ["capa_status"], unique=False)
    if "ix_quality_cars_evidence_received_at" not in indexes:
        op.create_index("ix_quality_cars_evidence_received_at", "quality_cars", ["evidence_received_at"], unique=False)
    if "ix_quality_cars_evidence_verified_at" not in indexes:
        op.create_index("ix_quality_cars_evidence_verified_at", "quality_cars", ["evidence_verified_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("quality_cars"):
        return

    indexes = _table_indexes("quality_cars")
    columns = _table_columns("quality_cars")

    if "ix_quality_cars_evidence_verified_at" in indexes:
        op.drop_index("ix_quality_cars_evidence_verified_at", table_name="quality_cars")
    if "ix_quality_cars_evidence_received_at" in indexes:
        op.drop_index("ix_quality_cars_evidence_received_at", table_name="quality_cars")
    if "ix_quality_cars_capa_status" in indexes:
        op.drop_index("ix_quality_cars_capa_status", table_name="quality_cars")
    if "ix_quality_cars_root_cause_status" in indexes:
        op.drop_index("ix_quality_cars_root_cause_status", table_name="quality_cars")

    if "evidence_verified_at" in columns:
        op.drop_column("quality_cars", "evidence_verified_at")
    if "evidence_received_at" in columns:
        op.drop_column("quality_cars", "evidence_received_at")
    if "evidence_required" in columns:
        op.drop_column("quality_cars", "evidence_required")
    if "capa_review_note" in columns:
        op.drop_column("quality_cars", "capa_review_note")
    if "capa_status" in columns:
        op.drop_column("quality_cars", "capa_status")
    if "capa_text" in columns:
        op.drop_column("quality_cars", "capa_text")
    if "root_cause_review_note" in columns:
        op.drop_column("quality_cars", "root_cause_review_note")
    if "root_cause_status" in columns:
        op.drop_column("quality_cars", "root_cause_status")
    if "root_cause_text" in columns:
        op.drop_column("quality_cars", "root_cause_text")
