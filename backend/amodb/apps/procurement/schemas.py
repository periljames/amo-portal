from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Optional

from pydantic import BaseModel, Field, model_validator

from . import models


class ReferenceLocation(BaseModel):
    id: int
    code: str
    name: str

    class Config:
        from_attributes = True


class ReferencePart(BaseModel):
    id: int
    part_number: str
    description: Optional[str] = None
    uom: str
    is_serialized: bool
    is_lot_controlled: bool

    class Config:
        from_attributes = True


class ReferenceVendor(BaseModel):
    id: int
    code: str
    name: str
    currency: str
    is_active: bool

    class Config:
        from_attributes = True


class ProcurementReferenceData(BaseModel):
    locations: List[ReferenceLocation] = Field(default_factory=list)
    parts: List[ReferencePart] = Field(default_factory=list)
    vendors: List[ReferenceVendor] = Field(default_factory=list)


class SupplierCreate(BaseModel):
    supplier_code: str = Field(..., min_length=2, max_length=64)
    legal_name: str = Field(..., min_length=2, max_length=255)
    trading_name: Optional[str] = None
    supplier_type: str = "DISTRIBUTOR"
    vendor_id: Optional[int] = None
    qms_supplier_id: Optional[str] = None
    risk_level: models.SupplierRiskLevel = models.SupplierRiskLevel.MEDIUM
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    country: Optional[str] = None
    physical_address: Optional[str] = None
    payment_terms: Optional[str] = None
    default_currency: str = "USD"
    quality_contact_name: Optional[str] = None
    quality_contact_email: Optional[str] = None
    notes: Optional[str] = None


class SupplierUpdate(BaseModel):
    legal_name: Optional[str] = None
    trading_name: Optional[str] = None
    supplier_type: Optional[str] = None
    vendor_id: Optional[int] = None
    qms_supplier_id: Optional[str] = None
    risk_level: Optional[models.SupplierRiskLevel] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    country: Optional[str] = None
    physical_address: Optional[str] = None
    payment_terms: Optional[str] = None
    default_currency: Optional[str] = None
    quality_contact_name: Optional[str] = None
    quality_contact_email: Optional[str] = None
    notes: Optional[str] = None


class ApprovalScopeCreate(BaseModel):
    site_code: str = "PRIMARY"
    category: str = Field(..., min_length=2, max_length=64)
    product_family: str = "ALL"
    manufacturer: Optional[str] = None
    authority: str = "TENANT_QMS"
    approval_number: Optional[str] = None
    effective_on: Optional[date] = None
    expires_on: Optional[date] = None
    restrictions: Optional[str] = None
    incoming_inspection_level: str = "STANDARD"
    evidence_reference: Optional[str] = None
    qms_evaluation_id: Optional[str] = None
    qms_audit_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.effective_on and self.expires_on and self.expires_on < self.effective_on:
            raise ValueError("expires_on must be on or after effective_on")
        return self


class ApprovalScopeRead(ApprovalScopeCreate):
    id: int
    amo_id: str
    supplier_id: int
    status: models.ApprovalScopeStatus
    approved_by_user_id: Optional[str] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SupplierRead(SupplierCreate):
    id: int
    amo_id: str
    status: models.SupplierLifecycleStatus
    is_active: bool
    approved_at: Optional[datetime] = None
    approved_by_user_id: Optional[str] = None
    suspended_at: Optional[datetime] = None
    suspension_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    approval_scopes: List[ApprovalScopeRead] = Field(default_factory=list)

    class Config:
        from_attributes = True


class SupplierDecision(BaseModel):
    action: str = Field(..., pattern="^(APPROVE|CONDITIONALLY_APPROVE|RESTRICT|SUSPEND|REACTIVATE|REJECT|ARCHIVE)$")
    reason: Optional[str] = None


class RequisitionLineCreate(BaseModel):
    inventory_part_id: Optional[int] = None
    item_type: str = "PART"
    part_number: Optional[str] = None
    description: str = Field(..., min_length=2)
    quantity: float = Field(..., gt=0)
    uom: str = "EA"
    technical_specification: Optional[str] = None
    controlled_document_id: Optional[str] = None
    controlled_document_revision: Optional[str] = None
    criticality: str = "STANDARD"
    approved_manufacturers: Optional[List[str]] = None
    required_certification: Optional[str] = None
    alternates_allowed: bool = False
    shelf_life_minimum_days: Optional[int] = Field(None, ge=0)
    delivery_location_id: Optional[int] = None
    source_module: Optional[str] = None
    source_record_id: Optional[str] = None
    notes: Optional[str] = None


class RequisitionCreate(BaseModel):
    requisition_number: str = Field(..., min_length=3, max_length=64)
    title: str = Field(..., min_length=3, max_length=255)
    requesting_department: str
    priority: models.ProcurementPriority = models.ProcurementPriority.ROUTINE
    required_by: Optional[date] = None
    cost_centre: Optional[str] = None
    project_code: Optional[str] = None
    budget_reference: Optional[str] = None
    justification: Optional[str] = None
    source_module: Optional[str] = None
    source_record_id: Optional[str] = None
    work_order_id: Optional[int] = None
    task_card_id: Optional[int] = None
    aircraft_serial_number: Optional[str] = None
    lines: List[RequisitionLineCreate] = Field(..., min_length=1)


class RequisitionLineRead(RequisitionLineCreate):
    id: int
    requisition_id: int
    line_number: int

    class Config:
        from_attributes = True


class RequisitionRead(BaseModel):
    id: int
    amo_id: str
    requisition_number: str
    title: str
    requesting_department: str
    priority: models.ProcurementPriority
    status: models.RequisitionStatus
    required_by: Optional[date] = None
    cost_centre: Optional[str] = None
    project_code: Optional[str] = None
    budget_reference: Optional[str] = None
    justification: Optional[str] = None
    source_module: Optional[str] = None
    source_record_id: Optional[str] = None
    work_order_id: Optional[int] = None
    task_card_id: Optional[int] = None
    aircraft_serial_number: Optional[str] = None
    requested_by_user_id: Optional[str] = None
    submitted_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    lines: List[RequisitionLineRead] = Field(default_factory=list)

    class Config:
        from_attributes = True


class RequisitionTransition(BaseModel):
    action: str = Field(..., pattern="^(SUBMIT|TECHNICAL_APPROVE|BUDGET_APPROVE|APPROVE|REJECT|CANCEL|CLOSE)$")
    reason: Optional[str] = None


class RFQCreate(BaseModel):
    rfq_number: str = Field(..., min_length=3, max_length=64)
    requisition_id: int
    title: str = Field(..., min_length=3)
    response_due_at: Optional[datetime] = None
    terms: Optional[str] = None
    quality_clauses: Optional[str] = None
    supplier_ids: List[int] = Field(..., min_length=1)
    issue_immediately: bool = True


class RFQRead(BaseModel):
    id: int
    amo_id: str
    rfq_number: str
    requisition_id: Optional[int] = None
    title: str
    status: models.RFQStatus
    response_due_at: Optional[datetime] = None
    terms: Optional[str] = None
    quality_clauses: Optional[str] = None
    issued_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QuoteLineCreate(BaseModel):
    requisition_line_id: Optional[int] = None
    supplier_part_number: Optional[str] = None
    manufacturer: Optional[str] = None
    quantity: float = Field(..., gt=0)
    uom: str = "EA"
    unit_price: Decimal = Field(..., ge=0)
    promised_date: Optional[date] = None
    traceability_statement: Optional[str] = None
    is_technically_compliant: bool = True
    deviation: Optional[str] = None


class QuoteCreate(BaseModel):
    rfq_id: int
    supplier_id: int
    quote_reference: str = Field(..., min_length=2)
    currency: str = "USD"
    freight_amount: Decimal = Decimal("0")
    tax_amount: Decimal = Decimal("0")
    lead_time_days: Optional[int] = Field(None, ge=0)
    valid_until: Optional[date] = None
    certification_offered: Optional[str] = None
    warranty_terms: Optional[str] = None
    technical_deviations: Optional[str] = None
    lines: List[QuoteLineCreate] = Field(..., min_length=1)


class QuoteEvaluate(BaseModel):
    status: models.QuoteStatus
    evaluation_score: Optional[float] = Field(None, ge=0, le=100)
    evaluation_notes: Optional[str] = None


class QuoteRead(BaseModel):
    id: int
    amo_id: str
    rfq_id: int
    supplier_id: int
    quote_reference: str
    status: models.QuoteStatus
    currency: str
    freight_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    lead_time_days: Optional[int] = None
    valid_until: Optional[date] = None
    certification_offered: Optional[str] = None
    technical_deviations: Optional[str] = None
    evaluation_score: Optional[float] = None
    evaluation_notes: Optional[str] = None
    received_at: datetime
    evaluated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PurchaseOrderLineInput(BaseModel):
    requisition_line_id: Optional[int] = None
    inventory_part_id: Optional[int] = None
    part_number: Optional[str] = None
    description: str
    manufacturer: Optional[str] = None
    quantity: float = Field(..., gt=0)
    uom: str = "EA"
    unit_price: Decimal = Field(..., ge=0)
    required_certification: Optional[str] = None
    promised_date: Optional[date] = None
    work_order_id: Optional[int] = None
    task_card_id: Optional[int] = None
    aircraft_serial_number: Optional[str] = None
    notes: Optional[str] = None


class PurchaseOrderCreate(BaseModel):
    po_number: str = Field(..., min_length=3, max_length=64)
    supplier_id: int
    quote_id: Optional[int] = None
    requisition_id: Optional[int] = None
    priority: models.ProcurementPriority = models.ProcurementPriority.ROUTINE
    currency: str = "USD"
    freight_amount: Decimal = Decimal("0")
    tax_amount: Decimal = Decimal("0")
    delivery_terms: Optional[str] = None
    payment_terms: Optional[str] = None
    quality_clauses: Optional[str] = None
    ship_to_location_id: Optional[int] = None
    promised_delivery_date: Optional[date] = None
    override_reference: Optional[str] = None
    override_reason: Optional[str] = None
    lines: List[PurchaseOrderLineInput] = Field(..., min_length=1)


class PurchaseOrderApproval(BaseModel):
    stage: str = Field(..., pattern="^(TECHNICAL|BUDGET|PROCUREMENT|QUALITY|FINAL)$")
    comment: Optional[str] = None


class PurchaseOrderAcknowledge(BaseModel):
    supplier_ack_reference: Optional[str] = None
    promised_delivery_date: Optional[date] = None


class PurchaseOrderLineRead(BaseModel):
    id: int
    purchase_order_id: int
    requisition_line_id: Optional[int] = None
    inventory_part_id: Optional[int] = None
    line_number: int
    part_number: Optional[str] = None
    description: str
    manufacturer: Optional[str] = None
    quantity: float
    received_quantity: float
    uom: str
    unit_price: Decimal
    required_certification: Optional[str] = None
    promised_date: Optional[date] = None
    work_order_id: Optional[int] = None
    task_card_id: Optional[int] = None
    aircraft_serial_number: Optional[str] = None

    class Config:
        from_attributes = True


class PurchaseOrderRead(BaseModel):
    id: int
    amo_id: str
    po_number: str
    supplier_id: int
    quote_id: Optional[int] = None
    requisition_id: Optional[int] = None
    status: models.PurchaseOrderStatus
    priority: models.ProcurementPriority
    currency: str
    subtotal: Decimal
    freight_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    promised_delivery_date: Optional[date] = None
    supplier_ack_reference: Optional[str] = None
    approved_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    lines: List[PurchaseOrderLineRead] = Field(default_factory=list)

    class Config:
        from_attributes = True


class ReceiptLineCreate(BaseModel):
    purchase_order_line_id: int
    inventory_part_id: Optional[int] = None
    part_number: str
    description: Optional[str] = None
    manufacturer: Optional[str] = None
    quantity: float = Field(..., gt=0)
    uom: str = "EA"
    lot_number: Optional[str] = None
    serial_number: Optional[str] = None
    manufacture_date: Optional[date] = None
    expiry_date: Optional[date] = None
    release_document_type: Optional[str] = None
    release_document_number: Optional[str] = None
    release_document_issuer: Optional[str] = None
    release_document_date: Optional[date] = None
    chain_of_custody: Optional[str] = None
    target_location_id: int
    trace_documents: Optional[List[dict[str, Any]]] = None


class ReceiptCreate(BaseModel):
    receipt_number: str = Field(..., min_length=3, max_length=64)
    purchase_order_id: int
    delivery_note_number: Optional[str] = None
    airway_bill_number: Optional[str] = None
    supplier_shipment_reference: Optional[str] = None
    package_condition: Optional[str] = None
    quarantine_location_id: Optional[int] = None
    notes: Optional[str] = None
    lines: List[ReceiptLineCreate] = Field(..., min_length=1)


class ReceiptLineRead(ReceiptLineCreate):
    id: int
    receipt_id: int
    disposition: Optional[models.InspectionDisposition] = None
    released_inventory_movement_id: Optional[int] = None
    discrepancy_notes: Optional[str] = None

    class Config:
        from_attributes = True


class ReceiptRead(BaseModel):
    id: int
    amo_id: str
    receipt_number: str
    purchase_order_id: int
    status: models.ReceiptStatus
    delivery_note_number: Optional[str] = None
    airway_bill_number: Optional[str] = None
    supplier_shipment_reference: Optional[str] = None
    package_condition: Optional[str] = None
    received_at: datetime
    quarantine_location_id: Optional[int] = None
    inspection_completed_at: Optional[datetime] = None
    released_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    lines: List[ReceiptLineRead] = Field(default_factory=list)

    class Config:
        from_attributes = True


class InspectionCreate(BaseModel):
    documentation_complete: bool
    physical_condition_acceptable: bool
    supplier_scope_valid: bool
    part_identity_matches: bool
    traceability_acceptable: bool
    shelf_life_acceptable: bool = True
    suspected_unapproved_part: bool = False
    disposition: models.InspectionDisposition
    findings: Optional[str] = None
    conditions: Optional[str] = None
    line_dispositions: dict[int, models.InspectionDisposition] = Field(default_factory=dict)


class ReceiptRelease(BaseModel):
    release_comment: Optional[str] = None


class QualityHoldCreate(BaseModel):
    hold_number: str
    target_type: str
    target_id: str
    reason: str
    qms_finding_id: Optional[str] = None
    qms_car_id: Optional[str] = None


class QualityHoldRelease(BaseModel):
    release_reason: str


class QualityHoldRead(BaseModel):
    id: int
    amo_id: str
    hold_number: str
    target_type: str
    target_id: str
    reason: str
    status: models.QualityHoldStatus
    qms_finding_id: Optional[str] = None
    qms_car_id: Optional[str] = None
    placed_at: datetime
    released_at: Optional[datetime] = None
    release_reason: Optional[str] = None

    class Config:
        from_attributes = True


class InvoiceMatchCreate(BaseModel):
    purchase_order_id: int
    invoice_reference: str
    invoice_total: Decimal
    finance_reference: Optional[str] = None
    tolerance_amount: Decimal = Decimal("0.01")
    notes: Optional[str] = None


class InvoiceMatchRead(BaseModel):
    id: int
    amo_id: str
    purchase_order_id: int
    invoice_reference: str
    invoice_total: Decimal
    received_total: Decimal
    variance_amount: Decimal
    status: models.InvoiceMatchStatus
    finance_reference: Optional[str] = None
    matched_at: datetime

    class Config:
        from_attributes = True


class DashboardResponse(BaseModel):
    contract: str = "procurement-operational-dashboard.v1"
    as_of: datetime
    counters: dict[str, int]
    action_queue: list[dict[str, Any]]
    supply_exceptions: list[dict[str, Any]]
    quality_control: list[dict[str, Any]]
    supplier_health: list[dict[str, Any]]
    integration_health: dict[str, Any]
