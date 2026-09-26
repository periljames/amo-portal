from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from amodb.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.utcnow()


class LibraryCatalogItem(Base):
    """Tenant-owned bibliographic/catalogue identity for non-governed library material.

    Controlled manuals continue to use Manual/ManualRevision.  This model covers
    books, journals, media, reference works and other holdings that belong in the
    same discovery/circulation experience but must not be forced through an AMO
    manual approval workflow.
    """

    __tablename__ = "document_library_catalog_items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "catalogue_code", name="uq_doc_library_item_tenant_code"),
        Index("ix_doc_library_item_tenant_type_status", "tenant_id", "material_type", "status"),
        Index("ix_doc_library_item_tenant_title", "tenant_id", "title"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    catalogue_code = Column(String(128), nullable=False)
    material_type = Column(String(40), nullable=False, default="BOOK")
    title = Column(String(500), nullable=False)
    subtitle = Column(String(500), nullable=True)
    authors_json = Column(JSONB, nullable=False, default=list)
    publisher = Column(String(255), nullable=True)
    publication_year = Column(Integer, nullable=True)
    edition = Column(String(128), nullable=True)
    language = Column(String(32), nullable=True)
    identifiers_json = Column(JSONB, nullable=False, default=dict)
    subjects_json = Column(JSONB, nullable=False, default=list)
    description = Column(Text, nullable=True)
    search_text = Column(Text, nullable=False, default="")
    source_provider = Column(String(64), nullable=False, default="MANUAL")
    source_record_id = Column(String(255), nullable=True)
    source_url = Column(Text, nullable=True)
    cover_url = Column(Text, nullable=True)
    restricted_flag = Column(Boolean, nullable=False, default=False)
    access_scope_json = Column(JSONB, nullable=False, default=dict)
    circulation_policy_json = Column(JSONB, nullable=False, default=dict)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    status = Column(String(32), nullable=False, default="ACTIVE")
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class LibraryCatalogIdentifier(Base):
    """Normalized external/library identifier used for deduplication and lookup."""

    __tablename__ = "document_library_catalog_identifiers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "scheme", "normalized_value", name="uq_doc_library_identifier_tenant_scheme_value"),
        Index("ix_doc_library_identifier_item", "catalog_item_id"),
        Index("ix_doc_library_identifier_lookup", "tenant_id", "normalized_value"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    catalog_item_id = Column(String(36), ForeignKey("document_library_catalog_items.id", ondelete="CASCADE"), nullable=False)
    scheme = Column(String(32), nullable=False)
    normalized_value = Column(String(255), nullable=False)
    display_value = Column(String(255), nullable=False)
    source = Column(String(64), nullable=False, default="MANUAL")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class LibraryHolding(Base):
    """One physical or offline-media item that can be located and circulated."""

    __tablename__ = "document_library_holdings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "barcode", name="uq_doc_library_holding_tenant_barcode"),
        UniqueConstraint("tenant_id", "qr_token", name="uq_doc_library_holding_tenant_qr"),
        Index("ix_doc_library_holding_tenant_status", "tenant_id", "status"),
        Index("ix_doc_library_holding_catalog_status", "catalog_item_id", "status"),
        Index("ix_doc_library_holding_holder_due", "holder_user_id", "due_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    catalog_item_id = Column(String(36), ForeignKey("document_library_catalog_items.id", ondelete="CASCADE"), nullable=False)
    barcode = Column(String(128), nullable=False)
    qr_token = Column(String(64), nullable=False, default=_uuid)
    accession_number = Column(String(128), nullable=True)
    call_number = Column(String(128), nullable=True)
    format = Column(String(32), nullable=False, default="PHYSICAL")
    home_location = Column(String(255), nullable=False)
    current_location = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False, default="AVAILABLE")
    holder_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    checked_out_at = Column(DateTime(timezone=True), nullable=True)
    due_at = Column(DateTime(timezone=True), nullable=True)
    renewal_count = Column(Integer, nullable=False, default=0)
    last_inventory_at = Column(DateTime(timezone=True), nullable=True)
    acquired_on = Column(Date, nullable=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    version = Column(Integer, nullable=False, default=1)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class LibraryCirculationEvent(Base):
    """Append-only custody/history event for a catalogue holding."""

    __tablename__ = "document_library_circulation_events"
    __table_args__ = (
        Index("ix_doc_library_event_holding_created", "holding_id", "created_at"),
        Index("ix_doc_library_event_tenant_patron", "tenant_id", "patron_user_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    holding_id = Column(String(36), ForeignKey("document_library_holdings.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(40), nullable=False)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    patron_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    from_status = Column(String(32), nullable=True)
    to_status = Column(String(32), nullable=True)
    from_location = Column(String(255), nullable=True)
    to_location = Column(String(255), nullable=True)
    due_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class LibraryHoldRequest(Base):
    """Reader reservation/hold for a catalogue title."""

    __tablename__ = "document_library_holds"
    __table_args__ = (
        Index("ix_doc_library_hold_item_status", "catalog_item_id", "status", "created_at"),
        Index("ix_doc_library_hold_user_status", "tenant_id", "user_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    catalog_item_id = Column(String(36), ForeignKey("document_library_catalog_items.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(32), nullable=False, default="ACTIVE")
    pickup_location = Column(String(255), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    fulfilled_holding_id = Column(String(36), ForeignKey("document_library_holdings.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class LibraryInventorySession(Base):
    """A governed shelf/room stocktake performed by Document Control."""

    __tablename__ = "document_library_inventory_sessions"
    __table_args__ = (
        Index("ix_doc_library_inventory_tenant_status", "tenant_id", "status", "started_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    location_prefix = Column(String(255), nullable=False)
    status = Column(String(24), nullable=False, default="OPEN")
    expected_count = Column(Integer, nullable=False, default=0)
    observed_count = Column(Integer, nullable=False, default=0)
    misplaced_count = Column(Integer, nullable=False, default=0)
    missing_count = Column(Integer, nullable=False, default=0)
    started_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    closed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)


class LibraryInventoryObservation(Base):
    """One immutable scan/observation made during a physical inventory session."""

    __tablename__ = "document_library_inventory_observations"
    __table_args__ = (
        UniqueConstraint("session_id", "holding_id", name="uq_doc_library_inventory_observation"),
        Index("ix_doc_library_inventory_observation_session", "session_id", "observed_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(String(36), ForeignKey("document_library_inventory_sessions.id", ondelete="CASCADE"), nullable=False)
    holding_id = Column(String(36), ForeignKey("document_library_holdings.id", ondelete="CASCADE"), nullable=False)
    observed_location = Column(String(255), nullable=False)
    expected_location = Column(String(255), nullable=False)
    outcome = Column(String(24), nullable=False)
    observed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    observed_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
