"""Prevent concurrent equipment records claiming one active Inventory serial.

Revision ID: qms_equipment_serial_261112
Revises: dms_training_link_261111

Before upgrading a populated database, reconcile duplicate active
(amo_id, inventory_serial_id) pairs. Do not silently delete either
governance record or take away its calibration evidence.
"""
from alembic import op


revision = "qms_equipment_serial_261112"
down_revision = "dms_training_link_261111"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_qms_equipment_active_inventory_serial
        ON qms_equipment (amo_id, (payload ->> 'inventory_serial_id'))
        WHERE deleted_at IS NULL
          AND NULLIF(payload ->> 'inventory_serial_id', '') IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_qms_equipment_active_inventory_serial")
