import {
  addSupplierApprovalScope,
  approveProcurementPurchaseOrder,
  createProcurementInvoiceMatch,
  createProcurementPurchaseOrder,
  createProcurementQualityHold,
  createProcurementQuote,
  createProcurementReceipt,
  createProcurementRequisition,
  createProcurementRfq,
  createProcurementSupplier,
  evaluateProcurementQuote,
  inspectProcurementReceipt,
  releaseProcurementQualityHold,
  releaseProcurementReceipt,
} from "../../services/procurement";
import type { ProcurementRequisition } from "../../types/procurement";
import type { FormState, Modal, WorkspaceData } from "./procurementUiModel";

export async function submitProcurementForm(
  amoCode: string,
  modal: Exclude<Modal, null>,
  form: FormState,
  data: WorkspaceData,
): Promise<unknown> {
  const text = (name: string) => String(form[name] || "").trim();
  const number = (name: string) => Number(form[name] || 0);
  const yes = (name: string) => form[name] === true || form[name] === "yes";
  const selectedPart = data.referenceData.parts.find((item) => item.id === number("partId"));
  const selectedOrder = data.orders.find((item) => item.id === number("poId"));
  const selectedLine = selectedOrder?.lines.find((item) => item.id === number("poLineId"));

  if (modal === "requisition") {
    return createProcurementRequisition(amoCode, {
      requisition_number: text("number"),
      title: text("title"),
      requesting_department: text("department"),
      priority: text("priority") || "ROUTINE",
      required_by: text("requiredBy") || null,
      justification: text("justification") || null,
      source_module: text("sourceModule") || null,
      source_record_id: text("sourceRecordId") || null,
      work_order_id: number("workOrderId") || null,
      aircraft_serial_number: text("aircraftSerial") || null,
      lines: [{
        inventory_part_id: number("partId") || null,
        item_type: "PART",
        part_number: selectedPart?.part_number || text("partNumber") || null,
        description: text("description") || selectedPart?.description || selectedPart?.part_number,
        quantity: number("quantity"),
        uom: selectedPart?.uom || text("uom") || "EA",
        criticality: text("criticality") || "STANDARD",
        required_certification: text("certification") || null,
        delivery_location_id: number("locationId") || null,
      }],
    }) as Promise<ProcurementRequisition>;
  }
  if (modal === "supplier") {
    return createProcurementSupplier(amoCode, {
      supplier_code: text("code"), legal_name: text("name"), trading_name: text("tradingName") || null,
      supplier_type: text("supplierType") || "DISTRIBUTOR", vendor_id: number("vendorId") || null,
      risk_level: text("risk") || "MEDIUM", email: text("email") || null, country: text("country") || null,
      default_currency: text("currency") || "USD", quality_contact_name: text("qualityContact") || null,
      quality_contact_email: text("qualityEmail") || null,
    });
  }
  if (modal === "scope") {
    return addSupplierApprovalScope(amoCode, number("supplierId"), {
      site_code: text("siteCode") || "PRIMARY", category: text("category"), product_family: text("productFamily") || "ALL",
      authority: text("authority") || "TENANT_QMS", approval_number: text("approvalNumber") || null,
      effective_on: text("effectiveOn") || null, expires_on: text("expiresOn") || null,
      restrictions: text("restrictions") || null, incoming_inspection_level: text("inspectionLevel") || "STANDARD",
      evidence_reference: text("evidenceReference") || null, qms_evaluation_id: text("qmsEvaluationId"),
      qms_audit_id: text("qmsAuditId") || null,
    });
  }
  if (modal === "rfq") {
    return createProcurementRfq(amoCode, {
      rfq_number: text("number"), requisition_id: number("requisitionId"), title: text("title"),
      response_due_at: text("dueAt") || null, terms: text("terms") || null,
      quality_clauses: text("qualityClauses") || null,
      supplier_ids: text("supplierIds").split(",").map(Number).filter(Boolean),
      issue_immediately: yes("issueImmediately"),
    });
  }
  if (modal === "quote") {
    return createProcurementQuote(amoCode, {
      rfq_id: number("rfqId"), supplier_id: number("supplierId"), quote_reference: text("reference"),
      currency: text("currency") || "USD", freight_amount: number("freight"), tax_amount: number("tax"),
      lead_time_days: number("leadTime") || null, valid_until: text("validUntil") || null,
      certification_offered: text("certification") || null, technical_deviations: text("deviations") || null,
      lines: [{ quantity: number("quantity"), uom: text("uom") || "EA", unit_price: number("unitPrice"),
        manufacturer: text("manufacturer") || null, promised_date: text("promisedDate") || null,
        traceability_statement: text("traceability") || null, is_technically_compliant: true,
        deviation: text("deviations") || null }],
    });
  }
  if (modal === "quoteEvaluation") {
    return evaluateProcurementQuote(amoCode, number("quoteId"), {
      status: text("evaluationStatus"),
      evaluation_score: text("evaluationScore") ? number("evaluationScore") : null,
      evaluation_notes: text("evaluationNotes"),
    });
  }
  if (modal === "po") {
    return createProcurementPurchaseOrder(amoCode, {
      po_number: text("number"), supplier_id: number("supplierId"), quote_id: number("quoteId") || null,
      requisition_id: number("requisitionId") || null, priority: text("priority") || "ROUTINE",
      currency: text("currency") || "USD", freight_amount: number("freight"), tax_amount: number("tax"),
      delivery_terms: text("deliveryTerms") || null, payment_terms: text("paymentTerms") || null,
      quality_clauses: text("qualityClauses") || null, ship_to_location_id: number("locationId") || null,
      promised_delivery_date: text("promisedDate") || null,
      lines: [{ inventory_part_id: number("partId") || null, part_number: selectedPart?.part_number || text("partNumber") || null,
        description: text("description") || selectedPart?.description || selectedPart?.part_number,
        quantity: number("quantity"), uom: selectedPart?.uom || text("uom") || "EA", unit_price: number("unitPrice"),
        manufacturer: text("manufacturer") || null, required_certification: text("certification") || null,
        promised_date: text("promisedDate") || null, work_order_id: number("workOrderId") || null,
        aircraft_serial_number: text("aircraftSerial") || null }],
    });
  }
  if (modal === "poApproval") {
    return approveProcurementPurchaseOrder(amoCode, number("poId"), text("approvalStage"), text("approvalComment"));
  }
  if (modal === "receipt") {
    return createProcurementReceipt(amoCode, {
      receipt_number: text("number"), purchase_order_id: number("poId"),
      delivery_note_number: text("deliveryNote") || null, airway_bill_number: text("airwayBill") || null,
      supplier_shipment_reference: text("shipmentReference") || null, package_condition: text("packageCondition") || null,
      quarantine_location_id: number("quarantineLocationId") || null,
      lines: [{ purchase_order_line_id: number("poLineId"), inventory_part_id: selectedLine?.inventory_part_id || null,
        part_number: selectedLine?.part_number || "UNSPECIFIED", description: selectedLine?.description || null,
        quantity: number("quantity"), uom: selectedLine?.uom || "EA", lot_number: text("lotNumber") || null,
        serial_number: text("serialNumber") || null, expiry_date: text("expiryDate") || null,
        release_document_type: text("releaseDocumentType") || null,
        release_document_number: text("releaseDocumentNumber") || null,
        release_document_issuer: text("releaseDocumentIssuer") || null,
        release_document_date: text("releaseDocumentDate") || null,
        chain_of_custody: text("chainOfCustody") || null, target_location_id: number("targetLocationId") }],
    });
  }
  if (modal === "inspection") {
    return inspectProcurementReceipt(amoCode, number("receiptId"), {
      documentation_complete: yes("documentationComplete"),
      physical_condition_acceptable: yes("physicalCondition"),
      supplier_scope_valid: yes("supplierScope"),
      part_identity_matches: yes("partIdentity"),
      traceability_acceptable: yes("traceabilityAcceptable"),
      shelf_life_acceptable: yes("shelfLife"),
      suspected_unapproved_part: yes("suspectedUnapprovedPart"),
      disposition: text("disposition"),
      findings: text("findings") || null,
      conditions: text("conditions") || null,
      line_dispositions: {},
    });
  }
  if (modal === "receiptRelease") {
    return releaseProcurementReceipt(amoCode, number("receiptId"), text("releaseComment"));
  }
  if (modal === "hold") {
    return createProcurementQualityHold(amoCode, {
      hold_number: text("number"), target_type: text("targetType"), target_id: text("targetId"),
      reason: text("reason"), qms_finding_id: text("qmsFindingId") || null, qms_car_id: text("qmsCarId") || null,
    });
  }
  if (modal === "holdRelease") {
    return releaseProcurementQualityHold(amoCode, number("holdId"), text("releaseReason"));
  }
  return createProcurementInvoiceMatch(amoCode, {
    purchase_order_id: number("poId"), invoice_reference: text("invoiceReference"),
    invoice_total: number("invoiceTotal"), finance_reference: text("financeReference") || null,
    tolerance_amount: number("tolerance") || 0.01, notes: text("notes") || null,
  });
}
