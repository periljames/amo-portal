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
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ...database import Base

from .enums import (
    QMSDomain,
    QMSDocType,
    QMSDocStatus,
    QMSDistributionFormat,
    QMSChangeRequestStatus,
    QMSAuditKind,
    QMSAuditStatus,
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

    approved_by_authority = Column(Boolean, nullable=False, default=False)
    authority_ref = Column(String(255), nullable=True)

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
    holder_user_id = Column(String(36), USER_ID_FK, nullable=True, index=True)

    dist_format = Column(
        SAEnum(QMSDistributionFormat, name="qms_dist_format", native_enum=False),
        nullable=False,
        default=QMSDistributionFormat.SOFT_COPY,
        index=True,
    )
    requires_ack = Column(Boolean, nullable=False, default=False)

    acked_at = Column(DateTime(timezone=True), nullable=True)
    acked_by_user_id = Column(String(36), USER_ID_FK, nullable=True, index=True)

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

    created_by_user_id = Column(String(36), USER_ID_FK, nullable=True, index=True)
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
    lead_auditor_user_id = Column(String(36), USER_ID_FK, nullable=True, index=True)

    planned_start = Column(Date, nullable=True)
    planned_end = Column(Date, nullable=True)
    actual_start = Column(Date, nullable=True)
    actual_end = Column(Date, nullable=True)

    report_file_ref = Column(String(512), nullable=True)
    retention_until = Column(Date, nullable=True)

    created_by_user_id = Column(String(36), USER_ID_FK, nullable=True, index=True)
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

    created_by_user_id = Column(String(36), USER_ID_FK, nullable=True, index=True)
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

    responsible_user_id = Column(String(36), USER_ID_FK, nullable=True, index=True)
    due_date = Column(Date, nullable=True, index=True)
    evidence_ref = Column(String(512), nullable=True)

    status = Column(
        SAEnum(QMSCAPStatus, name="qms_cap_status", native_enum=False),
        nullable=False,
        default=QMSCAPStatus.OPEN,
        index=True,
    )

    created_by_user_id = Column(String(36), USER_ID_FK, nullable=True, index=True)
    updated_by_user_id = Column(String(36), USER_ID_FK, nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    finding = relationship("QMSAuditFinding", back_populates="cap", lazy="joined")

    __table_args__ = (
        Index("ix_qms_caps_status_due", "status", "due_date"),
    )

    def __repr__(self) -> str:
        return f"<QMSCorrectiveAction id={self.id} finding_id={self.finding_id} status={self.status}>"
