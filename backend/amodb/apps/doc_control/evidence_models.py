from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from amodb.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.utcnow()


class DocumentEvidenceAsset(Base):
    """Immutable retained evidence uploaded for a governed Document Control record.

    Files are always tenant- and document-scoped. The row stores the retained
    checksum and storage metadata; workflow/authority/custody evidence JSON stores
    references to this asset rather than asking operators to type opaque IDs.
    """

    __tablename__ = "document_evidence_assets"
    __table_args__ = (
        Index("ix_document_evidence_tenant_manual_created", "tenant_id", "manual_id", "created_at"),
        Index("ix_document_evidence_tenant_revision", "tenant_id", "revision_id"),
        Index("ix_document_evidence_tenant_sha256", "tenant_id", "sha256"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False)
    revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="SET NULL"), nullable=True)
    category = Column(String(48), nullable=False, default="GENERAL")
    purpose = Column(String(128), nullable=True)
    filename = Column(String(255), nullable=False)
    mime_type = Column(String(128), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    storage_path = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    uploaded_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    source_context_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
