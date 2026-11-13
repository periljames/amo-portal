"""Tenant-owned Microsoft 365 Graph connection and per-manual working-file links."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Index
from amodb.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DocumentMicrosoftConnection(Base):
    __tablename__ = "document_microsoft_connections"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, unique=True)
    status = Column(String(24), nullable=False, default="NOT_CONNECTED")
    microsoft_tenant_id = Column(String(72), nullable=True)
    microsoft_user_id = Column(String(128), nullable=True)
    microsoft_user_name = Column(String(255), nullable=True)
    connected_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    encrypted_refresh_token = Column(Text, nullable=True)
    granted_scopes = Column(Text, nullable=True)
    oauth_state_sha256 = Column(String(64), nullable=True, unique=True)
    oauth_state_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    oauth_state_expires_at = Column(DateTime(timezone=True), nullable=True)
    last_connected_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class DocumentMicrosoftFileLink(Base):
    __tablename__ = "document_microsoft_file_links"
    __table_args__ = (
        UniqueConstraint("tenant_id", "manual_id", name="uq_doc_microsoft_file_tenant_manual"),
        Index("ix_doc_microsoft_file_tenant_revision", "tenant_id", "last_imported_revision_id"),
    )
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    manual_id = Column(String(36), ForeignKey("manuals.id", ondelete="CASCADE"), nullable=False)
    drive_id = Column(String(512), nullable=False)
    item_id = Column(String(512), nullable=False)
    item_name = Column(String(255), nullable=False)
    web_url = Column(Text, nullable=False)
    observed_etag = Column(String(255), nullable=False)
    observed_modified_at = Column(DateTime(timezone=True), nullable=True)
    observed_size = Column(Integer, nullable=True)
    last_imported_etag = Column(String(255), nullable=True)
    last_imported_source_sha256 = Column(String(64), nullable=True)
    last_imported_revision_id = Column(String(36), ForeignKey("manual_revisions.id", ondelete="SET NULL"), nullable=True)
    linked_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    linked_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
