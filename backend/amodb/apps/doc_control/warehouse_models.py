from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from amodb.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.utcnow()


class WarehouseContentRecord(Base):
    """Canonical logical identity for every governed tenant information asset."""

    __tablename__ = "document_warehouse_content_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "resource_type", "canonical_code", name="uq_doc_wh_record_tenant_type_code"),
        UniqueConstraint("tenant_id", "source_entity_type", "source_entity_id", name="uq_doc_wh_record_source"),
        Index("ix_doc_wh_record_tenant_type_status", "tenant_id", "resource_type", "lifecycle_status"),
        Index("ix_doc_wh_record_tenant_title", "tenant_id", "title"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    resource_type = Column(String(64), nullable=False)
    canonical_code = Column(String(160), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    classification = Column(String(32), nullable=False, default="INTERNAL")
    lifecycle_status = Column(String(32), nullable=False, default="ACTIVE")
    owner_department = Column(String(128), nullable=True)
    source_entity_type = Column(String(64), nullable=False)
    source_entity_id = Column(String(128), nullable=False)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class WarehouseContentVersion(Base):
    """Immutable edition/revision identity beneath a logical content record."""

    __tablename__ = "document_warehouse_content_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "content_record_id", "sequence", name="uq_doc_wh_version_sequence"),
        UniqueConstraint("tenant_id", "source_version_type", "source_version_id", name="uq_doc_wh_version_source"),
        Index("ix_doc_wh_version_record_status", "content_record_id", "lifecycle_status", "sequence"),
        Index("ix_doc_wh_version_tenant_effective", "tenant_id", "effective_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    content_record_id = Column(String(36), ForeignKey("document_warehouse_content_records.id", ondelete="CASCADE"), nullable=False)
    version_label = Column(String(128), nullable=False)
    sequence = Column(Integer, nullable=False)
    lifecycle_status = Column(String(32), nullable=False, default="DRAFT")
    source_version_type = Column(String(64), nullable=False)
    source_version_id = Column(String(128), nullable=False)
    file_hash = Column(String(64), nullable=True)
    effective_at = Column(DateTime(timezone=True), nullable=True)
    superseded_at = Column(DateTime(timezone=True), nullable=True)
    change_summary = Column(Text, nullable=True)
    immutable = Column(Boolean, nullable=False, default=False)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class WarehouseBinaryObject(Base):
    """Stored original or derivative attached to an exact warehouse version."""

    __tablename__ = "document_warehouse_binary_objects"
    __table_args__ = (
        UniqueConstraint("tenant_id", "content_version_id", "sha256", "object_role", name="uq_doc_wh_binary_version_hash_role"),
        Index("ix_doc_wh_binary_version", "content_version_id", "object_role"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    content_version_id = Column(String(36), ForeignKey("document_warehouse_content_versions.id", ondelete="CASCADE"), nullable=False)
    object_role = Column(String(32), nullable=False, default="ORIGINAL")
    filename = Column(String(255), nullable=False)
    mime_type = Column(String(128), nullable=False)
    size_bytes = Column(Integer, nullable=True)
    sha256 = Column(String(64), nullable=False)
    storage_uri = Column(Text, nullable=False)
    derived_from_binary_id = Column(String(36), ForeignKey("document_warehouse_binary_objects.id", ondelete="SET NULL"), nullable=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class WarehouseIdentifier(Base):
    """Normalized business/library identifier for deterministic retrieval."""

    __tablename__ = "document_warehouse_identifiers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "scheme", "normalized_value", name="uq_doc_wh_identifier_lookup"),
        Index("ix_doc_wh_identifier_record", "content_record_id", "scheme"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    content_record_id = Column(String(36), ForeignKey("document_warehouse_content_records.id", ondelete="CASCADE"), nullable=False)
    scheme = Column(String(32), nullable=False)
    normalized_value = Column(String(255), nullable=False)
    display_value = Column(String(255), nullable=False)
    source = Column(String(64), nullable=False, default="SYSTEM")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class WarehouseLocation(Base):
    """Tenant physical hierarchy for shelves, rooms, offices, aircraft and sites."""

    __tablename__ = "document_warehouse_locations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_doc_wh_location_tenant_code"),
        Index("ix_doc_wh_location_parent", "tenant_id", "parent_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    code = Column(String(128), nullable=False)
    name = Column(String(255), nullable=False)
    location_type = Column(String(40), nullable=False, default="SHELF")
    parent_id = Column(String(36), ForeignKey("document_warehouse_locations.id", ondelete="SET NULL"), nullable=True)
    path_text = Column(String(1000), nullable=False)
    status = Column(String(24), nullable=False, default="ACTIVE")
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class WarehouseItemCopy(Base):
    """Trackable physical/offline copy tied to a logical work and optional exact version."""

    __tablename__ = "document_warehouse_item_copies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "barcode", name="uq_doc_wh_copy_barcode"),
        UniqueConstraint("tenant_id", "qr_token", name="uq_doc_wh_copy_qr"),
        UniqueConstraint("tenant_id", "source_entity_type", "source_entity_id", name="uq_doc_wh_copy_source"),
        Index("ix_doc_wh_copy_record_status", "content_record_id", "status"),
        Index("ix_doc_wh_copy_revision_compliance", "tenant_id", "revision_compliance", "status"),
        Index("ix_doc_wh_copy_location", "tenant_id", "current_location_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    content_record_id = Column(String(36), ForeignKey("document_warehouse_content_records.id", ondelete="CASCADE"), nullable=False)
    content_version_id = Column(String(36), ForeignKey("document_warehouse_content_versions.id", ondelete="SET NULL"), nullable=True)
    source_entity_type = Column(String(64), nullable=False)
    source_entity_id = Column(String(128), nullable=False)
    copy_number = Column(String(128), nullable=True)
    barcode = Column(String(128), nullable=False)
    qr_token = Column(String(128), nullable=False, default=_uuid)
    format = Column(String(32), nullable=False, default="PHYSICAL")
    status = Column(String(32), nullable=False, default="AVAILABLE")
    home_location_id = Column(String(36), ForeignKey("document_warehouse_locations.id", ondelete="SET NULL"), nullable=True)
    current_location_id = Column(String(36), ForeignKey("document_warehouse_locations.id", ondelete="SET NULL"), nullable=True)
    location_text = Column(String(1000), nullable=True)
    custodian_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    installed_version_label = Column(String(128), nullable=True)
    required_version_label = Column(String(128), nullable=True)
    revision_compliance = Column(String(32), nullable=False, default="NOT_APPLICABLE")
    last_inventory_at = Column(DateTime(timezone=True), nullable=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class WarehouseRelationship(Base):
    """First-class relationship graph across governed tenant resources."""

    __tablename__ = "document_warehouse_relationships"
    __table_args__ = (
        Index("ix_doc_wh_rel_source", "tenant_id", "source_record_id", "relationship_type", "status"),
        Index("ix_doc_wh_rel_target", "tenant_id", "target_record_id", "relationship_type", "status"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    source_record_id = Column(String(36), ForeignKey("document_warehouse_content_records.id", ondelete="CASCADE"), nullable=False)
    source_version_id = Column(String(36), ForeignKey("document_warehouse_content_versions.id", ondelete="SET NULL"), nullable=True)
    relationship_type = Column(String(64), nullable=False)
    target_record_id = Column(String(36), ForeignKey("document_warehouse_content_records.id", ondelete="CASCADE"), nullable=False)
    target_version_id = Column(String(36), ForeignKey("document_warehouse_content_versions.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(24), nullable=False, default="ACTIVE")
    verified_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    effective_from = Column(DateTime(timezone=True), nullable=True)
    effective_to = Column(DateTime(timezone=True), nullable=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class WarehouseExternalReference(Base):
    __tablename__ = "document_warehouse_external_references"
    __table_args__ = (
        Index("ix_doc_wh_external_record", "content_record_id", "provider", "reference_type"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    content_record_id = Column(String(36), ForeignKey("document_warehouse_content_records.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(64), nullable=False)
    reference_type = Column(String(64), nullable=False)
    external_id = Column(String(255), nullable=True)
    url = Column(Text, nullable=False)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class WarehouseAccessPolicy(Base):
    __tablename__ = "document_warehouse_access_policies"
    __table_args__ = (
        Index("ix_doc_wh_access_record_action", "content_record_id", "action", "priority"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    content_record_id = Column(String(36), ForeignKey("document_warehouse_content_records.id", ondelete="CASCADE"), nullable=False)
    action = Column(String(32), nullable=False, default="READ")
    effect = Column(String(16), nullable=False, default="ALLOW")
    principal_type = Column(String(32), nullable=False, default="ROLE")
    principal_value = Column(String(255), nullable=False)
    conditions_json = Column(JSONB, nullable=False, default=dict)
    priority = Column(Integer, nullable=False, default=100)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class WarehouseAcknowledgement(Base):
    __tablename__ = "document_warehouse_acknowledgements"
    __table_args__ = (
        UniqueConstraint("tenant_id", "content_version_id", "user_id", name="uq_doc_wh_ack_version_user"),
        Index("ix_doc_wh_ack_record_user", "content_record_id", "user_id", "acknowledged_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    content_record_id = Column(String(36), ForeignKey("document_warehouse_content_records.id", ondelete="CASCADE"), nullable=False)
    content_version_id = Column(String(36), ForeignKey("document_warehouse_content_versions.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    file_hash = Column(String(64), nullable=True)
    acknowledgement_method = Column(String(40), nullable=False, default="READER_SIGNOFF")
    session_metadata_json = Column(JSONB, nullable=False, default=dict)
    acknowledged_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class WarehouseAuditEvent(Base):
    """Append-only resource history independent from document version history."""

    __tablename__ = "document_warehouse_audit_events"
    __table_args__ = (
        Index("ix_doc_wh_audit_record_created", "content_record_id", "created_at"),
        Index("ix_doc_wh_audit_tenant_event", "tenant_id", "event_type", "created_at"),
        Index("ix_doc_wh_audit_transaction", "tenant_id", "transaction_id"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    content_record_id = Column(String(36), ForeignKey("document_warehouse_content_records.id", ondelete="CASCADE"), nullable=False)
    content_version_id = Column(String(36), ForeignKey("document_warehouse_content_versions.id", ondelete="SET NULL"), nullable=True)
    item_copy_id = Column(String(36), ForeignKey("document_warehouse_item_copies.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(String(64), nullable=False)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    transaction_id = Column(String(64), nullable=False, default=_uuid)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class WarehouseCollection(Base):
    __tablename__ = "document_warehouse_collections"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_doc_wh_collection_code"),
        Index("ix_doc_wh_collection_type_status", "tenant_id", "collection_type", "status"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    code = Column(String(128), nullable=False)
    name = Column(String(255), nullable=False)
    collection_type = Column(String(40), nullable=False, default="GENERAL")
    status = Column(String(24), nullable=False, default="ACTIVE")
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class WarehouseCollectionMembership(Base):
    __tablename__ = "document_warehouse_collection_memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "collection_id", "content_record_id", name="uq_doc_wh_collection_member"),
        Index("ix_doc_wh_collection_member_record", "tenant_id", "content_record_id"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    collection_id = Column(String(36), ForeignKey("document_warehouse_collections.id", ondelete="CASCADE"), nullable=False)
    content_record_id = Column(String(36), ForeignKey("document_warehouse_content_records.id", ondelete="CASCADE"), nullable=False)
    added_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class WarehousePatron(Base):
    __tablename__ = "document_warehouse_patrons"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_doc_wh_patron_user"),
        UniqueConstraint("tenant_id", "patron_barcode", name="uq_doc_wh_patron_barcode"),
        Index("ix_doc_wh_patron_status_type", "tenant_id", "status", "patron_type"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    patron_barcode = Column(String(128), nullable=True)
    patron_type = Column(String(32), nullable=False, default="EMPLOYEE")
    status = Column(String(24), nullable=False, default="ACTIVE")
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class WarehouseLoan(Base):
    __tablename__ = "document_warehouse_loans"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_entity_type", "source_entity_id", name="uq_doc_wh_loan_source"),
        Index("ix_doc_wh_loan_patron_status", "tenant_id", "patron_id", "status", "due_at"),
        Index("ix_doc_wh_loan_item_status", "item_copy_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    item_copy_id = Column(String(36), ForeignKey("document_warehouse_item_copies.id", ondelete="CASCADE"), nullable=False)
    patron_id = Column(String(36), ForeignKey("document_warehouse_patrons.id", ondelete="RESTRICT"), nullable=False)
    source_entity_type = Column(String(64), nullable=False)
    source_entity_id = Column(String(128), nullable=False)
    status = Column(String(24), nullable=False, default="ACTIVE")
    checked_out_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    due_at = Column(DateTime(timezone=True), nullable=True)
    returned_at = Column(DateTime(timezone=True), nullable=True)
    renewal_count = Column(Integer, nullable=False, default=0)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class WarehouseHold(Base):
    __tablename__ = "document_warehouse_holds"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_entity_type", "source_entity_id", name="uq_doc_wh_hold_source"),
        Index("ix_doc_wh_hold_record_status", "content_record_id", "status", "created_at"),
        Index("ix_doc_wh_hold_patron_status", "patron_id", "status", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    content_record_id = Column(String(36), ForeignKey("document_warehouse_content_records.id", ondelete="CASCADE"), nullable=False)
    patron_id = Column(String(36), ForeignKey("document_warehouse_patrons.id", ondelete="CASCADE"), nullable=False)
    fulfilled_item_copy_id = Column(String(36), ForeignKey("document_warehouse_item_copies.id", ondelete="SET NULL"), nullable=True)
    source_entity_type = Column(String(64), nullable=False)
    source_entity_id = Column(String(128), nullable=False)
    status = Column(String(24), nullable=False, default="ACTIVE")
    pickup_location = Column(String(1000), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class WarehouseItemEvent(Base):
    __tablename__ = "document_warehouse_item_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_event_type", "source_event_id", name="uq_doc_wh_item_event_source"),
        Index("ix_doc_wh_item_event_copy_created", "item_copy_id", "created_at"),
        Index("ix_doc_wh_item_event_tenant_type", "tenant_id", "event_type", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    item_copy_id = Column(String(36), ForeignKey("document_warehouse_item_copies.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(40), nullable=False)
    source_event_type = Column(String(64), nullable=False)
    source_event_id = Column(String(128), nullable=False)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    patron_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    from_status = Column(String(32), nullable=True)
    to_status = Column(String(32), nullable=True)
    from_location = Column(String(1000), nullable=True)
    to_location = Column(String(1000), nullable=True)
    due_at = Column(DateTime(timezone=True), nullable=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class WarehouseWorkflowInstance(Base):
    __tablename__ = "document_warehouse_workflows"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_workflow_type", "source_workflow_id", name="uq_doc_wh_workflow_source"),
        Index("ix_doc_wh_workflow_record_state", "content_record_id", "state"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    content_record_id = Column(String(36), ForeignKey("document_warehouse_content_records.id", ondelete="CASCADE"), nullable=False)
    content_version_id = Column(String(36), ForeignKey("document_warehouse_content_versions.id", ondelete="SET NULL"), nullable=True)
    source_workflow_type = Column(String(64), nullable=False)
    source_workflow_id = Column(String(128), nullable=False)
    state = Column(String(48), nullable=False)
    effective_at = Column(DateTime(timezone=True), nullable=True)
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


class WarehouseRetentionRule(Base):
    __tablename__ = "document_warehouse_retention_rules"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source_rule_type", "source_rule_id", name="uq_doc_wh_retention_source"),
        UniqueConstraint("tenant_id", "code", name="uq_doc_wh_retention_code"),
        Index("ix_doc_wh_retention_status", "tenant_id", "status", "disposition_action"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False)
    code = Column(String(128), nullable=False)
    name = Column(String(255), nullable=False)
    source_rule_type = Column(String(64), nullable=False)
    source_rule_id = Column(String(128), nullable=False)
    retention_months = Column(Integer, nullable=False)
    trigger_event = Column(String(64), nullable=False, default="CAPTURED")
    disposition_action = Column(String(32), nullable=False, default="REVIEW_AT_EXPIRY")
    status = Column(String(24), nullable=False, default="ACTIVE")
    metadata_json = Column(JSONB, nullable=False, default=dict)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
