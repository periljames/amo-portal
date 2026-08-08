import { apiGet } from "./crs";
import { getApiBaseUrl } from "./config";
import { authHeaders } from "./auth";
import { downloadWithFetch, type DownloadedFile } from "../utils/downloads";
import type {
  ResolvedEntitlement,
  UsageMeter,
  Invoice,
  BillingAuditLog,
  InvoiceDetail,
  BillingAccessStatus,
} from "../types/billing";

export async function fetchBillingAccessStatus(): Promise<BillingAccessStatus> {
  return apiGet<BillingAccessStatus>("/billing/access-status", {
    headers: authHeaders(),
  });
}

export async function fetchEntitlements(): Promise<ResolvedEntitlement[]> {
  return apiGet<ResolvedEntitlement[]>("/billing/entitlements", {
    headers: authHeaders(),
  });
}

export async function fetchUsageMeters(): Promise<UsageMeter[]> {
  return apiGet<UsageMeter[]>("/billing/usage-meters", {
    headers: authHeaders(),
  });
}

export async function fetchBillingAuditLogs(params: {
  amo_id?: string;
  event_type?: string;
  limit?: number;
}): Promise<BillingAuditLog[]> {
  const query = new URLSearchParams();
  if (params.amo_id) query.set("amo_id", params.amo_id);
  if (params.event_type) query.set("event_type", params.event_type);
  if (params.limit) query.set("limit", params.limit.toString());
  const suffix = query.toString();
  return apiGet<BillingAuditLog[]>(suffix ? `/billing/audit?${suffix}` : "/billing/audit", {
    headers: authHeaders(),
  });
}

export async function fetchInvoices(): Promise<Invoice[]> {
  return apiGet<Invoice[]>("/billing/invoices", {
    headers: authHeaders(),
  });
}

export async function fetchInvoiceDetail(invoiceId: string): Promise<InvoiceDetail> {
  return apiGet<InvoiceDetail>(`/billing/invoices/${encodeURIComponent(invoiceId)}`, {
    headers: authHeaders(),
  });
}

export function getInvoiceDocumentUrl(invoiceId: string, format: "html" | "pdf") {
  return `${getApiBaseUrl()}/billing/invoices/${encodeURIComponent(invoiceId)}/document?format=${format}`;
}

export async function fetchInvoiceDocument(
  invoiceId: string,
  format: "html" | "pdf",
): Promise<DownloadedFile> {
  return downloadWithFetch(
    getInvoiceDocumentUrl(invoiceId, format),
    { headers: authHeaders() },
    `invoice-${invoiceId}.${format}`,
    120_000,
  );
}

export async function exportInvoicesCsv(): Promise<DownloadedFile> {
  return downloadWithFetch(
    `${getApiBaseUrl()}/billing/invoices/export?format=csv`,
    { headers: authHeaders() },
    "billing-invoices.csv",
    120_000,
  );
}

export async function exportBillingAuditCsv(params?: {
  amo_id?: string;
  event_type?: string;
  limit?: number;
}): Promise<DownloadedFile> {
  const query = new URLSearchParams();
  if (params?.amo_id) query.set("amo_id", params.amo_id);
  if (params?.event_type) query.set("event_type", params.event_type);
  if (params?.limit) query.set("limit", String(params.limit));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return downloadWithFetch(
    `${getApiBaseUrl()}/billing/audit/export${suffix}`,
    { headers: authHeaders() },
    "billing-audit.csv",
    120_000,
  );
}
