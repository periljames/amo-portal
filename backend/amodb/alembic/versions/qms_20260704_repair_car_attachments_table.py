"""repair missing quality CAR attachments table

Revision ID: qms_20260704_car_attach_repair
Revises: m4a5n6u7a8l9
Create Date: 2026-07-04 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "qms_20260704_car_attach_repair"
down_revision: Union[str, Sequence[str], None] = "m4a5n6u7a8l9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table(table_name):
        return set()
    return {column["name"] for column in insp.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("quality_cars"):
        return

    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS quality_car_attachments (
                id UUID NOT NULL,
                car_id UUID NOT NULL,
                filename VARCHAR(255) NOT NULL,
                file_ref VARCHAR(512) NOT NULL,
                content_type VARCHAR(128),
                size_bytes INTEGER,
                sha256 VARCHAR(64),
                uploaded_at TIMESTAMP WITH TIME ZONE NOT NULL
            )
            """
        )
    )

    existing_columns = _columns("quality_car_attachments")
    required_columns = {
        "id": "UUID",
        "car_id": "UUID",
        "filename": "VARCHAR(255)",
        "file_ref": "VARCHAR(512)",
        "content_type": "VARCHAR(128)",
        "size_bytes": "INTEGER",
        "sha256": "VARCHAR(64)",
        "uploaded_at": "TIMESTAMP WITH TIME ZONE",
    }
    for column_name, ddl in required_columns.items():
        if column_name not in existing_columns:
            op.execute(sa.text(f"ALTER TABLE quality_car_attachments ADD COLUMN IF NOT EXISTS {column_name} {ddl}"))

    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_quality_car_attachments_id_runtime ON quality_car_attachments (id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_quality_car_attachments_car_id_runtime ON quality_car_attachments (car_id)"))
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_quality_car_attachments_sha256_runtime ON quality_car_attachments (sha256)"))


def downgrade() -> None:
    # Do not drop uploaded evidence records during rollback.  The repair migration
    # is intentionally additive and safe to leave in place.
    pass
