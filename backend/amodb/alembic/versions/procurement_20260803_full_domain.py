"""Create the tenant-scoped aviation procurement and supply-chain domain.

Revision ID: procurement_20260803_full_domain
Revises: 2c4d7e9f0a1b
Create Date: 2026-08-03
"""

from __future__ import annotations

from alembic import op

from amodb.apps.procurement import models


revision = "procurement_20260803_full_domain"
down_revision = "2c4d7e9f0a1b"
branch_labels = ("procurement",)
depends_on = None


_TABLES = (
    models.ProcurementSupplier.__table__,
    models.SupplierApprovalScope.__table__,
    models.ProcurementRequisition.__table__,
    models.ProcurementRequisitionLine.__table__,
    models.ProcurementRFQ.__table__,
    models.ProcurementRFQSupplier.__table__,
    models.ProcurementQuote.__table__,
    models.ProcurementQuoteLine.__table__,
    models.ProcurementPurchaseOrder.__table__,
    models.ProcurementPurchaseOrderLine.__table__,
    models.ProcurementReceipt.__table__,
    models.ProcurementReceiptLine.__table__,
    models.ProcurementReceivingInspection.__table__,
    models.ProcurementQualityHold.__table__,
    models.ProcurementInvoiceMatch.__table__,
    models.ProcurementEvent.__table__,
)


def upgrade() -> None:
    bind = op.get_bind()
    for table in _TABLES:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(_TABLES):
        table.drop(bind=bind, checkfirst=True)
