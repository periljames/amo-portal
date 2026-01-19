"""
Add aircraft_documents table for regulatory compliance tracking.

Revision ID: 0f1e4ad3c5b1
Revises: 8e1ae4ea5206
Create Date: 2025-03-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0f1e4ad3c5b1"
down_revision: Union[str, Sequence[str], None] = "8e1ae4ea5206"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "aircraft_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("aircraft_serial_number", sa.String(length=50), nullable=False, index=True),
        sa.Column(
            "document_type",
            sa.Enum(
                "CERTIFICATE_OF_AIRWORTHINESS",
                "CERTIFICATE_OF_REGISTRATION",
                "AIRWORTHINESS_REVIEW_CERTIFICATE",
                "RADIO_TELEPHONY_LICENSE",
                "NOISE_CERTIFICATE",
                "INSURANCE",
                "WEIGHT_AND_BALANCE_SCHEDULE",
                "MEL_APPROVAL",
                "OTHER",
                name="aircraft_document_type_enum",
                native_enum=False,
            ),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "authority",
            sa.Enum(
                "FAA",
                "EASA",
                "KCAA",
                "CAA_UK",
                "OTHER",
                name="regulatory_authority_enum",
                native_enum=False,
            ),
            nullable=False,
            index=True,
            server_default="KCAA",
        ),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("reference_number", sa.String(length=128), nullable=True),
        sa.Column("compliance_basis", sa.String(length=255), nullable=True),
        sa.Column("issued_on", sa.Date(), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("alert_window_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column(
            "status",
            sa.Enum(
                "CURRENT",
                "DUE_SOON",
                "OVERDUE",
                "OVERRIDDEN",
                name="aircraft_document_status_enum",
                native_enum=False,
            ),
            nullable=False,
            server_default="CURRENT",
            index=True,
        ),
        sa.Column("file_storage_path", sa.String(length=512), nullable=True),
        sa.Column("file_original_name", sa.String(length=255), nullable=True),
        sa.Column("file_content_type", sa.String(length=128), nullable=True),
        sa.Column("last_uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_uploaded_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("override_expires_on", sa.Date(), nullable=True),
        sa.Column("override_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("override_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["aircraft_serial_number"], ["aircraft.serial_number"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["override_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["last_uploaded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "aircraft_serial_number",
            "document_type",
            "authority",
            name="uq_aircraft_document_unique",
        ),
        sa.CheckConstraint("alert_window_days >= 0", name="ck_aircraft_doc_alert_window_nonneg"),
        sa.CheckConstraint(
            "expires_on IS NULL OR issued_on IS NULL OR expires_on >= issued_on",
            name="ck_aircraft_doc_issue_before_expiry",
        ),
    )
    op.create_index(
        "ix_aircraft_documents_status_due",
        "aircraft_documents",
        ["status", "expires_on"],
        unique=False,
    )
    op.create_index(
        "ix_aircraft_documents_aircraft_due",
        "aircraft_documents",
        ["aircraft_serial_number", "expires_on"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_aircraft_documents_aircraft_due", table_name="aircraft_documents")
    op.drop_index("ix_aircraft_documents_status_due", table_name="aircraft_documents")
    op.drop_table("aircraft_documents")
