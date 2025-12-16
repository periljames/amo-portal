# backend/amodb/apps/quality/models.py
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from amodb.database import Base

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


class QMSDocument(Base):
    __tablename__ = "qms_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    domain = Column(SAEnum(QMSDomain, name="qms_domain", native_enum=False), nullable=False)
    doc_type = Column(SAEnum(QMSDocType, name="qms_doc_type", native_enum=False), nullable=False)

    doc_code = Column(String(50), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    status = Column(SAEnum(QMSDocStatus, name="qms_doc_status", native_enum=False), nullable=False, default=QMSDocStatus.DRAFT)

    current_issue_no = Column(Integer, nullable=True)
    current_rev_no = Column(Integer, nullable=True)
    effective_date = Column(Date, nullable=True)

    restricted_access = Column(Boolean, nullable=False, default=False)
    current_file_ref = Column(String(512), nullable=True)

    created_by_user_id = Column(String(64), nullable=True)
    updated_by_user_id = Column(String(64), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    revisions = relationship("QMSDocumentRevision", back_populates="document", cascade="all, delete-orphan")
    distributions = relationship("QMSDocumentDistribution", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("domain", "doc_type", "doc_code", name="uq_qms_doc_code"),
        Index("ix_qms_documents_domain_status", "domain", "status"),
    )


class QMSDocumentRevision(Base):
    __tablename__ = "qms_document_revisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("qms_documents.id", ondelete="CASCADE"), nullable=False, index=True)

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

    created_by_user_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    document = relationship("QMSDocument", back_populates="revisions")

    __table_args__ = (
        UniqueConstraint("document_id", "issue_no", "rev_no", name="uq_qms_doc_revision"),
        Index("ix_qms_doc_revisions_doc_created", "document_id", "created_at"),
    )


class QMSDocumentDistribution(Base):
    __tablename__ = "qms_document_distributions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    document_id = Column(UUID(as_uuid=True), ForeignKey("qms_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    revision_id = Column(UUID(as_uuid=True), ForeignKey("qms_document_revisions.id", ondelete="SET NULL"), nullable=True)

    copy_number = Column(String(64), nullable=True)
    holder_label = Column(String(255), nullable=False)
    holder_user_id = Column(String(64), nullable=True)

    dist_format = Column(SAEnum(QMSDistributionFormat, name="qms_dist_format", native_enum=False), nullable=False, default=QMSDistributionFormat.SOFT_COPY)
    requires_ack = Column(Boolean, nullable=False, default=False)

    acked_at = Column(DateTime(timezone=True), nullable=True)
    acked_by_user_id = Column(String(64), nullable=True)

    distributed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    document = relationship("QMSDocument", back_populates="distributions")


class QMSManualChangeRequest(Base):
    __tablename__ = "qms_manual_change_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    domain = Column(SAEnum(QMSDomain, name="qms_cr_domain", native_enum=False), nullable=False)

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

    status = Column(SAEnum(QMSChangeRequestStatus, name="qms_cr_status", native_enum=False), nullable=False, default=QMSChangeRequestStatus.SUBMITTED)

    manual_owner_decision = Column(String(64), nullable=True)
    qa_decision = Column(String(64), nullable=True)
    librarian_decision = Column(String(64), nullable=True)
    review_feedback = Column(Text, nullable=True)

    created_by_user_id = Column(String(64), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_qms_cr_domain_status", "domain", "status"),
    )


class QMSAudit(Base):
    __tablename__ = "qms_audits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    domain = Column(SAEnum(QMSDomain, name="qms_audit_domain", native_enum=False), nullable=False)
    kind = Column(SAEnum(QMSAuditKind, name="qms_audit_kind", native_enum=False), nullable=False, default=QMSAuditKind.INTERNAL)
    status = Column(SAEnum(QMSAuditStatus, name="qms_audit_status", native_enum=False), nullable=False, default=QMSAuditStatus.PLANNED)

    audit_ref = Column(String(64), nullable=False, index=True)
    title = Column(String(255), nullable=False)

    scope = Column(Text, nullable=True)
    criteria = Column(Text, nullable=True)

    auditee = Column(String(255), nullable=True)
    lead_auditor_user_id = Column(String(64), nullable=True)

    planned_start = Column(Date, nullable=True)
    planned_end = Column(Date, nullable=True)
    actual_start = Column(Date, nullable=True)
    actual_end = Column(Date, nullable=True)

    report_file_ref = Column(String(512), nullable=True)
    retention_until = Column(Date, nullable=True)

    created_by_user_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    findings = relationship("QMSAuditFinding", back_populates="audit", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("domain", "audit_ref", name="uq_qms_audit_ref"),
        Index("ix_qms_audits_domain_status", "domain", "status"),
    )


class QMSAuditFinding(Base):
    __tablename__ = "qms_audit_findings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    audit_id = Column(UUID(as_uuid=True), ForeignKey("qms_audits.id", ondelete="CASCADE"), nullable=False, index=True)

    finding_ref = Column(String(64), nullable=True, index=True)
    finding_type = Column(SAEnum(QMSFindingType, name="qms_finding_type", native_enum=False), nullable=False, default=QMSFindingType.NON_CONFORMITY)

    severity = Column(SAEnum(QMSFindingSeverity, name="qms_finding_severity", native_enum=False), nullable=False, default=QMSFindingSeverity.MINOR)
    level = Column(SAEnum(FindingLevel, name="qms_finding_level", native_enum=False), nullable=False, default=FindingLevel.LEVEL_3)

    requirement_ref = Column(String(255), nullable=True)
    description = Column(Text, nullable=False)
    objective_evidence = Column(Text, nullable=True)

    safety_sensitive = Column(Boolean, nullable=False, default=False)

    target_close_date = Column(Date, nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    audit = relationship("QMSAudit", back_populates="findings")
    cap = relationship("QMSCorrectiveAction", back_populates="finding", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_qms_findings_audit_created", "audit_id", "created_at"),
        Index("ix_qms_findings_level", "level"),
    )


class QMSCorrectiveAction(Base):
    __tablename__ = "qms_corrective_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    finding_id = Column(UUID(as_uuid=True), ForeignKey("qms_audit_findings.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    root_cause = Column(Text, nullable=True)
    containment_action = Column(Text, nullable=True)
    corrective_action = Column(Text, nullable=True)
    preventive_action = Column(Text, nullable=True)

    responsible_user_id = Column(String(64), nullable=True)
    due_date = Column(Date, nullable=True)
    evidence_ref = Column(String(512), nullable=True)

    status = Column(SAEnum(QMSCAPStatus, name="qms_cap_status", native_enum=False), nullable=False, default=QMSCAPStatus.OPEN)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    finding = relationship("QMSAuditFinding", back_populates="cap")
