from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from amodb.database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class SupplierLifecycleStatus(str, enum.Enum):
    PROSPECTIVE = "PROSPECTIVE"
    UNDER_REVIEW = "UNDER_REVIEW"
    CONDITIONALLY_APPROVED = "CONDITIONALLY_APPROVED"
    APPROVED = "APPROVED"
    RESTRICTED = "RESTRICTED"
    SUSPENDED = "SUSPENDED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


class SupplierRiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ApprovalScopeStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class RequisitionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    TECHNICAL_REVIEW = "TECHNICAL_REVIEW"
    BUDGET_REVIEW = "BUDGET_REVIEW"
    SOURCING = "SOURCING"
    APPROVED = "APPROVED"
    PARTIALLY_ORDERED = "PARTIALLY_ORDERED"
    ORDERED = "ORDERED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


class ProcurementPriority(str, enum.Enum):
    ROUTINE = "ROUTINE"
    URGENT = "URGENT"
    AOG = "AOG"


class RFQStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    PARTIALLY_RESPONDED = "PARTIALLY_RESPONDED"
    EVALUATION = "EVALUATION"
    AWARDED = "AWARDED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class QuoteStatus(str, enum.Enum):
    RECEIVED = "RECEIVED"
    COMPLIANT = "COMPLIANT"
    NONCOMPLIANT = "NONCOMPLIANT"
    SHORTLISTED = "SHORTLISTED"
    AWARDED = "AWARDED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class PurchaseOrderStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING_TECHNICAL_REVIEW = "PENDING_TECHNICAL_REVIEW"
    PENDING_BUDGET_APPROVAL = "PENDING_BUDGET_APPROVAL"
    PENDING_PROCUREMENT_APPROVAL = "PENDING_PROCUREMENT_APPROVAL"
    PENDING_QUALITY_APPROVAL = "PENDING_QUALITY_APPROVAL"
    APPROVED = "APPROVED"
    SENT = "SENT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_SHIPPED = "PARTIALLY_SHIPPED"
    SHIPPED = "SHIPPED"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    RECEIVED_PENDING_INSPECTION = "RECEIVED_PENDING_INSPECTION"
    FULFILLED = "FULFILLED"
    CLOSED = "CLOSED"
    ON_HOLD = "ON_HOLD"
    REVISED = "REVISED"
    CANCELLED = "CANCELLED"


class ReceiptStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    RECEIVED = "RECEIVED"
    QUARANTINED = "QUARANTINED"
    DOCUMENT_REVIEW = "DOCUMENT_REVIEW"
    PHYSICAL_INSPECTION = "PHYSICAL_INSPECTION"
    ACCEPTED_PENDING_RELEASE = "ACCEPTED_PENDING_RELEASE"
    RELEASED = "RELEASED"
    REJECTED = "REJECTED"
    RETURN_PENDING = "RETURN_PENDING"
    RETURNED = "RETURNED"


class InspectionDisposition(str, enum.Enum):
    ACCEPTED = "ACCEPTED"
    CONDITIONALLY_ACCEPTED = "CONDITIONALLY_ACCEPTED"
    ON_HOLD = "ON_HOLD"
    REJECTED = "REJECTED"
    RETURN_TO_SUPPLIER = "RETURN_TO_SUPPLIER"
    ESCALATED_TO_QUALITY = "ESCALATED_TO_QUALITY"


class QualityHoldStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    RELEASED = "RELEASED"
    CANCELLED = "CANCELLED"


class InvoiceMatchStatus(str, enum.Enum):
    PENDING = "PENDING"
    MATCHED = "MATCHED"
    VARIANCE = "VARIANCE"
    BLOCKED = "BLOCKED"
    APPROVED_FOR_PAYMENT = "APPROVED_FOR_PAYMENT"


class ProcurementSupplier(Base):
    __tablename__ = "procurement_suppliers"
    __table_args__ = (
        UniqueConstraint("amo_id", "supplier_code", name="uq_procurement_supplier_code"),
        Index("ix_procurement_suppliers_amo_status", "amo_id", "status"),
        Index("ix_procurement_suppliers_vendor", "vendor_id"),
        Index("ix_procurement_suppliers_qms", "qms_supplier_id"),
    )

    id = Column(Integer, primary_key=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_code = Column(String(64), nullable=False, index=True)
    legal_name = Column(String(255), nullable=False)
    trading_name = Column(String(255), nullable=True)
    supplier_type = Column(String(64), nullable=False, default="DISTRIBUTOR", index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id", ondelete="SET NULL"), nullable=True)
    qms_supplier_id = Column(String(64), nullable=True)
    status = Column(
        SAEnum(SupplierLifecycleStatus, name="procurement_supplier_status_enum", native_enum=False),
        nullable=False,
        default=SupplierLifecycleStatus.PROSPECTIVE,
        index=True,
    )
    risk_level = Column(
        SAEnum(SupplierRiskLevel, name="procurement_supplier_risk_enum", native_enum=False),
        nullable=False,
        default=SupplierRiskLevel.MEDIUM,
        index=True,
    )
    email = Column(String(255), nullable=True)
    phone = Column(String(64), nullable=True)
    website = Column(String(255), nullable=True)
    country = Column(String(64), nullable=True)
    physical_address = Column(Text, nullable=True)
    payment_terms = Column(String(128), nullable=True)
    default_currency = Column(String(8), nullable=False, default="USD")
    quality_contact_name = Column(String(255), nullable=True)
    quality_contact_email = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    suspended_at = Column(DateTime(timezone=True), nullable=True)
    suspended_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    suspension_reason = Column(Text, nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    approval_scopes = relationship("SupplierApprovalScope", back_populates="supplier", lazy="selectin")
    quotes = relationship("ProcurementQuote", back_populates="supplier", lazy="selectin")
    purchase_orders = relationship("ProcurementPurchaseOrder", back_populates="supplier", lazy="selectin")


class SupplierApprovalScope(Base):
    __tablename__ = "procurement_supplier_approval_scopes"
    __table_args__ = (
        UniqueConstraint(
            "amo_id",
            "supplier_id",
            "site_code",
            "category",
            "product_family",
            "authority",
            name="uq_procurement_supplier_scope",
        ),
        Index("ix_procurement_scope_supplier_status", "supplier_id", "status"),
        Index("ix_procurement_scope_amo_expiry", "amo_id", "expires_on"),
    )

    id = Column(Integer, primary_key=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("procurement_suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
    site_code = Column(String(64), nullable=False, default="PRIMARY")
    category = Column(String(64), nullable=False, index=True)
    product_family = Column(String(128), nullable=False, default="ALL")
    manufacturer = Column(String(128), nullable=True)
    authority = Column(String(64), nullable=False, default="TENANT_QMS")
    approval_number = Column(String(128), nullable=True)
    status = Column(
        SAEnum(ApprovalScopeStatus, name="procurement_scope_status_enum", native_enum=False),
        nullable=False,
        default=ApprovalScopeStatus.DRAFT,
        index=True,
    )
    effective_on = Column(Date, nullable=True)
    expires_on = Column(Date, nullable=True, index=True)
    restrictions = Column(Text, nullable=True)
    incoming_inspection_level = Column(String(32), nullable=False, default="STANDARD")
    evidence_reference = Column(String(255), nullable=True)
    qms_evaluation_id = Column(String(64), nullable=True)
    qms_audit_id = Column(String(64), nullable=True)
    approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    supplier = relationship("ProcurementSupplier", back_populates="approval_scopes", lazy="joined")


class ProcurementRequisition(Base):
    __tablename__ = "procurement_requisitions"
    __table_args__ = (
        UniqueConstraint("amo_id", "requisition_number", name="uq_procurement_requisition_number"),
        Index("ix_procurement_requisitions_amo_status", "amo_id", "status"),
        Index("ix_procurement_requisitions_required", "amo_id", "required_by"),
    )

    id = Column(Integer, primary_key=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    requisition_number = Column(String(64), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    requesting_department = Column(String(64), nullable=False, index=True)
    priority = Column(
        SAEnum(ProcurementPriority, name="procurement_priority_enum", native_enum=False),
        nullable=False,
        default=ProcurementPriority.ROUTINE,
        index=True,
    )
    status = Column(
        SAEnum(RequisitionStatus, name="procurement_requisition_status_enum", native_enum=False),
        nullable=False,
        default=RequisitionStatus.DRAFT,
        index=True,
    )
    required_by = Column(Date, nullable=True)
    cost_centre = Column(String(64), nullable=True)
    project_code = Column(String(64), nullable=True)
    budget_reference = Column(String(128), nullable=True)
    justification = Column(Text, nullable=True)
    source_module = Column(String(64), nullable=True, index=True)
    source_record_id = Column(String(128), nullable=True, index=True)
    work_order_id = Column(Integer, ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True, index=True)
    task_card_id = Column(Integer, ForeignKey("task_cards.id", ondelete="SET NULL"), nullable=True, index=True)
    aircraft_serial_number = Column(String(50), ForeignKey("aircraft.serial_number", ondelete="SET NULL"), nullable=True)
    requested_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    technical_reviewed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    budget_reviewed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    lines = relationship("ProcurementRequisitionLine", back_populates="requisition", cascade="all, delete-orphan", lazy="selectin")
    rfqs = relationship("ProcurementRFQ", back_populates="requisition", lazy="selectin")


class ProcurementRequisitionLine(Base):
    __tablename__ = "procurement_requisition_lines"
    __table_args__ = (
        Index("ix_procurement_req_lines_req", "requisition_id"),
        Index("ix_procurement_req_lines_part", "part_number"),
        CheckConstraint("quantity > 0", name="ck_procurement_req_line_quantity_positive"),
    )

    id = Column(Integer, primary_key=True)
    requisition_id = Column(Integer, ForeignKey("procurement_requisitions.id", ondelete="CASCADE"), nullable=False, index=True)
    inventory_part_id = Column(Integer, ForeignKey("inventory_parts.id", ondelete="SET NULL"), nullable=True)
    line_number = Column(Integer, nullable=False)
    item_type = Column(String(32), nullable=False, default="PART")
    part_number = Column(String(64), nullable=True, index=True)
    description = Column(String(255), nullable=False)
    quantity = Column(Float, nullable=False)
    uom = Column(String(16), nullable=False, default="EA")
    technical_specification = Column(Text, nullable=True)
    controlled_document_id = Column(String(64), nullable=True)
    controlled_document_revision = Column(String(64), nullable=True)
    criticality = Column(String(32), nullable=False, default="STANDARD", index=True)
    approved_manufacturers = Column(JSON, nullable=True)
    required_certification = Column(String(128), nullable=True)
    alternates_allowed = Column(Boolean, nullable=False, default=False)
    shelf_life_minimum_days = Column(Integer, nullable=True)
    delivery_location_id = Column(Integer, ForeignKey("inventory_locations.id", ondelete="SET NULL"), nullable=True)
    source_module = Column(String(64), nullable=True)
    source_record_id = Column(String(128), nullable=True)
    notes = Column(Text, nullable=True)

    requisition = relationship("ProcurementRequisition", back_populates="lines", lazy="joined")


class ProcurementRFQ(Base):
    __tablename__ = "procurement_rfqs"
    __table_args__ = (
        UniqueConstraint("amo_id", "rfq_number", name="uq_procurement_rfq_number"),
        Index("ix_procurement_rfqs_amo_status", "amo_id", "status"),
    )

    id = Column(Integer, primary_key=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    rfq_number = Column(String(64), nullable=False, index=True)
    requisition_id = Column(Integer, ForeignKey("procurement_requisitions.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(255), nullable=False)
    status = Column(
        SAEnum(RFQStatus, name="procurement_rfq_status_enum", native_enum=False),
        nullable=False,
        default=RFQStatus.DRAFT,
        index=True,
    )
    response_due_at = Column(DateTime(timezone=True), nullable=True)
    terms = Column(Text, nullable=True)
    quality_clauses = Column(Text, nullable=True)
    issued_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    requisition = relationship("ProcurementRequisition", back_populates="rfqs", lazy="joined")
    invited_suppliers = relationship("ProcurementRFQSupplier", back_populates="rfq", cascade="all, delete-orphan", lazy="selectin")
    quotes = relationship("ProcurementQuote", back_populates="rfq", lazy="selectin")


class ProcurementRFQSupplier(Base):
    __tablename__ = "procurement_rfq_suppliers"
    __table_args__ = (
        UniqueConstraint("rfq_id", "supplier_id", name="uq_procurement_rfq_supplier"),
        Index("ix_procurement_rfq_supplier_response", "rfq_id", "responded_at"),
    )

    id = Column(Integer, primary_key=True)
    rfq_id = Column(Integer, ForeignKey("procurement_rfqs.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("procurement_suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
    invited_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    responded_at = Column(DateTime(timezone=True), nullable=True)
    declined_at = Column(DateTime(timezone=True), nullable=True)
    decline_reason = Column(Text, nullable=True)

    rfq = relationship("ProcurementRFQ", back_populates="invited_suppliers", lazy="joined")
    supplier = relationship("ProcurementSupplier", lazy="joined")


class ProcurementQuote(Base):
    __tablename__ = "procurement_quotes"
    __table_args__ = (
        UniqueConstraint("amo_id", "quote_reference", "supplier_id", name="uq_procurement_quote_supplier_ref"),
        Index("ix_procurement_quotes_rfq_status", "rfq_id", "status"),
    )

    id = Column(Integer, primary_key=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    rfq_id = Column(Integer, ForeignKey("procurement_rfqs.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("procurement_suppliers.id", ondelete="RESTRICT"), nullable=False, index=True)
    quote_reference = Column(String(128), nullable=False)
    status = Column(
        SAEnum(QuoteStatus, name="procurement_quote_status_enum", native_enum=False),
        nullable=False,
        default=QuoteStatus.RECEIVED,
        index=True,
    )
    currency = Column(String(8), nullable=False, default="USD")
    freight_amount = Column(Numeric(14, 2), nullable=False, default=0)
    tax_amount = Column(Numeric(14, 2), nullable=False, default=0)
    total_amount = Column(Numeric(14, 2), nullable=False, default=0)
    lead_time_days = Column(Integer, nullable=True)
    valid_until = Column(Date, nullable=True)
    certification_offered = Column(String(255), nullable=True)
    warranty_terms = Column(Text, nullable=True)
    technical_deviations = Column(Text, nullable=True)
    evaluation_score = Column(Float, nullable=True)
    evaluation_notes = Column(Text, nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    evaluated_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    evaluated_at = Column(DateTime(timezone=True), nullable=True)

    rfq = relationship("ProcurementRFQ", back_populates="quotes", lazy="joined")
    supplier = relationship("ProcurementSupplier", back_populates="quotes", lazy="joined")
    lines = relationship("ProcurementQuoteLine", back_populates="quote", cascade="all, delete-orphan", lazy="selectin")


class ProcurementQuoteLine(Base):
    __tablename__ = "procurement_quote_lines"
    __table_args__ = (
        Index("ix_procurement_quote_lines_quote", "quote_id"),
        CheckConstraint("quantity > 0", name="ck_procurement_quote_line_quantity_positive"),
    )

    id = Column(Integer, primary_key=True)
    quote_id = Column(Integer, ForeignKey("procurement_quotes.id", ondelete="CASCADE"), nullable=False, index=True)
    requisition_line_id = Column(Integer, ForeignKey("procurement_requisition_lines.id", ondelete="SET NULL"), nullable=True)
    supplier_part_number = Column(String(64), nullable=True)
    manufacturer = Column(String(128), nullable=True)
    quantity = Column(Float, nullable=False)
    uom = Column(String(16), nullable=False, default="EA")
    unit_price = Column(Numeric(14, 4), nullable=False, default=0)
    promised_date = Column(Date, nullable=True)
    traceability_statement = Column(Text, nullable=True)
    is_technically_compliant = Column(Boolean, nullable=False, default=True)
    deviation = Column(Text, nullable=True)

    quote = relationship("ProcurementQuote", back_populates="lines", lazy="joined")


class ProcurementPurchaseOrder(Base):
    __tablename__ = "procurement_purchase_orders"
    __table_args__ = (
        UniqueConstraint("amo_id", "po_number", name="uq_procurement_po_number"),
        Index("ix_procurement_po_amo_status", "amo_id", "status"),
        Index("ix_procurement_po_supplier", "supplier_id", "status"),
    )

    id = Column(Integer, primary_key=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    po_number = Column(String(64), nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("procurement_suppliers.id", ondelete="RESTRICT"), nullable=False, index=True)
    quote_id = Column(Integer, ForeignKey("procurement_quotes.id", ondelete="SET NULL"), nullable=True)
    requisition_id = Column(Integer, ForeignKey("procurement_requisitions.id", ondelete="SET NULL"), nullable=True)
    status = Column(
        SAEnum(PurchaseOrderStatus, name="procurement_po_status_enum", native_enum=False),
        nullable=False,
        default=PurchaseOrderStatus.DRAFT,
        index=True,
    )
    priority = Column(
        SAEnum(ProcurementPriority, name="procurement_po_priority_enum", native_enum=False),
        nullable=False,
        default=ProcurementPriority.ROUTINE,
    )
    currency = Column(String(8), nullable=False, default="USD")
    subtotal = Column(Numeric(14, 2), nullable=False, default=0)
    freight_amount = Column(Numeric(14, 2), nullable=False, default=0)
    tax_amount = Column(Numeric(14, 2), nullable=False, default=0)
    total_amount = Column(Numeric(14, 2), nullable=False, default=0)
    delivery_terms = Column(String(128), nullable=True)
    payment_terms = Column(String(128), nullable=True)
    quality_clauses = Column(Text, nullable=True)
    ship_to_location_id = Column(Integer, ForeignKey("inventory_locations.id", ondelete="SET NULL"), nullable=True)
    requested_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    technical_approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    budget_approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    procurement_approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    quality_approved_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    promised_delivery_date = Column(Date, nullable=True)
    supplier_ack_reference = Column(String(128), nullable=True)
    override_reference = Column(String(128), nullable=True)
    override_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    supplier = relationship("ProcurementSupplier", back_populates="purchase_orders", lazy="joined")
    lines = relationship("ProcurementPurchaseOrderLine", back_populates="purchase_order", cascade="all, delete-orphan", lazy="selectin")
    receipts = relationship("ProcurementReceipt", back_populates="purchase_order", lazy="selectin")


class ProcurementPurchaseOrderLine(Base):
    __tablename__ = "procurement_purchase_order_lines"
    __table_args__ = (
        Index("ix_procurement_po_lines_po", "purchase_order_id"),
        Index("ix_procurement_po_lines_part", "part_number"),
        CheckConstraint("quantity > 0", name="ck_procurement_po_line_quantity_positive"),
    )

    id = Column(Integer, primary_key=True)
    purchase_order_id = Column(Integer, ForeignKey("procurement_purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    requisition_line_id = Column(Integer, ForeignKey("procurement_requisition_lines.id", ondelete="SET NULL"), nullable=True)
    inventory_part_id = Column(Integer, ForeignKey("inventory_parts.id", ondelete="SET NULL"), nullable=True)
    line_number = Column(Integer, nullable=False)
    part_number = Column(String(64), nullable=True, index=True)
    description = Column(String(255), nullable=False)
    manufacturer = Column(String(128), nullable=True)
    quantity = Column(Float, nullable=False)
    received_quantity = Column(Float, nullable=False, default=0)
    uom = Column(String(16), nullable=False, default="EA")
    unit_price = Column(Numeric(14, 4), nullable=False, default=0)
    required_certification = Column(String(128), nullable=True)
    promised_date = Column(Date, nullable=True)
    work_order_id = Column(Integer, ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True)
    task_card_id = Column(Integer, ForeignKey("task_cards.id", ondelete="SET NULL"), nullable=True)
    aircraft_serial_number = Column(String(50), ForeignKey("aircraft.serial_number", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)

    purchase_order = relationship("ProcurementPurchaseOrder", back_populates="lines", lazy="joined")


class ProcurementReceipt(Base):
    __tablename__ = "procurement_receipts"
    __table_args__ = (
        UniqueConstraint("amo_id", "receipt_number", name="uq_procurement_receipt_number"),
        Index("ix_procurement_receipts_amo_status", "amo_id", "status"),
        Index("ix_procurement_receipts_po", "purchase_order_id"),
    )

    id = Column(Integer, primary_key=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    receipt_number = Column(String(64), nullable=False, index=True)
    purchase_order_id = Column(Integer, ForeignKey("procurement_purchase_orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    status = Column(
        SAEnum(ReceiptStatus, name="procurement_receipt_status_enum", native_enum=False),
        nullable=False,
        default=ReceiptStatus.QUARANTINED,
        index=True,
    )
    delivery_note_number = Column(String(128), nullable=True)
    airway_bill_number = Column(String(128), nullable=True)
    supplier_shipment_reference = Column(String(128), nullable=True)
    package_condition = Column(String(64), nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    received_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    quarantine_location_id = Column(Integer, ForeignKey("inventory_locations.id", ondelete="SET NULL"), nullable=True)
    inspection_started_at = Column(DateTime(timezone=True), nullable=True)
    inspection_completed_at = Column(DateTime(timezone=True), nullable=True)
    released_at = Column(DateTime(timezone=True), nullable=True)
    released_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    purchase_order = relationship("ProcurementPurchaseOrder", back_populates="receipts", lazy="joined")
    lines = relationship("ProcurementReceiptLine", back_populates="receipt", cascade="all, delete-orphan", lazy="selectin")
    inspections = relationship("ProcurementReceivingInspection", back_populates="receipt", cascade="all, delete-orphan", lazy="selectin")


class ProcurementReceiptLine(Base):
    __tablename__ = "procurement_receipt_lines"
    __table_args__ = (
        Index("ix_procurement_receipt_lines_receipt", "receipt_id"),
        Index("ix_procurement_receipt_lines_part_serial", "part_number", "serial_number"),
        CheckConstraint("quantity > 0", name="ck_procurement_receipt_line_quantity_positive"),
    )

    id = Column(Integer, primary_key=True)
    receipt_id = Column(Integer, ForeignKey("procurement_receipts.id", ondelete="CASCADE"), nullable=False, index=True)
    purchase_order_line_id = Column(Integer, ForeignKey("procurement_purchase_order_lines.id", ondelete="RESTRICT"), nullable=False)
    inventory_part_id = Column(Integer, ForeignKey("inventory_parts.id", ondelete="SET NULL"), nullable=True)
    part_number = Column(String(64), nullable=False, index=True)
    description = Column(String(255), nullable=True)
    manufacturer = Column(String(128), nullable=True)
    quantity = Column(Float, nullable=False)
    uom = Column(String(16), nullable=False, default="EA")
    lot_number = Column(String(64), nullable=True)
    serial_number = Column(String(64), nullable=True)
    manufacture_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True)
    release_document_type = Column(String(64), nullable=True)
    release_document_number = Column(String(128), nullable=True)
    release_document_issuer = Column(String(128), nullable=True)
    release_document_date = Column(Date, nullable=True)
    chain_of_custody = Column(Text, nullable=True)
    target_location_id = Column(Integer, ForeignKey("inventory_locations.id", ondelete="SET NULL"), nullable=False)
    disposition = Column(
        SAEnum(InspectionDisposition, name="procurement_receipt_disposition_enum", native_enum=False),
        nullable=True,
        index=True,
    )
    released_inventory_movement_id = Column(Integer, ForeignKey("inventory_movement_ledger.id", ondelete="SET NULL"), nullable=True)
    discrepancy_notes = Column(Text, nullable=True)
    trace_documents = Column(JSON, nullable=True)

    receipt = relationship("ProcurementReceipt", back_populates="lines", lazy="joined")


class ProcurementReceivingInspection(Base):
    __tablename__ = "procurement_receiving_inspections"
    __table_args__ = (
        Index("ix_procurement_inspections_receipt", "receipt_id", "completed_at"),
    )

    id = Column(Integer, primary_key=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    receipt_id = Column(Integer, ForeignKey("procurement_receipts.id", ondelete="CASCADE"), nullable=False, index=True)
    inspection_type = Column(String(32), nullable=False, default="FULL")
    documentation_complete = Column(Boolean, nullable=False, default=False)
    physical_condition_acceptable = Column(Boolean, nullable=False, default=False)
    supplier_scope_valid = Column(Boolean, nullable=False, default=False)
    part_identity_matches = Column(Boolean, nullable=False, default=False)
    traceability_acceptable = Column(Boolean, nullable=False, default=False)
    shelf_life_acceptable = Column(Boolean, nullable=False, default=True)
    suspected_unapproved_part = Column(Boolean, nullable=False, default=False)
    disposition = Column(
        SAEnum(InspectionDisposition, name="procurement_inspection_disposition_enum", native_enum=False),
        nullable=False,
        index=True,
    )
    findings = Column(Text, nullable=True)
    conditions = Column(Text, nullable=True)
    inspected_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    receipt = relationship("ProcurementReceipt", back_populates="inspections", lazy="joined")


class ProcurementQualityHold(Base):
    __tablename__ = "procurement_quality_holds"
    __table_args__ = (
        Index("ix_procurement_holds_amo_status", "amo_id", "status"),
        Index("ix_procurement_holds_target", "target_type", "target_id"),
    )

    id = Column(Integer, primary_key=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    hold_number = Column(String(64), nullable=False, index=True)
    target_type = Column(String(32), nullable=False, index=True)
    target_id = Column(String(128), nullable=False, index=True)
    reason = Column(Text, nullable=False)
    status = Column(
        SAEnum(QualityHoldStatus, name="procurement_hold_status_enum", native_enum=False),
        nullable=False,
        default=QualityHoldStatus.ACTIVE,
        index=True,
    )
    qms_finding_id = Column(String(64), nullable=True)
    qms_car_id = Column(String(64), nullable=True)
    placed_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    placed_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    released_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    released_at = Column(DateTime(timezone=True), nullable=True)
    release_reason = Column(Text, nullable=True)


class ProcurementInvoiceMatch(Base):
    __tablename__ = "procurement_invoice_matches"
    __table_args__ = (
        UniqueConstraint("amo_id", "invoice_reference", name="uq_procurement_invoice_reference"),
        Index("ix_procurement_match_amo_status", "amo_id", "status"),
    )

    id = Column(Integer, primary_key=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    purchase_order_id = Column(Integer, ForeignKey("procurement_purchase_orders.id", ondelete="RESTRICT"), nullable=False)
    invoice_reference = Column(String(128), nullable=False)
    invoice_total = Column(Numeric(14, 2), nullable=False)
    received_total = Column(Numeric(14, 2), nullable=False, default=0)
    variance_amount = Column(Numeric(14, 2), nullable=False, default=0)
    status = Column(
        SAEnum(InvoiceMatchStatus, name="procurement_invoice_match_status_enum", native_enum=False),
        nullable=False,
        default=InvoiceMatchStatus.PENDING,
        index=True,
    )
    finance_reference = Column(String(128), nullable=True)
    notes = Column(Text, nullable=True)
    matched_by_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    matched_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class ProcurementEvent(Base):
    __tablename__ = "procurement_events"
    __table_args__ = (
        Index("ix_procurement_events_amo_occurred", "amo_id", "occurred_at"),
        Index("ix_procurement_events_entity", "entity_type", "entity_id"),
    )

    id = Column(Integer, primary_key=True)
    amo_id = Column(String(36), ForeignKey("amos.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type = Column(String(64), nullable=False, index=True)
    entity_id = Column(String(128), nullable=False, index=True)
    action = Column(String(64), nullable=False, index=True)
    actor_user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    detail = Column(JSON, nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
