export type ProcurementReferenceData = {
  locations: Array<{ id: number; code: string; name: string }>;
  parts: Array<{
    id: number;
    part_number: string;
    description?: string | null;
    uom: string;
    is_serialized: boolean;
    is_lot_controlled: boolean;
  }>;
  vendors: Array<{ id: number; code: string; name: string; currency: string; is_active: boolean }>;
};

export type ProcurementPriority = "ROUTINE" | "URGENT" | "AOG";

export type ProcurementDashboard = {
  contract: "procurement-operational-dashboard.v1";
  as_of: string;
  counters: Record<string, number>;
  action_queue: ProcurementAction[];
  supply_exceptions: Array<Record<string, unknown>>;
  quality_control: Array<Record<string, unknown>>;
  supplier_health: Array<Record<string, unknown>>;
  integration_health: Record<string, unknown>;
};

export type ProcurementAction = {
  kind: string;
  id: number;
  reference: string;
  title: string;
  status: string;
  priority?: string;
  due_date?: string | null;
};

export type SupplierApprovalScope = {
  id: number;
  category: string;
  product_family: string;
  authority: string;
  status: string;
  expires_on?: string | null;
  restrictions?: string | null;
  incoming_inspection_level: string;
};

export type ProcurementSupplier = {
  id: number;
  supplier_code: string;
  legal_name: string;
  trading_name?: string | null;
  supplier_type: string;
  vendor_id?: number | null;
  qms_supplier_id?: string | null;
  status: string;
  risk_level: string;
  email?: string | null;
  country?: string | null;
  default_currency: string;
  approval_scopes: SupplierApprovalScope[];
};

export type RequisitionLine = {
  id?: number;
  part_number?: string | null;
  description: string;
  quantity: number;
  uom: string;
  criticality: string;
  required_certification?: string | null;
};

export type ProcurementRequisition = {
  id: number;
  requisition_number: string;
  title: string;
  requesting_department: string;
  priority: ProcurementPriority;
  status: string;
  required_by?: string | null;
  source_module?: string | null;
  source_record_id?: string | null;
  work_order_id?: number | null;
  aircraft_serial_number?: string | null;
  lines: RequisitionLine[];
};

export type ProcurementRFQ = {
  id: number;
  rfq_number: string;
  requisition_id?: number | null;
  title: string;
  status: string;
  response_due_at?: string | null;
  issued_at?: string | null;
};

export type ProcurementQuote = {
  id: number;
  rfq_id: number;
  supplier_id: number;
  quote_reference: string;
  status: string;
  currency: string;
  total_amount: string | number;
  lead_time_days?: number | null;
  valid_until?: string | null;
  evaluation_score?: number | null;
};

export type ProcurementPurchaseOrderLine = {
  id: number;
  purchase_order_id: number;
  line_number: number;
  inventory_part_id?: number | null;
  part_number?: string | null;
  description: string;
  quantity: number;
  received_quantity: number;
  uom: string;
  unit_price: string | number;
  required_certification?: string | null;
};

export type ProcurementPurchaseOrder = {
  id: number;
  po_number: string;
  supplier_id: number;
  requisition_id?: number | null;
  status: string;
  priority: ProcurementPriority;
  currency: string;
  total_amount: string | number;
  promised_delivery_date?: string | null;
  supplier_ack_reference?: string | null;
  lines: ProcurementPurchaseOrderLine[];
};

export type ProcurementReceiptLine = {
  id: number;
  receipt_id: number;
  purchase_order_line_id: number;
  inventory_part_id?: number | null;
  part_number: string;
  description?: string | null;
  quantity: number;
  uom: string;
  lot_number?: string | null;
  serial_number?: string | null;
  target_location_id: number;
  disposition?: string | null;
};

export type ProcurementReceipt = {
  id: number;
  receipt_number: string;
  purchase_order_id: number;
  status: string;
  delivery_note_number?: string | null;
  airway_bill_number?: string | null;
  package_condition?: string | null;
  received_at: string;
  inspection_completed_at?: string | null;
  released_at?: string | null;
  lines: ProcurementReceiptLine[];
};

export type ProcurementQualityHold = {
  id: number;
  hold_number: string;
  target_type: string;
  target_id: string;
  reason: string;
  status: string;
  qms_finding_id?: string | null;
  qms_car_id?: string | null;
  placed_at: string;
};

export type ProcurementDocumentEntityType =
  | "REQUISITION"
  | "RFQ"
  | "QUOTE"
  | "PURCHASE_ORDER"
  | "RECEIPT"
  | "SUPPLIER"
  | "QUALITY_HOLD";

export type ProcurementDocumentSource =
  | "PHYSICAL_FORM"
  | "EXTERNAL_SOFTWARE"
  | "EMAIL"
  | "SUPPLIER_PORTAL"
  | "PORTAL_EXPORT"
  | "OTHER";

export type ProcurementDocument = {
  id: number;
  entity_type: ProcurementDocumentEntityType;
  entity_id: string;
  document_type: string;
  title: string;
  document_number?: string | null;
  revision?: string | null;
  document_date?: string | null;
  source: ProcurementDocumentSource;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  notes?: string | null;
  is_quality_evidence: boolean;
  qms_reference?: string | null;
  status: "ACTIVE" | "VOID";
  uploaded_by_user_id?: string | null;
  uploaded_at: string;
  voided_by_user_id?: string | null;
  voided_at?: string | null;
  void_reason?: string | null;
  download_url: string;
};

export type ProcurementDocumentUpload = {
  entityType: ProcurementDocumentEntityType;
  entityId: string;
  documentType: string;
  title: string;
  source: ProcurementDocumentSource;
  documentNumber?: string;
  revision?: string;
  documentDate?: string;
  notes?: string;
  isQualityEvidence?: boolean;
  qmsReference?: string;
  file: File;
};
