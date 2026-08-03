import { apiRequest } from "./apiClient";
import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";
import type {
  ProcurementDashboard,
  ProcurementDocument,
  ProcurementDocumentEntityType,
  ProcurementDocumentUpload,
  ProcurementPurchaseOrder,
  ProcurementReferenceData,
  ProcurementQualityHold,
  ProcurementQuote,
  ProcurementReceipt,
  ProcurementRequisition,
  ProcurementRFQ,
  ProcurementSupplier,
} from "../types/procurement";

function base(amoCode: string): string {
  return `/api/maintenance/${encodeURIComponent(amoCode)}/procurement`;
}

function json<T>(method: string, body?: unknown): RequestInit {
  return {
    method,
    body: body === undefined ? undefined : JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  };
}

export function getProcurementReferenceData(amoCode: string): Promise<ProcurementReferenceData> {
  return apiRequest<ProcurementReferenceData>(`${base(amoCode)}/reference-data`, { cacheTtlMs: 60_000 });
}

export function getProcurementDashboard(amoCode: string, signal?: AbortSignal): Promise<ProcurementDashboard> {
  return apiRequest<ProcurementDashboard>(`${base(amoCode)}/dashboard`, { signal, cacheTtlMs: 0 });
}

export function listProcurementSuppliers(amoCode: string): Promise<ProcurementSupplier[]> {
  return apiRequest<ProcurementSupplier[]>(`${base(amoCode)}/suppliers`, { cacheTtlMs: 0 });
}

export function createProcurementSupplier(amoCode: string, payload: Record<string, unknown>): Promise<ProcurementSupplier> {
  return apiRequest<ProcurementSupplier>(`${base(amoCode)}/suppliers`, json("POST", payload));
}

export function addSupplierApprovalScope(
  amoCode: string,
  supplierId: number,
  payload: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  return apiRequest(`${base(amoCode)}/suppliers/${supplierId}/approval-scopes`, json("POST", payload));
}

export function decideProcurementSupplier(
  amoCode: string,
  supplierId: number,
  payload: { action: string; reason?: string },
): Promise<ProcurementSupplier> {
  return apiRequest<ProcurementSupplier>(`${base(amoCode)}/suppliers/${supplierId}/decision`, json("POST", payload));
}

export function listProcurementRequisitions(amoCode: string): Promise<ProcurementRequisition[]> {
  return apiRequest<ProcurementRequisition[]>(`${base(amoCode)}/requisitions`, { cacheTtlMs: 0 });
}

export function createProcurementRequisition(
  amoCode: string,
  payload: Record<string, unknown>,
): Promise<ProcurementRequisition> {
  return apiRequest<ProcurementRequisition>(`${base(amoCode)}/requisitions`, json("POST", payload));
}

export function transitionProcurementRequisition(
  amoCode: string,
  requisitionId: number,
  action: string,
  reason?: string,
): Promise<ProcurementRequisition> {
  return apiRequest<ProcurementRequisition>(
    `${base(amoCode)}/requisitions/${requisitionId}/transition`,
    json("POST", { action, reason }),
  );
}

export function listProcurementRfqs(amoCode: string): Promise<ProcurementRFQ[]> {
  return apiRequest<ProcurementRFQ[]>(`${base(amoCode)}/rfqs`, { cacheTtlMs: 0 });
}

export function createProcurementRfq(amoCode: string, payload: Record<string, unknown>): Promise<ProcurementRFQ> {
  return apiRequest<ProcurementRFQ>(`${base(amoCode)}/rfqs`, json("POST", payload));
}

export function listProcurementQuotes(amoCode: string): Promise<ProcurementQuote[]> {
  return apiRequest<ProcurementQuote[]>(`${base(amoCode)}/quotes`, { cacheTtlMs: 0 });
}

export function createProcurementQuote(amoCode: string, payload: Record<string, unknown>): Promise<ProcurementQuote> {
  return apiRequest<ProcurementQuote>(`${base(amoCode)}/quotes`, json("POST", payload));
}

export function evaluateProcurementQuote(
  amoCode: string,
  quoteId: number,
  payload: Record<string, unknown>,
): Promise<ProcurementQuote> {
  return apiRequest<ProcurementQuote>(`${base(amoCode)}/quotes/${quoteId}/evaluate`, json("POST", payload));
}

export function listProcurementPurchaseOrders(amoCode: string): Promise<ProcurementPurchaseOrder[]> {
  return apiRequest<ProcurementPurchaseOrder[]>(`${base(amoCode)}/purchase-orders`, { cacheTtlMs: 0 });
}

export function createProcurementPurchaseOrder(
  amoCode: string,
  payload: Record<string, unknown>,
): Promise<ProcurementPurchaseOrder> {
  return apiRequest<ProcurementPurchaseOrder>(`${base(amoCode)}/purchase-orders`, json("POST", payload));
}

export function approveProcurementPurchaseOrder(
  amoCode: string,
  poId: number,
  stage: string,
  comment?: string,
): Promise<ProcurementPurchaseOrder> {
  return apiRequest<ProcurementPurchaseOrder>(
    `${base(amoCode)}/purchase-orders/${poId}/approve`,
    json("POST", { stage, comment }),
  );
}

export function sendProcurementPurchaseOrder(amoCode: string, poId: number): Promise<ProcurementPurchaseOrder> {
  return apiRequest<ProcurementPurchaseOrder>(`${base(amoCode)}/purchase-orders/${poId}/send`, json("POST"));
}

export function acknowledgeProcurementPurchaseOrder(
  amoCode: string,
  poId: number,
  payload: Record<string, unknown>,
): Promise<ProcurementPurchaseOrder> {
  return apiRequest<ProcurementPurchaseOrder>(
    `${base(amoCode)}/purchase-orders/${poId}/acknowledge`,
    json("POST", payload),
  );
}

export function listProcurementReceipts(amoCode: string): Promise<ProcurementReceipt[]> {
  return apiRequest<ProcurementReceipt[]>(`${base(amoCode)}/receipts`, { cacheTtlMs: 0 });
}

export function createProcurementReceipt(amoCode: string, payload: Record<string, unknown>): Promise<ProcurementReceipt> {
  return apiRequest<ProcurementReceipt>(`${base(amoCode)}/receipts`, json("POST", payload));
}

export function inspectProcurementReceipt(
  amoCode: string,
  receiptId: number,
  payload: Record<string, unknown>,
): Promise<ProcurementReceipt> {
  return apiRequest<ProcurementReceipt>(`${base(amoCode)}/receipts/${receiptId}/inspect`, json("POST", payload));
}

export function releaseProcurementReceipt(
  amoCode: string,
  receiptId: number,
  releaseComment?: string,
): Promise<ProcurementReceipt> {
  return apiRequest<ProcurementReceipt>(
    `${base(amoCode)}/receipts/${receiptId}/release`,
    json("POST", { release_comment: releaseComment }),
  );
}

export function listProcurementQualityHolds(amoCode: string): Promise<ProcurementQualityHold[]> {
  return apiRequest<ProcurementQualityHold[]>(`${base(amoCode)}/quality-holds`, { cacheTtlMs: 0 });
}

export function createProcurementQualityHold(
  amoCode: string,
  payload: Record<string, unknown>,
): Promise<ProcurementQualityHold> {
  return apiRequest<ProcurementQualityHold>(`${base(amoCode)}/quality-holds`, json("POST", payload));
}

export function releaseProcurementQualityHold(
  amoCode: string,
  holdId: number,
  releaseReason: string,
): Promise<ProcurementQualityHold> {
  return apiRequest<ProcurementQualityHold>(
    `${base(amoCode)}/quality-holds/${holdId}/release`,
    json("POST", { release_reason: releaseReason }),
  );
}

export function createProcurementInvoiceMatch(
  amoCode: string,
  payload: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  return apiRequest(`${base(amoCode)}/finance/three-way-match`, json("POST", payload));
}

export function listProcurementDocuments(
  amoCode: string,
  filters: {
    entityType?: ProcurementDocumentEntityType;
    entityId?: string;
    activeOnly?: boolean;
    verificationStatus?: string;
  } = {},
): Promise<ProcurementDocument[]> {
  const params = new URLSearchParams();
  if (filters.entityType) params.set("entity_type", filters.entityType);
  if (filters.entityId) params.set("entity_id", filters.entityId);
  if (filters.activeOnly === false) params.set("active_only", "false");
  if (filters.verificationStatus) params.set("verification_status", filters.verificationStatus);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return apiRequest<ProcurementDocument[]>(`${base(amoCode)}/documents${suffix}`, { cacheTtlMs: 0 });
}

function appendOptional(body: FormData, key: string, value?: string): void {
  if (value?.trim()) body.append(key, value.trim());
}

function uploadError(xhr: XMLHttpRequest): string {
  try {
    const body = JSON.parse(xhr.responseText || "{}") as { detail?: unknown; message?: unknown };
    const detail = body.detail ?? body.message;
    if (typeof detail === "string" && detail.trim()) return detail.trim();
    if (detail != null) return JSON.stringify(detail);
  } catch {
    if (xhr.responseText?.trim()) return xhr.responseText.trim();
  }
  return xhr.statusText || "The document evidence could not be retained.";
}

export function uploadProcurementDocument(
  amoCode: string,
  payload: ProcurementDocumentUpload,
  onProgress?: (percentage: number) => void,
): Promise<ProcurementDocument> {
  const body = new FormData();
  body.append("entity_type", payload.entityType);
  body.append("entity_id", payload.entityId);
  body.append("document_type", payload.documentType);
  body.append("title", payload.title);
  body.append("source", payload.source);
  appendOptional(body, "document_number", payload.documentNumber);
  appendOptional(body, "revision", payload.revision);
  appendOptional(body, "document_date", payload.documentDate);
  appendOptional(body, "physical_reference", payload.physicalReference);
  appendOptional(body, "physical_location", payload.physicalLocation);
  appendOptional(body, "external_system", payload.externalSystem);
  appendOptional(body, "external_reference", payload.externalReference);
  appendOptional(body, "external_url", payload.externalUrl);
  appendOptional(body, "dms_document_id", payload.dmsDocumentId);
  appendOptional(body, "dms_revision_id", payload.dmsRevisionId);
  appendOptional(body, "notes", payload.notes);
  body.append("is_quality_evidence", String(Boolean(payload.isQualityEvidence)));
  appendOptional(body, "qms_reference", payload.qmsReference);
  if (payload.file) body.append("file", payload.file, payload.file.name);

  return new Promise<ProcurementDocument>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${getApiBaseUrl()}${base(amoCode)}/documents`);
    xhr.timeout = 90_000;
    const headers = new Headers(authHeaders());
    headers.forEach((value, key) => xhr.setRequestHeader(key, value));
    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return;
      onProgress?.(Math.min(99, Math.round((event.loaded / event.total) * 100)));
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress?.(100);
        try {
          resolve(JSON.parse(xhr.responseText) as ProcurementDocument);
        } catch {
          reject(new Error("The server returned an invalid document response."));
        }
        return;
      }
      reject(new Error(uploadError(xhr)));
    };
    xhr.onerror = () => reject(new Error("The upload connection failed. Check network access and retry."));
    xhr.ontimeout = () => reject(new Error("The document upload timed out. Check the connection and retry."));
    xhr.onabort = () => reject(new Error("The document upload was cancelled."));
    xhr.send(body);
  });
}

export function verifyProcurementDocument(
  amoCode: string,
  documentId: number,
  outcome: "VERIFIED" | "REJECTED",
  notes: string,
): Promise<ProcurementDocument> {
  return apiRequest<ProcurementDocument>(
    `${base(amoCode)}/documents/${documentId}/verify`,
    json("POST", { outcome, notes }),
  );
}

export function voidProcurementDocument(
  amoCode: string,
  documentId: number,
  reason: string,
): Promise<ProcurementDocument> {
  return apiRequest<ProcurementDocument>(
    `${base(amoCode)}/documents/${documentId}/void`,
    json("POST", { reason }),
  );
}

export async function downloadProcurementDocument(
  amoCode: string,
  document: ProcurementDocument,
): Promise<void> {
  if (!document.download_url) throw new Error("This evidence record is a reference link and has no retained file.");
  const response = await fetch(
    `${getApiBaseUrl()}${base(amoCode)}/documents/${document.id}/download`,
    { headers: authHeaders() },
  );
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail || "The retained document could not be downloaded.");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = window.document.createElement("a");
  link.href = url;
  link.download = document.original_filename || `procurement-document-${document.id}`;
  window.document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
