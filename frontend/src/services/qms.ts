// src/services/qms.ts
// QMS (Quality Management System) API helpers.
//
// This module is intentionally small and uses fetch + the existing auth token.
// It matches the backend routing under the Quality router:
//   - GET /quality/qms/documents
//   - GET /quality/qms/distributions
//   - GET /quality/qms/change-requests
//   - GET /quality/audits

import { getToken, handleAuthFailure } from "./auth";

const API_BASE =
  (import.meta as any).env?.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export type QMSDocumentStatus = "DRAFT" | "ACTIVE" | "OBSOLETE";
export type QMSAuditStatus = "PLANNED" | "IN_PROGRESS" | "CAP_OPEN" | "CLOSED";
export type QMSChangeRequestStatus =
  | "SUBMITTED"
  | "UNDER_REVIEW"
  | "SUBMITTED_TO_AUTHORITY"
  | "APPROVED"
  | "REJECTED"
  | "CANCELLED";

export type CARProgram = "QUALITY" | "RELIABILITY";
export type CARStatus =
  | "DRAFT"
  | "OPEN"
  | "IN_PROGRESS"
  | "PENDING_VERIFICATION"
  | "CLOSED"
  | "ESCALATED"
  | "CANCELLED";
export type CARPriority = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface QMSDocumentOut {
  id: string;
  domain: string;
  doc_type: string;
  doc_code: string;
  title: string;
  status: QMSDocumentStatus;
  current_issue_no: string | null;
  current_rev_no: string | null;
  effective_date: string | null; // YYYY-MM-DD
  current_file_ref: string | null;
  updated_at: string; // ISO datetime
  created_at: string; // ISO datetime
}

export interface QMSDistributionOut {
  id: string;
  doc_id: string;
  recipient_user_id: string;
  requires_ack: boolean;
  acked_at: string | null; // ISO datetime
  created_at: string; // ISO datetime
}

export interface QMSChangeRequestOut {
  id: string;
  domain: string;
  title: string;
  status: QMSChangeRequestStatus;
  reason: string | null;
  requested_at: string; // ISO datetime
  updated_at: string; // ISO datetime
}

export interface QMSAuditOut {
  id: string;
  domain: string;
  kind: string;
  status: QMSAuditStatus;
  audit_ref: string;
  title: string;
  planned_start: string | null; // YYYY-MM-DD
  planned_end: string | null; // YYYY-MM-DD
  updated_at: string; // ISO datetime
  created_at: string; // ISO datetime
}

export interface CAROut {
  id: string;
  program: CARProgram;
  car_number: string;
  title: string;
  summary: string;
  priority: CARPriority;
  status: CARStatus;
  due_date: string | null; // YYYY-MM-DD
  target_closure_date: string | null; // YYYY-MM-DD
  closed_at: string | null;
  escalated_at: string | null;
  finding_id: string | null;
  requested_by_user_id: string | null;
  assigned_to_user_id: string | null;
  invite_token: string;
  reminder_interval_days: number;
  next_reminder_at: string | null;
  containment_action?: string | null;
  root_cause?: string | null;
  corrective_action?: string | null;
  preventive_action?: string | null;
  evidence_ref?: string | null;
  submitted_by_name?: string | null;
  submitted_by_email?: string | null;
  submitted_at?: string | null;
  created_at: string;
  updated_at: string;
}

type QueryVal = string | number | boolean | null | undefined;

function toQuery(params: Record<string, QueryVal>): string {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === null || v === undefined) return;
    qs.set(k, String(v));
  });
  const s = qs.toString();
  return s ? `?${s}` : "";
}

async function fetchJson<T>(path: string): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    method: "GET",
    headers: {
      Accept: "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    credentials: "include",
  });

  if (res.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`QMS API ${res.status}: ${text || res.statusText}`);
  }
  return (await res.json()) as T;
}

async function sendJson<T>(path: string, method: "POST" | "PATCH", body: unknown): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body ?? {}),
    credentials: "include",
  });

  if (res.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`QMS API ${res.status}: ${text || res.statusText}`);
  }
  return (await res.json()) as T;
}

export async function qmsListDocuments(params?: {
  status_?: QMSDocumentStatus;
  domain?: string;
  doc_type?: string;
  q?: string;
}): Promise<QMSDocumentOut[]> {
  return fetchJson<QMSDocumentOut[]>(
    `/quality/qms/documents${toQuery(params ?? {})}`
  );
}

export async function qmsListDistributions(params?: {
  doc_id?: string;
  outstanding_only?: boolean;
}): Promise<QMSDistributionOut[]> {
  return fetchJson<QMSDistributionOut[]>(
    `/quality/qms/distributions${toQuery(params ?? {})}`
  );
}

export async function qmsListChangeRequests(params?: {
  domain?: string;
  status_?: QMSChangeRequestStatus;
}): Promise<QMSChangeRequestOut[]> {
  return fetchJson<QMSChangeRequestOut[]>(
    `/quality/qms/change-requests${toQuery(params ?? {})}`
  );
}

export async function qmsListAudits(params?: {
  domain?: string;
  status_?: QMSAuditStatus;
  kind?: string;
}): Promise<QMSAuditOut[]> {
  return fetchJson<QMSAuditOut[]>(`/quality/audits${toQuery(params ?? {})}`);
}

export async function qmsListCars(params?: {
  program?: CARProgram;
  status_?: CARStatus;
  assigned_to_user_id?: string;
}): Promise<CAROut[]> {
  return fetchJson<CAROut[]>(`/quality/cars${toQuery(params ?? {})}`);
}

export async function qmsCreateCar(payload: {
  program: CARProgram;
  title: string;
  summary: string;
  priority?: CARPriority;
  due_date?: string | null;
  target_closure_date?: string | null;
  assigned_to_user_id?: string | null;
  finding_id?: string | null;
}): Promise<CAROut> {
  return sendJson<CAROut>("/quality/cars", "POST", payload);
}

export async function qmsGetCarInvite(carId: string): Promise<{
  car_id: string;
  invite_token: string;
  invite_url: string;
  next_reminder_at: string | null;
  car_number: string;
  title: string;
  summary: string;
  priority: CARPriority;
  status: CARStatus;
  due_date: string | null;
  target_closure_date: string | null;
}> {
  return fetchJson(`/quality/cars/${carId}/invite`);
}

export async function qmsRescheduleCarReminder(carId: string, intervalDays: number): Promise<CAROut> {
  return sendJson<CAROut>(`/quality/cars/${carId}/reminders?reminder_interval_days=${intervalDays}`, "POST", {});
}

export async function qmsGetCarInviteByToken(token: string): Promise<{
  car_id: string;
  invite_token: string;
  invite_url: string;
  next_reminder_at: string | null;
  car_number: string;
  title: string;
  summary: string;
  priority: CARPriority;
  status: CARStatus;
  due_date: string | null;
  target_closure_date: string | null;
}> {
  return fetchJson(`/quality/cars/invite/${token}`);
}

export async function qmsSubmitCarInvite(
  token: string,
  payload: {
    submitted_by_name: string;
    submitted_by_email: string;
    containment_action?: string | null;
    root_cause?: string | null;
    corrective_action?: string | null;
    preventive_action?: string | null;
    evidence_ref?: string | null;
    due_date?: string | null;
    target_closure_date?: string | null;
  }
): Promise<CAROut> {
  return sendJson<CAROut>(`/quality/cars/invite/${token}`, "PATCH", payload);
}
