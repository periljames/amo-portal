from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String, Text

from amodb.database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class ProcurementDocumentEntityType(str, Enum):
    REQUISITION = "REQUISITION"
    RFQ = "RFQ"
    QUOTE = "QUOTE"
    PURCHASE_ORDER = "PURCHASE_ORDER"
    RECEIPT = "RECEIPT"
    SUPPLIER = "SUPPLIER"
    QUALITY_HOLD = "QUALITY_HOLD"


class ProcurementDocumentSource(str, Enum):
    PHYSICAL_FORM = "PHYSICAL_FORM"
    EXTERNAL_SOFTWARE = "EXTERNAL_SOFTWARE"
    EMAIL = "EMAIL"
    SUPPLIER_PORTAL = "SUPPLIER_PORTAL"
    PORTAL_EXPORT = "PORTAL_EXPORT"
    DMS_CONTROLLED = "DMS_CONTROLLED"
    OTHER = "OTHER"


class ProcurementDocumentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    VOID = "VOID"


class ProcurementDocumentVerificationStatus(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class ProcurementDocument(Base):
    __tablename__ = "procurement_documents"
    __table_args__ = (
        Index("ix_procurement_documents_amo_entity", "amo_id", "entity_type", "entity_id"),
        Index("ix_procurement_documents_amo_status", "amo_id", "status", "uploaded_at"),
        Index("ix_procurement_documents_amo_verification", "amo_id", "verification_status", "uploaded_at"),
        Index("ix_procurement_documents_sha256", "amo_id", "sha256"),
        Index("ix_procurement_documents_dms", "amo_id", "dms_document_id", "dms_revision_id"),
    )

    id = Column(Integer, primary_key=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type = Column(
        SAEnum(ProcurementDocumentEntityType, name="procurement_document_entity_type_enum", native_enum=False),
        nullable=False,
        index=True,
    )
    entity_id = Column(String(128), nullable=False, index=True)
    document_type = Column(String(64), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    document_number = Column(String(128), nullable=True, index=True)
    revision = Column(String(64), nullable=True)
    document_date = Column(Date, nullable=True)
    source = Column(
        SAEnum(ProcurementDocumentSource, name="procurement_document_source_enum", native_enum=False),
        nullable=False,
        default=ProcurementDocumentSource.PHYSICAL_FORM,
        index=True,
    )

    original_filename = Column(String(255), nullable=True)
    stored_path = Column(Text, nullable=True)
    mime_type = Column(String(128), nullable=True)
    size_bytes = Column(BigInteger, nullable=True)
    sha256 = Column(String(64), nullable=True, index=True)

    physical_reference = Column(String(255), nullable=True, index=True)
    physical_location = Column(String(255), nullable=True)
    external_system = Column(String(128), nullable=True)
    external_reference = Column(String(255), nullable=True, index=True)
    external_url = Column(Text, nullable=True)
    dms_document_id = Column(String(64), nullable=True, index=True)
    dms_revision_id = Column(String(64), nullable=True, index=True)

    notes = Column(Text, nullable=True)
    is_quality_evidence = Column(Boolean, nullable=False, default=False, index=True)
    qms_reference = Column(String(128), nullable=True, index=True)
    verification_status = Column(
        SAEnum(
            ProcurementDocumentVerificationStatus,
            name="procurement_document_verification_status_enum",
            native_enum=False,
        ),
        nullable=False,
        default=ProcurementDocumentVerificationStatus.NOT_REQUIRED,
        index=True,
    )
    verification_notes = Column(Text, nullable=True)
    verified_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)

    status = Column(
        SAEnum(ProcurementDocumentStatus, name="procurement_document_status_enum", native_enum=False),
        nullable=False,
        default=ProcurementDocumentStatus.ACTIVE,
        index=True,
    )
    uploaded_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    voided_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    voided_at = Column(DateTime(timezone=True), nullable=True)
    void_reason = Column(Text, nullable=True)
