from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text

from amodb.database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class ProcurementDocument(Base):
    __tablename__ = "procurement_documents"
    __table_args__ = (
        Index("ix_procurement_documents_entity", "amo_id", "entity_type", "entity_id"),
        Index("ix_procurement_documents_status", "amo_id", "status", "created_at"),
    )

    id = Column(Integer, primary_key=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type = Column(String(40), nullable=False, index=True)
    entity_id = Column(String(128), nullable=False, index=True)
    document_kind = Column(String(64), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    source_type = Column(String(32), nullable=False, default="UPLOADED", index=True)
    status = Column(String(24), nullable=False, default="ACTIVE", index=True)
    file_name = Column(String(255), nullable=True)
    storage_path = Column(Text, nullable=True)
    mime_type = Column(String(128), nullable=True)
    size_bytes = Column(BigInteger, nullable=True)
    sha256 = Column(String(64), nullable=True, index=True)
    physical_reference = Column(String(255), nullable=True)
    physical_location = Column(String(255), nullable=True)
    dms_document_id = Column(String(64), nullable=True, index=True)
    dms_revision_id = Column(String(64), nullable=True)
    notes = Column(Text, nullable=True)
    is_verified = Column(Boolean, nullable=False, default=False, index=True)
    uploaded_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
