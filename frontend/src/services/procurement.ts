import { apiRequest } from "./apiClient";
import type {
  ProcurementDashboard,
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
