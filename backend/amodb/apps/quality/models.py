# backend/amodb/apps/quality/models.py
#
# QMS / Quality module ORM models:
# - Document control (documents, revisions, distribution)
# - Manual / controlled-doc change requests
# - Audit management (audits, findings)
# - Corrective Action Plans (CAP)
#
# Hardening goals (long-run safety):
# - Consistent audit user FK types: users.id GUID String(36) (accounts app).
# - Timezone-aware UTC timestamps.
# - Non-native enums to avoid Postgres enum lifecycle headaches in Alembic.
# - Check constraints to prevent negative revision/issue numbers and invalid planning fields.
# - Uniqueness/indexing for common lookups and to prevent silent duplicates.
# - Relationship loading tuned to avoid N+1 where it matters (selectin/joined).

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ...database import Base

from .enums import (
    CARActionType,
    CARResponseStatus,
    CARPriority,
    CARProgram,
    CARStatus,
    QMSNotificationSeverity,
    QMSDomain,
    QMSDocType,
    QMSDocStatus,
    QMSDistributionFormat,
    QMSRetentionCategory,
    QMSRevisionLifecycleStatus,
    QMSSecurityLevel,
    QMSPhysicalCopyStatus,
    QMSCustodyAction,
    QMSChangeRequestStatus,
    QMSAuditKind,
    QMSAuditStatus,
    QMSAuditScheduleFrequency,
    QMSFindingType,
    QMSFindingSeverity,
    FindingLevel,
    QMSCAPStatus,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _user_id_fk() -> ForeignKey:
    return ForeignKey("users.id", ondelete="SET NULL")


class QMSDocument(Base):
    __tablename__ = "qms_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    domain = Column(
        SAEnum(QMSDomain, name="qms_domain", native_enum=False),
        nullable=False,
        index=True,
    )
    doc_type = Column(
        SAEnum(QMSDocType, name="qms_doc_type", native_enum=False),
        nullable=False,
        index=True,
    )

    doc_code = Column(String(50), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    status = Column(
        SAEnum(QMSDocStatus, name="qms_doc_status", native_enum=False),
        nullable=False,
        default=QMSDocStatus.DRAFT,
        index=True,
    )

    current_issue_no = Column(Integer, nullable=True)
    current_rev_no = Column(Integer, nullable=True)
    effective_date = Column(Date, nullable=True)

    restricted_access = Column(Boolean, nullable=False, default=False)
    security_level = Column(
        SAEnum(QMSSecurityLevel, name="qms_security_level", native_enum=False),
        nullable=False,
        default=QMSSecurityLevel.INTERNAL,
    )
    retention_category = Column(
        SAEnum(QMSRetentionCategory, name="qms_retention_category", native_enum=False),
        nullable=False,
        default=QMSRetentionCategory.MAINT_RECORD_5Y,
    )
    owner_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)
    current_file_ref = Column(String(512), nullable=True)

    created_by_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)
    updated_by_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    revisions = relationship(
        "QMSDocumentRevision",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    distributions = relationship(
        "QMSDocumentDistribution",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("domain", "doc_type", "doc_code", name="uq_qms_doc_code"),
        Index("ix_qms_documents_domain_status", "domain", "status"),
        Index("ix_qms_documents_type_status", "doc_type", "status"),
        CheckConstraint("current_issue_no IS NULL OR current_issue_no >= 0", name="ck_qms_doc_issue_nonneg"),
        CheckConstraint("current_rev_no IS NULL OR current_rev_no >= 0", name="ck_qms_doc_rev_nonneg"),
    )

    def __repr__(self) -> str:
        return f"<QMSDocument id={self.id} code={self.doc_code} status={self.status}>"


class QMSDocumentRevision(Base):
    __tablename__ = "qms_document_revisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("qms_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    issue_no = Column(Integer, nullable=False)
    rev_no = Column(Integer, nullable=False)

    issued_date = Column(Date, nullable=True)
    entered_date = Column(Date, nullable=True)

    pages_affected = Column(String(255), nullable=True)
    tracking_serial = Column(String(128), nullable=True)
    change_summary = Column(Text, nullable=True)

    is_temporary = Column(Boolean, nullable=False, default=False)
    temporary_expires_on = Column(Date, nullable=True)

    file_ref = Column(String(512), nullable=True)
    version_semver = Column(String(32), nullable=True)
    lifecycle_status = Column(
        SAEnum(QMSRevisionLifecycleStatus, name="qms_revision_lifecycle_status", native_enum=False),
        nullable=False,
        default=QMSRevisionLifecycleStatus.DRAFT,
        index=True,
    )
    sha256 = Column(String(64), nullable=True, index=True)
    primary_storage_provider = Column(String(32), nullable=True)
    primary_storage_key = Column(String(1024), nullable=True)
    primary_storage_etag = Column(String(128), nullable=True)
    byte_size = Column(Integer, nullable=True)
    mime_type = Column(String(255), nullable=True)

    approved_by_authority = Column(Boolean, nullable=False, default=False)
    authority_ref = Column(String(255), nullable=True)
    approved_by_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    superseded_at = Column(DateTime(timezone=True), nullable=True)
    obsolete_at = Column(DateTime(timezone=True), nullable=True)

    created_by_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    document = relationship("QMSDocument", back_populates="revisions", lazy="joined")

    __table_args__ = (
        UniqueConstraint("document_id", "issue_no", "rev_no", name="uq_qms_doc_revision"),
        Index("ix_qms_doc_revisions_doc_created", "document_id", "created_at"),
        Index("ix_qms_doc_revisions_doc_issue_rev", "document_id", "issue_no", "rev_no"),
        CheckConstraint("issue_no >= 0", name="ck_qms_docrev_issue_nonneg"),
        CheckConstraint("rev_no >= 0", name="ck_qms_docrev_rev_nonneg"),
        CheckConstraint(
            "is_temporary = FALSE OR temporary_expires_on IS NOT NULL",
            name="ck_qms_docrev_temp_requires_expiry",
        ),
    )

    def __repr__(self) -> str:
        return f"<QMSDocumentRevision id={self.id} doc_id={self.document_id} issue={self.issue_no} rev={self.rev_no}>"


class QMSPhysicalControlledCopy(Base):
    __tablename__ = "physical_controlled_copies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    digital_revision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("qms_document_revisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    copy_serial_number = Column(String(128), nullable=False)
    current_holder_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)
    storage_location_path = Column(String(512), nullable=True)
    last_inspected_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(
        SAEnum(QMSPhysicalCopyStatus, name="qms_physical_copy_status", native_enum=False),
        nullable=False,
        default=QMSPhysicalCopyStatus.ACTIVE,
        index=True,
    )
    is_controlled_copy = Column(Boolean, nullable=False, default=True)
    copy_number = Column(Integer, nullable=False, default=1)
    voided_at = Column(DateTime(timezone=True), nullable=True)
    replaced_by_copy_id = Column(
        UUID(as_uuid=True),
        ForeignKey("physical_controlled_copies.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        UniqueConstraint("amo_id", "copy_serial_number", name="uq_physical_controlled_copy_serial"),
        Index("ix_physical_copy_amo_revision", "amo_id", "digital_revision_id"),
    )


class QMSCustodyLog(Base):
    __tablename__ = "custody_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    physical_copy_id = Column(
        UUID(as_uuid=True),
        ForeignKey("physical_controlled_copies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)
    action = Column(SAEnum(QMSCustodyAction, name="qms_custody_action", native_enum=False), nullable=False, index=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    gps_lat = Column(Numeric(10, 7), nullable=True)
    gps_lng = Column(Numeric(10, 7), nullable=True)
    notes = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_custody_logs_amo_copy_occurred", "amo_id", "physical_copy_id", "occurred_at"),
    )


class QMSDocumentDistribution(Base):
    __tablename__ = "qms_document_distributions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("qms_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("qms_document_revisions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    copy_number = Column(String(64), nullable=True)
    holder_label = Column(String(255), nullable=False)
    holder_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)

    dist_format = Column(
        SAEnum(QMSDistributionFormat, name="qms_dist_format", native_enum=False),
        nullable=False,
        default=QMSDistributionFormat.SOFT_COPY,
        index=True,
    )
    requires_ack = Column(Boolean, nullable=False, default=False)

    acked_at = Column(DateTime(timezone=True), nullable=True)
    acked_by_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)

    distributed_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    document = relationship("QMSDocument", back_populates="distributions", lazy="joined")
    revision = relationship("QMSDocumentRevision", lazy="joined")

    __table_args__ = (
        Index("ix_qms_doc_dist_doc_format", "document_id", "dist_format"),
        Index("ix_qms_doc_dist_ack", "document_id", "requires_ack", "acked_at"),
        # Prevent duplicate copy numbers per document (when copy_number is used).
        Index(
            "uq_qms_doc_dist_doc_copy_number_nn",
            "document_id",
            "copy_number",
            unique=True,
            postgresql_where=(copy_number.isnot(None)),
        ),
    )

    def __repr__(self) -> str:
        return f"<QMSDocumentDistribution id={self.id} doc_id={self.document_id} holder={self.holder_label}>"


class QMSManualChangeRequest(Base):
    __tablename__ = "qms_manual_change_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    domain = Column(
        SAEnum(QMSDomain, name="qms_domain", native_enum=False),
        nullable=False,
        index=True,
    )

    petitioner_name = Column(String(255), nullable=False)
    petitioner_email = Column(String(255), nullable=True)
    petitioner_phone = Column(String(64), nullable=True)
    petitioner_department = Column(String(128), nullable=True)

    manual_title = Column(String(255), nullable=False)
    manual_reference = Column(String(255), nullable=True)
    manual_copy_no = Column(String(64), nullable=True)
    manual_rev = Column(String(64), nullable=True)
    manual_location = Column(String(255), nullable=True)

    media_source = Column(String(255), nullable=True)
    remarks = Column(Text, nullable=True)

    change_request_text = Column(Text, nullable=False)

    status = Column(
        SAEnum(QMSChangeRequestStatus, name="qms_cr_status", native_enum=False),
        nullable=False,
        default=QMSChangeRequestStatus.SUBMITTED,
        index=True,
    )

    manual_owner_decision = Column(String(64), nullable=True)
    qa_decision = Column(String(64), nullable=True)
    librarian_decision = Column(String(64), nullable=True)
    review_feedback = Column(Text, nullable=True)

    created_by_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)
    submitted_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        Index("ix_qms_cr_domain_status", "domain", "status"),
        Index("ix_qms_cr_submitted_at", "submitted_at"),
    )

    def __repr__(self) -> str:
        return f"<QMSManualChangeRequest id={self.id} domain={self.domain} status={self.status}>"


class QMSAudit(Base):
    __tablename__ = "qms_audits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    domain = Column(
        SAEnum(QMSDomain, name="qms_domain", native_enum=False),
        nullable=False,
        index=True,
    )
    kind = Column(
        SAEnum(QMSAuditKind, name="qms_audit_kind", native_enum=False),
        nullable=False,
        default=QMSAuditKind.INTERNAL,
        index=True,
    )
    status = Column(
        SAEnum(QMSAuditStatus, name="qms_audit_status", native_enum=False),
        nullable=False,
        default=QMSAuditStatus.PLANNED,
        index=True,
    )

    audit_ref = Column(String(64), nullable=False, index=True)
    title = Column(String(255), nullable=False)

    scope = Column(Text, nullable=True)
    criteria = Column(Text, nullable=True)

    auditee = Column(String(255), nullable=True)
    auditee_email = Column(String(255), nullable=True)
    auditee_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)
    lead_auditor_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)
    observer_auditor_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)
    assistant_auditor_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)

    planned_start = Column(Date, nullable=True)
    planned_end = Column(Date, nullable=True)
    actual_start = Column(Date, nullable=True)
    actual_end = Column(Date, nullable=True)

    report_file_ref = Column(String(512), nullable=True)
    checklist_file_ref = Column(String(512), nullable=True)
    retention_until = Column(Date, nullable=True)
    upcoming_notice_sent_at = Column(DateTime(timezone=True), nullable=True)
    day_of_notice_sent_at = Column(DateTime(timezone=True), nullable=True)

    created_by_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    findings = relationship(
        "QMSAuditFinding",
        back_populates="audit",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("domain", "audit_ref", name="uq_qms_audit_ref"),
        Index("ix_qms_audits_domain_status", "domain", "status"),
        Index("ix_qms_audits_domain_kind", "domain", "kind"),
        CheckConstraint(
            "planned_start IS NULL OR planned_end IS NULL OR planned_end >= planned_start",
            name="ck_qms_audit_planned_dates_order",
        ),
        CheckConstraint(
            "actual_start IS NULL OR actual_end IS NULL OR actual_end >= actual_start",
            name="ck_qms_audit_actual_dates_order",
        ),
    )

    def __repr__(self) -> str:
        return f"<QMSAudit id={self.id} ref={self.audit_ref} status={self.status}>"


class QMSAuditFinding(Base):
    __tablename__ = "qms_audit_findings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    audit_id = Column(
        UUID(as_uuid=True),
        ForeignKey("qms_audits.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    finding_ref = Column(String(64), nullable=True, index=True)
    finding_type = Column(
        SAEnum(QMSFindingType, name="qms_finding_type", native_enum=False),
        nullable=False,
        default=QMSFindingType.NON_CONFORMITY,
        index=True,
    )

    severity = Column(
        SAEnum(QMSFindingSeverity, name="qms_finding_severity", native_enum=False),
        nullable=False,
        default=QMSFindingSeverity.MINOR,
        index=True,
    )
    level = Column(
        SAEnum(FindingLevel, name="qms_finding_level", native_enum=False),
        nullable=False,
        default=FindingLevel.LEVEL_3,
        index=True,
    )

    requirement_ref = Column(String(255), nullable=True)
    description = Column(Text, nullable=False)
    objective_evidence = Column(Text, nullable=True)

    safety_sensitive = Column(Boolean, nullable=False, default=False, index=True)

    target_close_date = Column(Date, nullable=True, index=True)
    closed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    verified_at = Column(DateTime(timezone=True), nullable=True, index=True)
    verified_by_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True, index=True)
    acknowledged_by_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)
    acknowledged_by_name = Column(String(255), nullable=True)
    acknowledged_by_email = Column(String(255), nullable=True)

    created_by_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    audit = relationship("QMSAudit", back_populates="findings", lazy="joined")
    cap = relationship(
        "QMSCorrectiveAction",
        back_populates="finding",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_qms_findings_audit_created", "audit_id", "created_at"),
        Index("ix_qms_findings_audit_level", "audit_id", "level"),
        Index("ix_qms_findings_audit_severity", "audit_id", "severity"),
        # If a finding_ref is used, keep it unique per audit.
        Index(
            "uq_qms_findings_audit_finding_ref_nn",
            "audit_id",
            "finding_ref",
            unique=True,
            postgresql_where=(finding_ref.isnot(None)),
        ),
    )

    def __repr__(self) -> str:
        return f"<QMSAuditFinding id={self.id} audit_id={self.audit_id} level={self.level} severity={self.severity}>"


class QMSAuditSchedule(Base):
    __tablename__ = "qms_audit_schedules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain = Column(
        SAEnum(QMSDomain, name="qms_audit_schedule_domain", native_enum=False),
        nullable=False,
        index=True,
    )
    kind = Column(
        SAEnum(QMSAuditKind, name="qms_audit_schedule_kind", native_enum=False),
        nullable=False,
        default=QMSAuditKind.INTERNAL,
        index=True,
    )
    frequency = Column(
        SAEnum(QMSAuditScheduleFrequency, name="qms_audit_schedule_frequency", native_enum=False),
        nullable=False,
        default=QMSAuditScheduleFrequency.MONTHLY,
        index=True,
    )
    title = Column(String(255), nullable=False)
    scope = Column(Text, nullable=True)
    criteria = Column(Text, nullable=True)
    auditee = Column(String(255), nullable=True)
    auditee_email = Column(String(255), nullable=True)
    auditee_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)
    lead_auditor_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)
    observer_auditor_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)
    assistant_auditor_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)
    duration_days = Column(Integer, nullable=False, default=1)
    next_due_date = Column(Date, nullable=False, index=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_by_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        Index("ix_qms_audit_schedules_domain_active", "domain", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<QMSAuditSchedule id={self.id} frequency={self.frequency} next_due={self.next_due_date}>"


class QMSCorrectiveAction(Base):
    __tablename__ = "qms_corrective_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    finding_id = Column(
        UUID(as_uuid=True),
        ForeignKey("qms_audit_findings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    root_cause = Column(Text, nullable=True)
    containment_action = Column(Text, nullable=True)
    corrective_action = Column(Text, nullable=True)
    preventive_action = Column(Text, nullable=True)

    responsible_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)
    due_date = Column(Date, nullable=True, index=True)
    evidence_ref = Column(String(512), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True, index=True)
    verified_by_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)

    status = Column(
        SAEnum(QMSCAPStatus, name="qms_cap_status", native_enum=False),
        nullable=False,
        default=QMSCAPStatus.OPEN,
        index=True,
    )

    created_by_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)
    updated_by_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    finding = relationship("QMSAuditFinding", back_populates="cap", lazy="joined")

    __table_args__ = (
        Index("ix_qms_caps_status_due", "status", "due_date"),
    )

    def __repr__(self) -> str:
        return f"<QMSCorrectiveAction id={self.id} finding_id={self.finding_id} status={self.status}>"


class QMSNotification(Base):
    __tablename__ = "qms_notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(36), _user_id_fk(), nullable=False, index=True)
    message = Column(Text, nullable=False)
    severity = Column(
        SAEnum(QMSNotificationSeverity, name="qms_notification_severity", native_enum=False),
        nullable=False,
        default=QMSNotificationSeverity.INFO,
        index=True,
    )
    created_by_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    read_at = Column(DateTime(timezone=True), nullable=True, index=True)

    __table_args__ = (
        Index("ix_qms_notifications_user_created", "user_id", "created_at"),
        Index("ix_qms_notifications_user_unread", "user_id", "read_at"),
    )

    def __repr__(self) -> str:
        return f"<QMSNotification id={self.id} user_id={self.user_id} severity={self.severity}>"


class CorrectiveActionRequest(Base):
    """
    CAR register entry.
    - program: QUALITY or RELIABILITY
    - car_number: unique per program + year (e.g., Q-2024-0001)
    - source: optional linkage to a QMS audit finding
    """

    __tablename__ = "quality_cars"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    program = Column(
        SAEnum(CARProgram, name="quality_car_program", native_enum=False),
        nullable=False,
        index=True,
    )
    car_number = Column(String(32), nullable=False)

    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=False)
    requested_by_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)
    assigned_to_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)

    priority = Column(
        SAEnum(CARPriority, name="quality_car_priority", native_enum=False),
        nullable=False,
        default=CARPriority.MEDIUM,
        index=True,
    )
    status = Column(
        SAEnum(CARStatus, name="quality_car_status", native_enum=False),
        nullable=False,
        default=CARStatus.DRAFT,
        index=True,
    )

    invite_token = Column(String(64), nullable=False, unique=True, index=True)
    reminder_interval_days = Column(Integer, nullable=False, default=7)
    next_reminder_at = Column(DateTime(timezone=True), nullable=True, index=True)

    containment_action = Column(Text, nullable=True)
    root_cause = Column(Text, nullable=True)
    corrective_action = Column(Text, nullable=True)
    preventive_action = Column(Text, nullable=True)
    evidence_ref = Column(String(512), nullable=True)
    submitted_by_name = Column(String(255), nullable=True)
    submitted_by_email = Column(String(255), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True, index=True)

    root_cause_text = Column(Text, nullable=True)
    root_cause_status = Column(String(32), nullable=False, default="PENDING", index=True)
    root_cause_review_note = Column(Text, nullable=True)
    capa_text = Column(Text, nullable=True)
    capa_status = Column(String(32), nullable=False, default="PENDING", index=True)
    capa_review_note = Column(Text, nullable=True)
    evidence_required = Column(Boolean, nullable=False, default=True)
    evidence_received_at = Column(DateTime(timezone=True), nullable=True, index=True)
    evidence_verified_at = Column(DateTime(timezone=True), nullable=True, index=True)

    due_date = Column(Date, nullable=True, index=True)
    target_closure_date = Column(Date, nullable=True, index=True)
    closed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    escalated_at = Column(DateTime(timezone=True), nullable=True, index=True)

    finding_id = Column(
        UUID(as_uuid=True),
        ForeignKey("qms_audit_findings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    finding = relationship("QMSAuditFinding", lazy="selectin")
    actions = relationship(
        "CARActionLog",
        back_populates="car",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    responses = relationship(
        "CARResponse",
        back_populates="car",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )
    attachments = relationship(
        "CARAttachment",
        back_populates="car",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("program", "car_number", name="uq_quality_car_number"),
        Index("ix_quality_cars_program_status", "program", "status"),
        Index("ix_quality_cars_program_due", "program", "due_date"),
        Index("ix_quality_cars_reminders", "next_reminder_at"),
    )

    def __repr__(self) -> str:
        return f"<CAR id={self.id} program={self.program} number={self.car_number} status={self.status}>"


class CARActionLog(Base):
    __tablename__ = "quality_car_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    car_id = Column(
        UUID(as_uuid=True),
        ForeignKey("quality_cars.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    action_type = Column(
        SAEnum(CARActionType, name="quality_car_action_type", native_enum=False),
        nullable=False,
        default=CARActionType.COMMENT,
        index=True,
    )
    message = Column(Text, nullable=False)
    actor_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    car = relationship("CorrectiveActionRequest", back_populates="actions", lazy="joined")

    __table_args__ = (
        Index("ix_quality_car_actions_car_type", "car_id", "action_type"),
    )

    def __repr__(self) -> str:
        return f"<CARAction car={self.car_id} type={self.action_type}>"


class CARResponse(Base):
    __tablename__ = "quality_car_responses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    car_id = Column(
        UUID(as_uuid=True),
        ForeignKey("quality_cars.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    containment_action = Column(Text, nullable=True)
    root_cause = Column(Text, nullable=True)
    corrective_action = Column(Text, nullable=True)
    preventive_action = Column(Text, nullable=True)
    evidence_ref = Column(String(512), nullable=True)
    submitted_by_name = Column(String(255), nullable=True)
    submitted_by_email = Column(String(255), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    status = Column(
        SAEnum(CARResponseStatus, name="quality_car_response_status", native_enum=False),
        nullable=False,
        default=CARResponseStatus.SUBMITTED,
        index=True,
    )

    car = relationship("CorrectiveActionRequest", back_populates="responses", lazy="joined")

    def __repr__(self) -> str:
        return f"<CARResponse id={self.id} car={self.car_id} status={self.status}>"


class CARAttachment(Base):
    __tablename__ = "quality_car_attachments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    car_id = Column(
        UUID(as_uuid=True),
        ForeignKey("quality_cars.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename = Column(String(255), nullable=False)
    file_ref = Column(String(512), nullable=False)
    content_type = Column(String(128), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    sha256 = Column(String(64), nullable=True, index=True)
    uploaded_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    car = relationship("CorrectiveActionRequest", back_populates="attachments", lazy="joined")

    def __repr__(self) -> str:
        return f"<CARAttachment id={self.id} car={self.car_id} filename={self.filename}>"


class UserAvailabilityStatus(str, enum.Enum):
    ON_DUTY = "ON_DUTY"
    AWAY = "AWAY"
    ON_LEAVE = "ON_LEAVE"


class UserAvailability(Base):
    __tablename__ = "user_availability"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(SAEnum(UserAvailabilityStatus, name="user_availability_status_enum", native_enum=False), nullable=False, index=True)
    effective_from = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    effective_to = Column(DateTime(timezone=True), nullable=True)
    note = Column(Text, nullable=True)
    updated_by_user_id = Column(String(36), _user_id_fk(), nullable=True, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("ix_user_availability_amo_status", "amo_id", "status"),
        Index("ix_user_availability_amo_user", "amo_id", "user_id"),
        Index("ix_user_availability_amo_updated", "amo_id", "updated_at"),
    )

    def __repr__(self) -> str:
        return f"<UserAvailability user={self.user_id} status={self.status}>"
