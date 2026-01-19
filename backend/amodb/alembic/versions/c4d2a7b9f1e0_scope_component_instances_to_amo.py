"""scope component instances to amo

Revision ID: c4d2a7b9f1e0
Revises: b7d9f3a1c2e4
Create Date: 2025-02-14 00:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c4d2a7b9f1e0"
down_revision: Union[str, Sequence[str], None] = "b7d9f3a1c2e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("component_instances", sa.Column("amo_id", sa.String(length=36), nullable=True))
    op.create_index(op.f("ix_component_instances_amo_id"), "component_instances", ["amo_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_component_instances_amo_id_amos"),
        "component_instances",
        "amos",
        ["amo_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("uq_component_instance_pn_sn", "component_instances", type_="unique")
    op.create_unique_constraint(
        "uq_component_instance_amo_pn_sn",
        "component_instances",
        ["amo_id", "part_number", "serial_number"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_component_instance_amo_pn_sn", "component_instances", type_="unique")
    op.create_unique_constraint(
        "uq_component_instance_pn_sn",
        "component_instances",
        ["part_number", "serial_number"],
    )
    op.drop_constraint(op.f("fk_component_instances_amo_id_amos"), "component_instances", type_="foreignkey")
    op.drop_index(op.f("ix_component_instances_amo_id"), table_name="component_instances")
    op.drop_column("component_instances", "amo_id")
