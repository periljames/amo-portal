// src/services/qms.ts
// QMS (Quality Management System) API helpers.
//
// This module is intentionally small and uses fetch + the existing auth token.
// Mature workflow helpers still use the legacy backend compatibility API
// while the visible frontend route surface has been consolidated under
// /maintenance/:amoCode/qms. Do not delete these compatibility calls until
// the canonical /api/maintenance/:amoCode/qms endpoints have response-shape
// parity for the detailed document, audit, CAR, AeroDoc, and manpower flows.

import { getToken, handleAuthFailure } from "./auth";
import { getApiBaseUrl } from "./config";
import { beginBackgroundLoading, beginLoading, endBackgroundLoading, endLoading } from "./loading";

export type QMSDocumentStatus = "DRAFT" | "ACTIVE" | "OBSOLETE";
export type QMSAuditStatus = "PLANNED" | "IN_PROGRESS" | "CAP_OPEN" | "CLOSED";
export type QMSAuditScheduleFrequency =
  | "ONE_TIME"
  | "MONTHLY"
  | "QUARTERLY"
  | "BI_ANNUAL"
  | "ANNUAL";
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
  audit_scope_id?: string | null;
  audit_scope_code?: string | null;
  status: QMSAuditStatus;
  audit_ref: string;
  title: string;
  scope?: string | null;
  criteria?: string | null;
  auditee?: string | null;
  auditee_email?: string | null;
  auditee_user_id?: string | null;
  auditee_user_name?: string | null;
  external_auditees?: QMSExternalAuditeeContact[] | null;
  lead_auditor_user_id?: string | null;
  lead_auditor_name?: string | null;
  observer_auditor_user_id?: string | null;
  observer_auditor_name?: string | null;
  assistant_auditor_user_id?: string | null;
  assistant_auditor_name?: string | null;
  notify_auditors?: boolean;
  notify_auditees?: boolean;
  reminder_interval_days?: number;
  planned_start: string | null; // YYYY-MM-DD
  planned_end: string | null; // YYYY-MM-DD
  actual_start?: string | null;
  actual_end?: string | null;
  report_file_ref?: string | null;
  checklist_file_ref?: string | null;
  retention_until?: string | null;
  upcoming_notice_sent_at?: string | null;
  day_of_notice_sent_at?: string | null;
  updated_at: string; // ISO datetime
  created_at: string; // ISO datetime
  deleted_at?: string | null;
  deleted_by_user_id?: string | null;
  delete_reason?: string | null;
}

export interface QMSExternalAuditeeContact {
  first_name: string;
  last_name: string;
  email: string;
  phone_contact?: string | null;
  designation: string;
}

export interface QMSAuditScopeOut {
  id: string;
  amo_id: string;
  code: string;
  name: string;
  description?: string | null;
  party_level: "FIRST_PARTY" | "SECOND_PARTY" | "THIRD_PARTY" | "REGULATORY" | string;
  default_kind: string;
  is_active: boolean;
  is_system_default: boolean;
  sort_order: number;
  created_by_user_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface QMSAuditScheduleOut {
  id: string;
  domain: string;
  kind: string;
  audit_scope_id?: string | null;
  audit_scope_code?: string | null;
  frequency: QMSAuditScheduleFrequency;
  title: string;
  scope?: string | null;
  criteria?: string | null;
  auditee?: string | null;
  auditee_email?: string | null;
  auditee_user_id?: string | null;
  auditee_user_name?: string | null;
  external_auditees?: QMSExternalAuditeeContact[] | null;
  lead_auditor_user_id?: string | null;
  lead_auditor_name?: string | null;
  observer_auditor_user_id?: string | null;
  observer_auditor_name?: string | null;
  assistant_auditor_user_id?: string | null;
  assistant_auditor_name?: string | null;
  notify_auditors?: boolean;
  notify_auditees?: boolean;
  reminder_interval_days?: number;
  duration_days: number;
  next_due_date: string;
  last_run_at?: string | null;
  is_active: boolean;
  created_by_user_id?: string | null;
  created_at: string;
  deleted_at?: string | null;
  deleted_by_user_id?: string | null;
  delete_reason?: string | null;
}

export interface QMSAuditParticipantOut {
  role: string;
  user_id: string | null;
  name: string | null;
  email: string | null;
}

export interface QMSAuditWorkspaceSummaryOut {
  audit_id: string;
  audit_ref: string;
  title: string;
  status: string;
  domain: string;
  kind: string;
  planned_start: string | null;
  planned_end: string | null;
  actual_start: string | null;
  actual_end: string | null;
  report_uploaded: boolean;
  checklist_uploaded: boolean;
  findings_total: number;
  findings_open: number;
  cars_total: number;
  cars_open: number;
  evidence_files_total: number;
}

export interface QMSAuditWorkspaceReadinessOut {
  planning_complete: boolean;
  fieldwork_ready: boolean;
  closure_ready: boolean;
  report_ready: boolean;
  public_response_window_open: boolean;
}

export interface QMSAuditWorkspaceActionOut {
  code: string;
  label: string;
  enabled: boolean;
  variant: string;
  count: number | null;
}

export interface QMSAuditNoticeStateOut {
  upcoming_notice_sent_at: string | null;
  day_of_notice_sent_at: string | null;
}

export interface QMSAuditWorkspaceOut {
  audit: QMSAuditOut;
  summary: QMSAuditWorkspaceSummaryOut;
  readiness: QMSAuditWorkspaceReadinessOut;
  actions: QMSAuditWorkspaceActionOut[];
  participants: QMSAuditParticipantOut[];
  notice_state: QMSAuditNoticeStateOut;
}

export interface QMSAuditWorkflowCheckItemOut {
  code: string;
  label: string;
  passed: boolean;
  detail: string;
}

export interface QMSAuditWorkflowCheckOut {
  audit_id: string;
  audit_status: string;
  checks: QMSAuditWorkflowCheckItemOut[];
  passed: boolean;
}

export interface QMSAuditWorkflowStageOut {
  id: string;
  label: string;
  complete: boolean;
  active: boolean;
  helper?: string | null;
  metric?: string | null;
}

export interface QMSAuditWorkflowSummaryOut {
  audit_id: string;
  current_stage_id: string;
  current_stage_label: string;
  percent_complete: number;
  findings_total: number;
  findings_open: number;
  cars_total: number;
  cars_open: number;
  checklist_uploaded: boolean;
  report_uploaded: boolean;
  acknowledged_by_name?: string | null;
  acknowledged_by_email?: string | null;
  created_at?: string | null;
  stages: QMSAuditWorkflowStageOut[];
}

export interface QMSAuditWorkflowOut {
  audit: QMSAuditOut;
  workflow: QMSAuditWorkflowSummaryOut;
}

export type QmsServiceOptions = { silent?: boolean };


export interface QMSAuditNoticeDispatchOut {
  audit_id: string;
  stage: string;
  notified_user_ids: string[];
  sent_at: string;
}

export interface QMSFindingOut {
  id: string;
  audit_id: string;
  finding_ref?: string | null;
  finding_type: string;
  severity: string;
  level: string;
  requirement_ref?: string | null;
  description: string;
  objective_evidence?: string | null;
  safety_sensitive: boolean;
  target_close_date?: string | null;
  closed_at?: string | null;
  verified_at?: string | null;
  verified_by_user_id?: string | null;
  acknowledged_at?: string | null;
  acknowledged_by_user_id?: string | null;
  acknowledged_by_name?: string | null;
  acknowledged_by_email?: string | null;
  created_by_user_id?: string | null;
  created_at: string;
}

export interface QMSFindingAttachmentOut {
  id: string;
  finding_id: string;
  filename: string;
  content_type?: string | null;
  size_bytes?: number | null;
  sha256?: string | null;
  uploaded_by_user_id?: string | null;
  uploaded_at: string;
  download_url: string;
}

export interface QualityChecklistItemOut {
  id: string;
  amo_id: string;
  audit_id: string;
  section?: string | null;
  checklist_ref?: string | null;
  requirement_ref?: string | null;
  prompt: string;
  response_status: string;
  objective_evidence?: string | null;
  finding_id?: string | null;
  assigned_to_user_id?: string | null;
  completed_by_user_id?: string | null;
  completed_at?: string | null;
  sort_order: number;
  created_by_user_id?: string | null;
  created_at: string;
  updated_at: string;
}

export type QualityChecklistItemPayload = {
  section?: string | null;
  checklist_ref?: string | null;
  requirement_ref?: string | null;
  prompt?: string | null;
  response_status?: string | null;
  objective_evidence?: string | null;
  finding_id?: string | null;
  assigned_to_user_id?: string | null;
  sort_order?: number;
};

export type QMSFindingCreatePayload = {
  finding_ref?: string | null;
  finding_type: string;
  severity: string;
  level?: string | null;
  requirement_ref?: string | null;
  description: string;
  objective_evidence?: string | null;
  safety_sensitive?: boolean;
  target_close_date?: string | null;
};

export type QMSFindingUpdatePayload = Partial<QMSFindingCreatePayload>;

export interface QMSAuditRegisterRowOut {
  audit: QMSAuditOut;
  finding: QMSFindingOut;
  linked_cars: CAROut[];
}

export interface QMSAuditRegisterResponse {
  rows: QMSAuditRegisterRowOut[];
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
  root_cause_text?: string | null;
  root_cause_status?: string;
  root_cause_review_note?: string | null;
  capa_text?: string | null;
  capa_status?: string;
  capa_review_note?: string | null;
  evidence_required?: boolean;
  evidence_received_at?: string | null;
  evidence_verified_at?: string | null;
  can_current_user_modify?: boolean | null;
  can_current_user_review?: boolean | null;
  is_escalated_locked?: boolean | null;
  audit_id?: string | null;
  audit_ref?: string | null;
  audit_title?: string | null;
  finding_ref?: string | null;
  finding_description?: string | null;
  date_issued?: string | null;
  date_closed?: string | null;
  days_out?: number | null;
  days_remaining_past?: number | null;
  auditor_remarks?: string | null;
  register_root_cause?: string | null;
  register_cap?: string | null;
  register_pap?: string | null;
  auditor_name?: string | null;
  requested_by_name?: string | null;
  responsible_department?: string | null;
  responsible_personnel?: string | null;
  car_category_limit?: string | null;
  car_sequence_no?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CARRegisterResponse {
  items: CAROut[];
  total: number;
  limit: number;
  offset: number;
}

type QueryVal = string | number | boolean | null | undefined;

const API_BASE = getApiBaseUrl();
const NOTIFICATION_SUMMARY_CACHE_KEY = "amo:qms-notification-summary:data";
const NOTIFICATION_SUMMARY_ETAG_KEY = "amo:qms-notification-summary:etag";

function readStoredNotificationSummary(): QMSNotificationSummaryOut | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(NOTIFICATION_SUMMARY_CACHE_KEY);
    return raw ? (JSON.parse(raw) as QMSNotificationSummaryOut) : null;
  } catch {
    return null;
  }
}

function writeStoredNotificationSummary(summary: QMSNotificationSummaryOut, etag?: string | null): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(NOTIFICATION_SUMMARY_CACHE_KEY, JSON.stringify(summary));
    if (etag) {
      window.localStorage.setItem(NOTIFICATION_SUMMARY_ETAG_KEY, etag);
    }
  } catch {
    // ignore storage failures
  }
}

function readStoredNotificationSummaryEtag(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(NOTIFICATION_SUMMARY_ETAG_KEY);
}


function toQuery(params: Record<string, QueryVal>): string {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === null || v === undefined) return;
    qs.set(k, String(v));
  });
  const s = qs.toString();
  return s ? `?${s}` : "";
}

function downloadEvidencePack(path: string): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("GET", `${API_BASE}${path}`);
    const token = getToken();
    if (token) {
      xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    }
    xhr.responseType = "blob";

    xhr.addEventListener("load", () => {
      if (xhr.status === 401) {
        handleAuthFailure("expired");
        reject(new Error("Session expired. Please sign in again."));
        return;
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        const message = xhr.responseText || `Request failed (${xhr.status})`;
        reject(new Error(message));
        return;
      }
      resolve(xhr.response as Blob);
    });

    xhr.addEventListener("error", () => {
      reject(new Error("Network error while downloading evidence pack."));
    });

    xhr.timeout = 45000;
    xhr.addEventListener("timeout", () => { reject(new Error("Timed out while downloading evidence pack.")); });
    xhr.send();
  });
}

async function downloadBinary(path: string): Promise<Blob> {
  const token = getToken();
  beginBackgroundLoading();
  try {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort("timeout"), 30000);
  const res = await fetch(`${API_BASE}${path}`, {
    method: "GET",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    credentials: "include",
    signal: controller.signal,
  });
  window.clearTimeout(timeout);

  if (res.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`QMS API ${res.status}: ${text || res.statusText}`);
  }
  return res.blob();
  } finally {
    endBackgroundLoading();
  }
}


async function publicFetchJson<T>(path: string): Promise<T> {
  beginBackgroundLoading();
  try {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort("timeout"), 20000);
    const res = await fetch(`${getApiBaseUrl()}${path}`, {
      method: "GET",
      headers: { Accept: "application/json" },
      credentials: "omit",
      signal: controller.signal,
    });
    window.clearTimeout(timeout);
    if (res.status === 401 || res.status === 403) {
      throw new Error("This invite is not available. Check that the link is correct and still active.");
    }
    if (res.status === 503) {
      const text = await res.text().catch(() => "");
      throw new Error(text || "Service unavailable. Please retry or contact support.");
    }
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`QMS API ${res.status}: ${text || res.statusText}`);
    }
    return (await res.json()) as T;
  } finally {
    endBackgroundLoading();
  }
}

async function publicSendJson<T>(
  path: string,
  method: "POST" | "PATCH" | "DELETE",
  body: unknown
): Promise<T> {
  beginLoading();
  try {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort("timeout"), 45000);
    const res = await fetch(`${getApiBaseUrl()}${path}`, {
      method,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body ?? {}),
      credentials: "omit",
      signal: controller.signal,
    });
    window.clearTimeout(timeout);
    if (res.status === 401 || res.status === 403) {
      throw new Error("This invite is not available. Check that the link is correct and still active.");
    }
    if (res.status === 503) {
      const text = await res.text().catch(() => "");
      throw new Error(text || "Service unavailable. Please retry or contact support.");
    }
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`QMS API ${res.status}: ${text || res.statusText}`);
    }
    if (res.status === 204) {
      return undefined as T;
    }
    return (await res.json()) as T;
  } finally {
    endLoading();
  }
}

async function fetchJson<T>(path: string): Promise<T> {
  const token = getToken();
  beginBackgroundLoading();
  try {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort("timeout"), 20000);
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "GET",
    headers: {
      Accept: "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    credentials: "include",
    signal: controller.signal,
  });
  window.clearTimeout(timeout);

  if (res.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }

  if (res.status === 503) {
    const text = await res.text().catch(() => "");
    throw new Error(text || "Service unavailable. Please retry or contact support.");
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`QMS API ${res.status}: ${text || res.statusText}`);
  }
  return (await res.json()) as T;
  } finally {
    endBackgroundLoading();
  }
}

async function sendJson<T>(
  path: string,
  method: "POST" | "PATCH" | "DELETE",
  body: unknown
): Promise<T> {
  const token = getToken();
  beginLoading();
  try {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort("timeout"), 45000);
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body ?? {}),
    credentials: "include",
    signal: controller.signal,
  });
  window.clearTimeout(timeout);

  if (res.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }

  if (res.status === 503) {
    const text = await res.text().catch(() => "");
    throw new Error(text || "Service unavailable. Please retry or contact support.");
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`QMS API ${res.status}: ${text || res.statusText}`);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
  } finally {
    endLoading();
  }
}


export interface QMSDashboardOut {
  domain: string | null;
  documents_total: number;
  documents_active: number;
  documents_draft: number;
  documents_obsolete: number;
  distributions_pending_ack: number;
  change_requests_total: number;
  change_requests_open: number;
  audits_total: number;
  audits_open: number;
  findings_open_total: number;
  findings_open_level_1: number;
  findings_open_level_2: number;
  findings_open_level_3: number;
  findings_open_level_4?: number;
  findings_overdue_total: number;
}

export async function qmsGetDashboard(params?: {
  domain?: string;
}): Promise<QMSDashboardOut> {
  return fetchJson<QMSDashboardOut>(`/quality/qms/dashboard${toQuery(params ?? {})}`);
}



export type QMSAvailabilityStatus = "ON_DUTY" | "AWAY" | "ON_LEAVE";

export interface QMSManpowerAvailabilityItem {
  id: string;
  user_id: string;
  status: QMSAvailabilityStatus;
  effective_from: string;
  effective_to: string | null;
  note: string | null;
  updated_by_user_id: string | null;
  updated_at: string;
}

export interface QMSManpowerOut {
  scope: "tenant" | "department";
  total_employees: number;
  by_role: Record<string, number>;
  availability: { on_duty: number; away: number; on_leave: number } | null;
  by_department: Array<{ department: string; count: number }> | null;
  updated_at: string;
}

export interface QMSCockpitActionItemOut {
  id: string;
  kind: string;
  audit_scope_id?: string | null;
  audit_scope_code?: string | null;
  title: string;
  status: string;
  priority: string;
  due_date: string | null;
  assignee_user_id: string | null;
}

export interface QMSCockpitSnapshotOut {
  generated_at: string;
  pending_acknowledgements: number;
  audits_open: number;
  audits_total: number;
  findings_overdue: number;
  findings_open_total: number;
  documents_active: number;
  documents_draft: number;
  documents_obsolete: number;
  change_requests_open: number;
  cars_open_total: number;
  cars_overdue: number;
  training_records_expiring_30d: number;
  training_records_expired: number;
  training_records_unverified: number;
  training_deferrals_pending: number;
  next_due_audit?: {
    id?: string;
    audit_ref?: string;
    title?: string;
    planned_start?: string | null;
    planned_end?: string | null;
  } | null;
  suppliers_active: number;
  suppliers_inactive: number;
  tasks_due_today?: number;
  tasks_overdue?: number;
  change_control_pending_approvals?: number;
  events_hold_count?: number;
  events_new_count?: number;
  compliance_exceptions_open?: number;
  compliance_overdue?: number;
  compliance_unplanned_applicable?: number;
  manpower?: QMSManpowerOut | null;
  audit_closure_trend: {
    period_start: string;
    period_end: string;
    closed_count: number;
    audit_ids: string[];
  }[];
  most_common_finding_trend_12m: {
    period_start: string;
    finding_type: string;
    count: number;
  }[];
  action_queue: QMSCockpitActionItemOut[];
}

export async function qmsGetCockpitSnapshot(params?: {
  domain?: string;
}): Promise<QMSCockpitSnapshotOut> {
  return fetchJson<QMSCockpitSnapshotOut>(`/quality/qms/cockpit-snapshot${toQuery(params ?? {})}`);
}

export async function qmsListManpowerAvailability(params?: { department?: string }): Promise<QMSManpowerAvailabilityItem[]> {
  return fetchJson<QMSManpowerAvailabilityItem[]>(`/quality/qms/manpower/availability${toQuery(params ?? {})}`);
}

export async function qmsSetManpowerAvailability(payload: {
  user_id: string;
  status: QMSAvailabilityStatus;
  effective_from?: string | null;
  effective_to?: string | null;
  note?: string | null;
}): Promise<QMSManpowerAvailabilityItem> {
  return sendJson<QMSManpowerAvailabilityItem>("/quality/qms/manpower/availability", "POST", payload);
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

export async function qmsCreateDistribution(payload: {
  doc_id: string;
  recipient_user_id: string;
  requires_ack?: boolean;
}): Promise<QMSDistributionOut> {
  return sendJson<QMSDistributionOut>("/quality/qms/distributions", "POST", {
    ...payload,
    requires_ack: payload.requires_ack ?? true,
  });
}

export async function qmsListChangeRequests(params?: {
  domain?: string;
  status_?: QMSChangeRequestStatus;
}): Promise<QMSChangeRequestOut[]> {
  return fetchJson<QMSChangeRequestOut[]>(
    `/quality/qms${"/change-requests"}${toQuery(params ?? {})}`
  );
}

export async function qmsListAuditScopes(params?: { active?: boolean }): Promise<QMSAuditScopeOut[]> {
  return fetchJson<QMSAuditScopeOut[]>(`/quality/audits/scopes${toQuery(params ?? {})}`);
}

export async function qmsCreateAuditScope(payload: Partial<QMSAuditScopeOut> & { code: string; name: string }): Promise<QMSAuditScopeOut> {
  return sendJson<QMSAuditScopeOut>("/quality/audits/scopes", "POST", payload);
}

export async function qmsUpdateAuditScope(scopeId: string, payload: Partial<QMSAuditScopeOut>): Promise<QMSAuditScopeOut> {
  return sendJson<QMSAuditScopeOut>(`/quality/audits/scopes/${encodeURIComponent(scopeId)}`, "PATCH", payload);
}

export async function qmsListAudits(params?: {
  domain?: string;
  status_?: QMSAuditStatus;
  kind?: string;
  deleted_only?: boolean;
  include_deleted?: boolean;
  limit?: number;
}, _options?: QmsServiceOptions): Promise<QMSAuditOut[]> {
  return fetchJson<QMSAuditOut[]>(`/quality/audits${toQuery(params ?? {})}`);
}

export async function qmsListAuditSchedules(params?: {
  domain?: string;
  active?: boolean;
  deleted_only?: boolean;
  include_deleted?: boolean;
  limit?: number;
}, _options?: QmsServiceOptions): Promise<QMSAuditScheduleOut[]> {
  return fetchJson<QMSAuditScheduleOut[]>(
    `/quality/audits/schedules${toQuery(params ?? {})}`
  );
}

export async function qmsCreateAuditSchedule(payload: {
  domain: string;
  kind: string;
  audit_scope_id?: string | null;
  audit_scope_code?: string | null;
  frequency: QMSAuditScheduleFrequency;
  title: string;
  scope?: string | null;
  criteria?: string | null;
  auditee?: string | null;
  auditee_email?: string | null;
  auditee_user_id?: string | null;
  external_auditees?: QMSExternalAuditeeContact[] | null;
  lead_auditor_user_id?: string | null;
  observer_auditor_user_id?: string | null;
  assistant_auditor_user_id?: string | null;
  notify_auditors?: boolean;
  notify_auditees?: boolean;
  reminder_interval_days?: number;
  duration_days: number;
  next_due_date: string;
}): Promise<QMSAuditScheduleOut> {
  return sendJson<QMSAuditScheduleOut>(
    "/quality/audits/schedules",
    "POST",
    payload
  );
}

export async function qmsUpdateAuditSchedule(
  scheduleId: string,
  payload: {
    kind?: string | null;
    audit_scope_id?: string | null;
    audit_scope_code?: string | null;
    frequency?: QMSAuditScheduleFrequency | null;
    title?: string | null;
    scope?: string | null;
    criteria?: string | null;
    auditee?: string | null;
    auditee_email?: string | null;
    auditee_user_id?: string | null;
    lead_auditor_user_id?: string | null;
    observer_auditor_user_id?: string | null;
    assistant_auditor_user_id?: string | null;
    duration_days?: number | null;
    next_due_date?: string | null;
    is_active?: boolean | null;
  }
): Promise<QMSAuditScheduleOut> {
  return sendJson<QMSAuditScheduleOut>(`/quality/audits/schedules/${encodeURIComponent(scheduleId)}`, "PATCH", payload);
}

export interface QMSPersonOption {
  id: string;
  full_name: string;
  email: string | null;
  role: string | null;
  department_id: string | null;
  position_title: string | null;
  staff_code?: string | null;
  avatar_url?: string | null;
}

export interface QMSAuditeeBrandOut {
  query: string;
  company_name: string | null;
  domain: string | null;
  website_url?: string | null;
  logo_url: string | null;
  logo_urls?: string[];
  source: string;
  resolved: boolean;
}

export async function qmsListAuditPersonnelOptions(params?: {
  search?: string;
  limit?: number;
}): Promise<QMSPersonOption[]> {
  const suffix = toQuery({ search: params?.search, limit: params?.limit ?? 50 });
  return fetchJson<QMSPersonOption[]>(`/quality/audits/personnel/options${suffix}`);
}

function extractDomainFromEmail(value?: string | null): string | null {
  const match = (value || "").trim().match(/@([A-Za-z0-9.-]+\.[A-Za-z]{2,})/);
  return match ? match[1].toLowerCase().replace(/^www\./, "") : null;
}

function safeHostname(value?: string | null): string | null {
  if (!value) return null;
  let raw = value.trim();
  if (!raw) return null;
  if (raw.includes("@")) return extractDomainFromEmail(raw);
  if (!/^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(raw)) raw = `https://${raw}`;
  try {
    const host = new URL(raw).hostname.toLowerCase().replace(/^www\./, "");
    return /^[a-z0-9.-]+\.[a-z]{2,}$/.test(host) ? host : null;
  } catch {
    return null;
  }
}

function humanizeDomain(domain: string | null): string | null {
  if (!domain) return null;
  const parts = domain.replace(/^www\./, "").split(".").filter(Boolean);
  if (!parts.length) return null;
  const label = parts.length > 2 ? parts[parts.length - 2] : parts[0];
  return label
    .replace(/[-_]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function cleanCompanyName(value?: string | null): string | null {
  const raw = (value || "").trim();
  if (!raw || raw.includes("@") || safeHostname(raw)) return null;
  return raw;
}

function uniqueStrings(values: Array<string | null | undefined>): string[] {
  const seen = new Set<string>();
  return values.filter((value): value is string => {
    if (!value) return false;
    const clean = value.trim();
    if (!clean || seen.has(clean)) return false;
    seen.add(clean);
    return true;
  });
}

function logoCandidatesForDomain(domain: string | null, extraLogo?: string | null): string[] {
  if (!domain) return uniqueStrings([extraLogo]);
  const encoded = encodeURIComponent(domain);
  return uniqueStrings([
    extraLogo,
    `https://logo.clearbit.com/${encoded}?size=256`,
    `https://www.google.com/s2/favicons?sz=256&domain_url=${encoded}`,
    `https://${domain}/favicon.ico`,
    `https://www.${domain}/favicon.ico`,
  ]);
}

async function commonsImageUrl(fileName: string | null | undefined): Promise<string | null> {
  const name = (fileName || "").trim();
  if (!name) return null;
  try {
    const title = name.startsWith("File:") ? name : `File:${name}`;
    const url = `https://commons.wikimedia.org/w/api.php?action=query&titles=${encodeURIComponent(title)}&prop=imageinfo&iiprop=url&format=json&origin=*`;
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    if (!response.ok) return null;
    const payload = await response.json() as any;
    const pages = payload?.query?.pages || {};
    for (const page of Object.values(pages) as any[]) {
      const imageUrl = page?.imageinfo?.[0]?.url;
      if (typeof imageUrl === "string" && imageUrl) return imageUrl;
    }
  } catch {
    return null;
  }
  return null;
}

async function resolveCompanyFromClearbit(name: string): Promise<{ companyName: string | null; domain: string | null; logoUrl: string | null }> {
  const query = name.trim();
  if (!query || query.length < 2) return { companyName: null, domain: null, logoUrl: null };
  try {
    const url = `https://autocomplete.clearbit.com/v1/companies/suggest?query=${encodeURIComponent(query)}`;
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    if (!response.ok) return { companyName: null, domain: null, logoUrl: null };
    const payload = await response.json() as Array<{ name?: string; domain?: string; logo?: string }>;
    const first = Array.isArray(payload) ? payload.find((item) => safeHostname(item.domain)) : null;
    if (!first) return { companyName: null, domain: null, logoUrl: null };
    return { companyName: first.name || query, domain: safeHostname(first.domain), logoUrl: first.logo || null };
  } catch {
    return { companyName: null, domain: null, logoUrl: null };
  }
}

async function resolveCompanyDomainFromWikidata(name: string): Promise<{ companyName: string | null; domain: string | null; logoUrl: string | null }> {
  const query = name.trim();
  if (!query || query.length < 2) return { companyName: null, domain: null, logoUrl: null };
  try {
    const searchUrl = `https://www.wikidata.org/w/api.php?action=wbsearchentities&search=${encodeURIComponent(query)}&language=en&format=json&limit=4&origin=*`;
    const searchResponse = await fetch(searchUrl, { headers: { Accept: "application/json" } });
    if (!searchResponse.ok) return { companyName: null, domain: null, logoUrl: null };
    const searchPayload = await searchResponse.json() as { search?: Array<{ id?: string; label?: string }> };
    for (const result of searchPayload.search || []) {
      if (!result.id) continue;
      const entityUrl = `https://www.wikidata.org/wiki/Special:EntityData/${encodeURIComponent(result.id)}.json`;
      const entityResponse = await fetch(entityUrl, { headers: { Accept: "application/json" } });
      if (!entityResponse.ok) continue;
      const entityPayload = await entityResponse.json() as any;
      const claims = entityPayload?.entities?.[result.id]?.claims || {};
      let domain: string | null = null;
      for (const claim of claims.P856 || []) {
        domain = safeHostname(claim?.mainsnak?.datavalue?.value);
        if (domain) break;
      }
      let logoUrl: string | null = null;
      const logoClaim = (claims.P154 || claims.P18 || [])[0]?.mainsnak?.datavalue?.value;
      if (logoClaim) logoUrl = await commonsImageUrl(String(logoClaim));
      if (domain || logoUrl) return { companyName: result.label || query, domain, logoUrl };
    }
  } catch {
    return { companyName: null, domain: null, logoUrl: null };
  }
  return { companyName: null, domain: null, logoUrl: null };
}

export async function qmsResolveAuditeeBrand(params: {
  name?: string | null;
  email?: string | null;
}): Promise<QMSAuditeeBrandOut> {
  const rawName = (params.name || "").trim();
  const rawEmail = (params.email || "").trim();
  const query = (rawName || rawEmail).trim();
  const directDomain = extractDomainFromEmail(rawEmail) || extractDomainFromEmail(rawName) || safeHostname(rawName);
  const cleanName = cleanCompanyName(rawName);

  if (directDomain) {
    const companyName = cleanName || humanizeDomain(directDomain);
    const logoUrls = logoCandidatesForDomain(directDomain);
    return {
      query: query || directDomain,
      company_name: companyName,
      domain: directDomain,
      website_url: `https://${directDomain}`,
      logo_url: logoUrls[0] || null,
      logo_urls: logoUrls,
      source: extractDomainFromEmail(rawEmail) || extractDomainFromEmail(rawName) ? "email-domain" : "domain",
      resolved: true,
    };
  }

  const clearbit = cleanName ? await resolveCompanyFromClearbit(cleanName) : { companyName: null, domain: null, logoUrl: null };
  if (clearbit.domain || clearbit.logoUrl) {
    const logoUrls = logoCandidatesForDomain(clearbit.domain, clearbit.logoUrl);
    return {
      query,
      company_name: clearbit.companyName || cleanName || humanizeDomain(clearbit.domain),
      domain: clearbit.domain,
      website_url: clearbit.domain ? `https://${clearbit.domain}` : null,
      logo_url: logoUrls[0] || null,
      logo_urls: logoUrls,
      source: "company-search",
      resolved: true,
    };
  }

  const resolved = cleanName ? await resolveCompanyDomainFromWikidata(cleanName) : { companyName: null, domain: null, logoUrl: null };
  if (resolved.domain || resolved.logoUrl) {
    const logoUrls = logoCandidatesForDomain(resolved.domain, resolved.logoUrl);
    return {
      query,
      company_name: resolved.companyName || cleanName || humanizeDomain(resolved.domain),
      domain: resolved.domain,
      website_url: resolved.domain ? `https://${resolved.domain}` : null,
      logo_url: logoUrls[0] || null,
      logo_urls: logoUrls,
      source: "wikidata",
      resolved: true,
    };
  }

  return {
    query,
    company_name: cleanName || null,
    domain: null,
    website_url: null,
    logo_url: null,
    logo_urls: [],
    source: "fallback",
    resolved: false,
  };
}

export type QMSAuditUpdatePayload = {
  status?: QMSAuditStatus | null;
  title?: string | null;
  kind?: string | null;
  audit_scope_id?: string | null;
  audit_scope_code?: string | null;
  scope?: string | null;
  criteria?: string | null;
  auditee?: string | null;
  auditee_email?: string | null;
  auditee_user_id?: string | null;
  external_auditees?: QMSExternalAuditeeContact[] | null;
  lead_auditor_user_id?: string | null;
  observer_auditor_user_id?: string | null;
  assistant_auditor_user_id?: string | null;
  planned_start?: string | null;
  planned_end?: string | null;
  actual_start?: string | null;
  actual_end?: string | null;
  report_file_ref?: string | null;
  checklist_file_ref?: string | null;
  notify_auditors?: boolean | null;
  notify_auditees?: boolean | null;
  reminder_interval_days?: number | null;
};

export async function qmsUpdateAudit(
  auditId: string,
  payload: QMSAuditUpdatePayload
): Promise<QMSAuditOut> {
  return sendJson<QMSAuditOut>(`/quality/audits/${encodeURIComponent(auditId)}`, "PATCH", payload);
}


export async function qmsDeleteAudit(auditId: string): Promise<void> {
  await sendJson<void>(`/quality/audits/${encodeURIComponent(auditId)}`, "DELETE", undefined);
}

export async function qmsRestoreAudit(auditId: string): Promise<QMSAuditOut> {
  return sendJson<QMSAuditOut>(`/quality/audits/${encodeURIComponent(auditId)}/restore`, "POST", {});
}

export async function qmsPurgeAudit(auditId: string): Promise<void> {
  await sendJson<void>(`/quality/audits/${encodeURIComponent(auditId)}/purge`, "DELETE", undefined);
}

export async function qmsStartAudit(auditId: string): Promise<QMSAuditOut> {
  return qmsUpdateAudit(auditId, { status: "IN_PROGRESS" });
}

export async function qmsCloseAudit(auditId: string): Promise<QMSAuditOut> {
  return qmsUpdateAudit(auditId, { status: "CLOSED" });
}

export async function qmsDeleteAuditSchedule(scheduleId: string): Promise<void> {
  await sendJson<void>(`/quality/audits/schedules/${scheduleId}`, "DELETE", undefined);
}

export async function qmsRestoreAuditSchedule(scheduleId: string): Promise<QMSAuditScheduleOut> {
  return sendJson<QMSAuditScheduleOut>(`/quality/audits/schedules/${encodeURIComponent(scheduleId)}/restore`, "POST", {});
}

export async function qmsPurgeAuditSchedule(scheduleId: string): Promise<void> {
  await sendJson<void>(`/quality/audits/schedules/${encodeURIComponent(scheduleId)}/purge`, "DELETE", undefined);
}

export async function qmsRunAuditSchedule(
  scheduleId: string
): Promise<QMSAuditOut> {
  return sendJson<QMSAuditOut>(
    `/quality/audits/schedules/${scheduleId}/run`,
    "POST",
    {}
  );
}

export async function qmsRunAuditReminders(upcomingDays: number): Promise<{
  day_of_sent: number;
  upcoming_sent: number;
}> {
  return sendJson<{ day_of_sent: number; upcoming_sent: number }>(
    `/quality/audits/reminders/run?upcoming_days=${upcomingDays}`,
    "POST",
    {}
  );
}

export async function qmsResolveAudit(auditKey: string, _options?: QmsServiceOptions): Promise<QMSAuditOut | null> {
  const key = auditKey.trim();
  if (!key) return null;
  const audits = await fetchJson<QMSAuditOut[]>(`/quality/audits`);
  const normalized = key.toLowerCase();
  return audits.find((audit) =>
    String(audit.id).toLowerCase() === normalized ||
    String(audit.audit_ref || "").toLowerCase() === normalized ||
    String(audit.audit_ref || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") === normalized
  ) ?? null;
}

export async function qmsGetAuditWorkflow(auditId: string, _options?: QmsServiceOptions): Promise<QMSAuditWorkflowOut> {
  return fetchJson<QMSAuditWorkflowOut>(`/quality/audits/${encodeURIComponent(auditId)}/workflow-check`);
}

export async function qmsGetAuditWorkspace(auditId: string): Promise<QMSAuditWorkspaceOut> {
  return fetchJson<QMSAuditWorkspaceOut>(`/quality/audits/${encodeURIComponent(auditId)}/workspace`);
}

export async function qmsGetAuditWorkflowCheck(auditId: string): Promise<QMSAuditWorkflowCheckOut> {
  return fetchJson<QMSAuditWorkflowCheckOut>(`/quality/audits/${encodeURIComponent(auditId)}/workflow-check`);
}

export async function qmsIssueAuditNotice(
  auditId: string,
  payload?: { stage?: "manual" | "upcoming" | "day_of" }
): Promise<QMSAuditNoticeDispatchOut> {
  return sendJson<QMSAuditNoticeDispatchOut>(
    `/quality/audits/${encodeURIComponent(auditId)}/issue-notice`,
    "POST",
    payload ?? {}
  );
}

export async function qmsUploadAuditChecklist(
  auditId: string,
  file: File
): Promise<QMSAuditOut> {
  const formData = new FormData();
  formData.append("file", file);
  const token = getToken();
  const res = await fetch(`${API_BASE}/quality/audits/${auditId}/checklist`, {
    method: "POST",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: formData,
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
  return (await res.json()) as QMSAuditOut;
}

export async function qmsDownloadAuditChecklist(auditId: string): Promise<Blob> {
  return downloadBinary(`/quality/audits/${auditId}/checklist`);
}

export async function qmsUploadAuditReport(
  auditId: string,
  file: File
): Promise<QMSAuditOut> {
  const formData = new FormData();
  formData.append("file", file);
  const token = getToken();
  const res = await fetch(`${API_BASE}/quality/audits/${auditId}/report`, {
    method: "POST",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: formData,
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
  return (await res.json()) as QMSAuditOut;
}

export async function qmsDownloadAuditReport(auditId: string): Promise<Blob> {
  return downloadBinary(`/quality/audits/${auditId}/report`);
}

export interface QMSAuditReportSharePayload {
  recipient_groups: string[];
  message?: string | null;
}

export interface QMSAuditReportShareOut {
  audit_id: string;
  recipient_groups: string[];
  recipient_user_ids: string[];
  shared: number;
}

export async function qmsShareAuditReport(
  auditId: string,
  payload: QMSAuditReportSharePayload
): Promise<QMSAuditReportShareOut> {
  return sendJson<QMSAuditReportShareOut>(
    `/quality/audits/${encodeURIComponent(auditId)}/report/share`,
    "POST",
    {
      recipient_groups: payload.recipient_groups,
      message: payload.message ?? null,
    }
  );
}

export async function qmsListFindings(auditId: string): Promise<QMSFindingOut[]> {
  return fetchJson<QMSFindingOut[]>(`/quality/audits/${auditId}/findings`);
}

export async function qmsCreateFinding(
  auditId: string,
  payload: QMSFindingCreatePayload
): Promise<QMSFindingOut> {
  return sendJson<QMSFindingOut>(`/quality/audits/${auditId}/findings`, "POST", payload);
}

function findingRoute(findingId: string, auditId?: string | null, suffix = ""): string {
  const encodedFindingId = encodeURIComponent(findingId);
  if (auditId) {
    return `/quality/audits/${encodeURIComponent(auditId)}/findings/${encodedFindingId}${suffix}`;
  }
  return `/quality/findings/${encodedFindingId}${suffix}`;
}

export async function qmsUpdateFinding(
  findingId: string,
  payload: QMSFindingUpdatePayload,
  auditId?: string | null
): Promise<QMSFindingOut> {
  return sendJson<QMSFindingOut>(findingRoute(findingId, auditId), "PATCH", payload);
}

export async function qmsDeleteFinding(findingId: string, auditId?: string | null): Promise<void> {
  await sendJson<void>(findingRoute(findingId, auditId), "DELETE", undefined);
}

export async function qmsFlagFindingForReview(findingId: string, reason: string, auditId?: string | null): Promise<QMSFindingOut> {
  return sendJson<QMSFindingOut>(findingRoute(findingId, auditId, "/review-flag"), "POST", { reason });
}

export async function qmsListAuditFindingAttachments(auditId: string): Promise<QMSFindingAttachmentOut[]> {
  try {
    return await fetchJson<QMSFindingAttachmentOut[]>(`/quality/audits/${auditId}/finding-attachments`);
  } catch (error) {
    if (error instanceof Error && error.message.includes("QMS API 404")) {
      return [];
    }
    throw error;
  }
}

export async function qmsListFindingAttachments(findingId: string): Promise<QMSFindingAttachmentOut[]> {
  return fetchJson<QMSFindingAttachmentOut[]>(`/quality/findings/${encodeURIComponent(findingId)}/attachments`);
}

export async function qmsUploadFindingAttachment(findingId: string, file: File): Promise<QMSFindingAttachmentOut> {
  const formData = new FormData();
  formData.append("file", file);
  const authToken = getToken();
  const res = await fetch(`${getApiBaseUrl()}/quality/findings/${encodeURIComponent(findingId)}/attachments`, {
    method: "POST",
    headers: {
      ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    },
    body: formData,
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
  return (await res.json()) as QMSFindingAttachmentOut;
}

export async function qmsDeleteFindingAttachment(findingId: string, attachmentId: string): Promise<void> {
  await sendJson<void>(`/quality/findings/${encodeURIComponent(findingId)}/attachments/${encodeURIComponent(attachmentId)}`, "DELETE", undefined);
}

export async function qmsListAuditChecklistItems(auditId: string): Promise<QualityChecklistItemOut[]> {
  return fetchJson<QualityChecklistItemOut[]>(`/quality/audits/${auditId}/checklist-items`);
}

export async function qmsCreateAuditChecklistItem(
  auditId: string,
  payload: QualityChecklistItemPayload
): Promise<QualityChecklistItemOut> {
  return sendJson<QualityChecklistItemOut>(`/quality/audits/${auditId}/checklist-items`, "POST", payload);
}

export async function qmsUpdateAuditChecklistItem(
  auditId: string,
  itemId: string,
  payload: QualityChecklistItemPayload
): Promise<QualityChecklistItemOut> {
  return sendJson<QualityChecklistItemOut>(`/quality/audits/${auditId}/checklist-items/${itemId}`, "PATCH", payload);
}

export async function qmsListFindingsBulk(params?: {
  domain?: string;
  audit_ids?: string[];
  limit?: number;
}, _options?: QmsServiceOptions): Promise<QMSFindingOut[]> {
  const qs = new URLSearchParams();
  if (params?.domain) qs.set("domain", params.domain);
  (params?.audit_ids ?? []).forEach((auditId) => qs.append("audit_ids", auditId));
  if (params?.limit) qs.set("limit", String(params.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson<QMSFindingOut[]>(`/quality/audits/findings${suffix}`);
}

export async function qmsGetAuditRegister(params?: {
  domain?: string;
  audit_id?: string;
  limit?: number;
}, _options?: QmsServiceOptions): Promise<QMSAuditRegisterResponse> {
  return fetchJson<QMSAuditRegisterResponse>(`/quality/audits/register${toQuery(params ?? {})}`);
}

export async function qmsVerifyFinding(
  findingId: string,
  payload: { objective_evidence?: string | null }
): Promise<QMSFindingOut> {
  return sendJson<QMSFindingOut>(
    `/quality/findings/${findingId}/verify`,
    "POST",
    payload
  );
}

export async function qmsCloseFinding(findingId: string): Promise<QMSFindingOut> {
  return sendJson<QMSFindingOut>(`/quality/findings/${findingId}/close`, "POST", {});
}

export async function qmsAcknowledgeFinding(
  findingId: string,
  payload: { acknowledged_by_name?: string; acknowledged_by_email?: string }
): Promise<QMSFindingOut> {
  return sendJson<QMSFindingOut>(
    `/quality/findings/${findingId}/ack`,
    "POST",
    payload
  );
}

export async function qmsListCars(params?: {
  program?: CARProgram;
  status_?: CARStatus;
  assigned_to_user_id?: string;
  audit_id?: string;
  limit?: number;
}, _options?: QmsServiceOptions): Promise<CAROut[]> {
  return fetchJson<CAROut[]>(`/quality/cars${toQuery(params ?? {})}`);
}

export async function qmsListCarRegister(params?: {
  program?: CARProgram;
  status_?: CARStatus;
  assigned_to_user_id?: string;
  audit_id?: string;
  search?: string;
  limit?: number;
  offset?: number;
}, _options?: QmsServiceOptions): Promise<CARRegisterResponse> {
  return fetchJson<CARRegisterResponse>(`/quality/cars/register${toQuery(params ?? {})}`);
}

export type CARAssignee = {
  id: string;
  full_name: string;
  email?: string | null;
  staff_code?: string | null;
  role: string;
  department_id?: string | null;
  department_code?: string | null;
  department_name?: string | null;
};

export async function qmsListCarAssignees(params?: {
  department_id?: string;
  search?: string;
}): Promise<CARAssignee[]> {
  return fetchJson<CARAssignee[]>(
    `/quality/cars/assignees${toQuery(params ?? {})}`
  );
}

export async function qmsCreateCar(payload: {
  program: CARProgram;
  title: string;
  summary: string;
  priority?: CARPriority;
  due_date?: string | null;
  target_closure_date?: string | null;
  assigned_to_user_id?: string | null;
  finding_id: string;
  evidence_required?: boolean;
}): Promise<CAROut> {
  return sendJson<CAROut>("/quality/cars", "POST", payload);
}

export async function qmsUpdateCar(
  carId: string,
  payload: {
    title?: string;
    summary?: string;
    priority?: CARPriority;
    status?: CARStatus;
    due_date?: string | null;
    target_closure_date?: string | null;
    assigned_to_user_id?: string | null;
    reminder_interval_days?: number | null;
  }
): Promise<CAROut> {
  return sendJson<CAROut>(`/quality/cars/${carId}`, "PATCH", payload);
}

export async function qmsReviewCarResponse(
  carId: string,
  payload: {
    root_cause_status?: "ACCEPTED" | "REJECTED";
    root_cause_review_note?: string | null;
    capa_status?: "ACCEPTED" | "REJECTED" | "NEEDS_EVIDENCE";
    capa_review_note?: string | null;
    message?: string | null;
  }
): Promise<CAROut> {
  return sendJson<CAROut>(`/quality/cars/${encodeURIComponent(carId)}/review`, "POST", payload);
}

export async function qmsDeleteCar(carId: string): Promise<void> {
  await sendJson(`/quality/cars/${carId}`, "DELETE", {});
}

export interface QualityCARExtensionRequestOut {
  id: string;
  amo_id: string;
  car_id: string;
  requested_due_date: string;
  reason: string;
  status: string;
  requested_by_user_id?: string | null;
  reviewed_by_user_id?: string | null;
  reviewed_at?: string | null;
  review_note?: string | null;
  created_at: string;
  updated_at: string;
}

export async function qmsListCarExtensionRequests(carId: string): Promise<QualityCARExtensionRequestOut[]> {
  return fetchJson<QualityCARExtensionRequestOut[]>(`/quality/cars/${encodeURIComponent(carId)}/extension-requests`);
}

export async function qmsForwardCarExtensionRequest(carId: string, extensionId: string): Promise<QualityCARExtensionRequestOut> {
  return sendJson<QualityCARExtensionRequestOut>(`/quality/cars/${encodeURIComponent(carId)}/extension-requests/${encodeURIComponent(extensionId)}/forward-to-qm`, "POST", {});
}

export interface CARInviteOut {
  car_id: string;
  invite_token: string;
  invite_url: string;
  car_form_download_url?: string | null;
  next_reminder_at: string | null;
  car_number: string;
  title: string;
  summary: string;
  priority: CARPriority;
  status: CARStatus;
  due_date: string | null;
  target_closure_date: string | null;
  evidence_required?: boolean;
  evidence_received_at?: string | null;
  evidence_verified_at?: string | null;
  submitted_at?: string | null;
  containment_action?: string | null;
  root_cause?: string | null;
  corrective_action?: string | null;
  preventive_action?: string | null;
  evidence_ref?: string | null;
  submitted_by_name?: string | null;
  submitted_by_email?: string | null;
  root_cause_status?: string | null;
  capa_status?: string | null;
  root_cause_review_note?: string | null;
  capa_review_note?: string | null;
  finding_id?: string | null;
  finding_ref?: string | null;
  finding_description?: string | null;
  audit_id?: string | null;
  audit_ref?: string | null;
  audit_title?: string | null;
  auditee?: string | null;
  auditee_email?: string | null;
  submission_count?: number;
  remaining_submissions?: number;
  latest_submission_at?: string | null;
  review_opened_at?: string | null;
  can_edit?: boolean;
  can_submit?: boolean;
  can_recall?: boolean;
  locked_reason?: string | null;
  related_cars?: Array<{
    car_id: string;
    invite_token: string;
    car_number: string;
    title: string;
    finding_ref?: string | null;
    finding_description?: string | null;
    status: CARStatus;
    due_date?: string | null;
    priority: CARPriority;
  }>;
}

export interface CARResponseOut {
  id: string;
  car_id: string;
  containment_action?: string | null;
  root_cause?: string | null;
  corrective_action?: string | null;
  preventive_action?: string | null;
  evidence_ref?: string | null;
  submitted_by_name?: string | null;
  submitted_by_email?: string | null;
  submitted_at: string;
  status: string;
  is_latest?: boolean;
  review_opened_at?: string | null;
  recalled_at?: string | null;
}

export async function qmsGetCarInvite(carId: string): Promise<CARInviteOut> {
  return fetchJson(`/quality/cars/${carId}/invite`);
}

export async function qmsRescheduleCarReminder(carId: string, intervalDays: number): Promise<CAROut> {
  return sendJson<CAROut>(`/quality/cars/${carId}/reminders?reminder_interval_days=${intervalDays}`, "POST", {});
}

export async function qmsGetCarInviteByToken(token: string): Promise<CARInviteOut> {
  return publicFetchJson(`/quality/cars/invite/${encodeURIComponent(token)}`);
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
    root_cause_text?: string | null;
    capa_text?: string | null;
  }
): Promise<CAROut> {
  return publicSendJson<CAROut>(`/quality/cars/invite/${encodeURIComponent(token)}`, "PATCH", payload);
}

export async function qmsRecallCarInviteSubmission(token: string): Promise<CARInviteOut> {
  return publicSendJson<CARInviteOut>(`/quality/cars/invite/${encodeURIComponent(token)}/recall`, "POST", {});
}

export async function qmsListCarResponses(carId: string, markOpen = true): Promise<CARResponseOut[]> {
  return fetchJson<CARResponseOut[]>(`/quality/cars/${encodeURIComponent(carId)}/responses?mark_open=${markOpen ? "true" : "false"}`);
}

export interface CARAttachmentOut {
  id: string;
  car_id: string;
  filename: string;
  description?: string | null;
  content_type: string | null;
  size_bytes: number | null;
  sha256: string | null;
  uploaded_at: string;
  download_url: string;
}

export type CARActionType = "COMMENT" | "STATUS_CHANGE" | "REMINDER" | "ESCALATION" | "ASSIGNMENT" | string;

export interface CARActionOut {
  id: string;
  car_id: string;
  action_type: CARActionType;
  message: string;
  actor_user_id: string | null;
  actor_name?: string | null;
  actor_role?: string | null;
  delivery_status?: string | null;
  created_at: string;
}

export interface CARActionCreate {
  action_type?: CARActionType;
  message: string;
}

export async function qmsListCarActions(carId: string): Promise<CARActionOut[]> {
  return fetchJson<CARActionOut[]>(`/quality/cars/${encodeURIComponent(carId)}/actions`);
}

export async function qmsAddCarAction(carId: string, payload: CARActionCreate): Promise<CARActionOut> {
  return sendJson<CARActionOut>(`/quality/cars/${encodeURIComponent(carId)}/actions`, "POST", {
    action_type: payload.action_type ?? "COMMENT",
    message: payload.message,
  });
}

export async function qmsRequestCarAccess(carId: string, message?: string): Promise<CARActionOut> {
  const cleanMessage = (message || "I can support resolution of this CAR. Please review and assign write access if appropriate.").trim();
  return qmsAddCarAction(carId, {
    action_type: "ASSIGNMENT",
    message: cleanMessage || "CAR access requested.",
  });
}

export async function qmsListCarInviteActions(token: string): Promise<CARActionOut[]> {
  return publicFetchJson<CARActionOut[]>(`/quality/cars/invite/${encodeURIComponent(token)}/actions`);
}

export function qmsGetCarInviteFormUrl(token: string): string {
  return `${getApiBaseUrl()}/quality/cars/invite/${encodeURIComponent(token)}/form`;
}

export async function qmsListCarInviteAttachments(token: string): Promise<CARAttachmentOut[]> {
  return publicFetchJson<CARAttachmentOut[]>(`/quality/cars/invite/${encodeURIComponent(token)}/attachments`);
}

export async function qmsUploadCarInviteAttachment(
  token: string,
  file: File,
  description?: string
): Promise<CARAttachmentOut> {
  const formData = new FormData();
  formData.append("file", file);
  if (description?.trim()) formData.append("description", description.trim());
  const res = await fetch(`${getApiBaseUrl()}/quality/cars/invite/${encodeURIComponent(token)}/attachments`, {
    method: "POST",
    body: formData,
    credentials: "omit",
  });

  if (res.status === 401 || res.status === 403) {
    throw new Error("This invite is not available. Check that the link is correct and still active.");
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`QMS API ${res.status}: ${text || res.statusText}`);
  }
  return (await res.json()) as CARAttachmentOut;
}
export async function qmsUpdateCarInviteAttachment(
  token: string,
  attachmentId: string,
  payload: { description?: string | null }
): Promise<CARAttachmentOut> {
  return publicSendJson<CARAttachmentOut>(
    `/quality/cars/invite/${encodeURIComponent(token)}/attachments/${encodeURIComponent(attachmentId)}`,
    "PATCH",
    payload
  );
}

export async function qmsDeleteCarInviteAttachment(token: string, attachmentId: string): Promise<void> {
  await publicSendJson<void>(
    `/quality/cars/invite/${encodeURIComponent(token)}/attachments/${encodeURIComponent(attachmentId)}`,
    "DELETE",
    undefined
  );
}




export async function qmsListCarAttachments(carId: string): Promise<CARAttachmentOut[]> {
  return fetchJson<CARAttachmentOut[]>(`/quality/cars/${encodeURIComponent(carId)}/attachments`);
}

export async function qmsDownloadCarAttachmentBlob(carId: string, attachmentId: string): Promise<Blob> {
  return downloadBinary(`/quality/cars/${encodeURIComponent(carId)}/attachments/${encodeURIComponent(attachmentId)}/download`);
}

export async function qmsListCarAttachmentsBulk(params?: {
  car_ids?: string[];
}): Promise<CARAttachmentOut[]> {
  const qs = new URLSearchParams();
  (params?.car_ids ?? []).forEach((carId) => qs.append("car_ids", carId));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson<CARAttachmentOut[]>(`/quality/cars/attachments/bulk${suffix}`);
}

export async function qmsUploadCarAttachment(carId: string, file: File): Promise<CARAttachmentOut> {
  const formData = new FormData();
  formData.append("file", file);
  const authToken = getToken();
  const res = await fetch(`${getApiBaseUrl()}/quality/cars/${encodeURIComponent(carId)}/attachments`, {
    method: "POST",
    headers: {
      ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    },
    body: formData,
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
  return (await res.json()) as CARAttachmentOut;
}

export async function qmsDeleteCarAttachment(carId: string, attachmentId: string): Promise<void> {
  await sendJson<void>(`/quality/cars/${encodeURIComponent(carId)}/attachments/${encodeURIComponent(attachmentId)}`, "DELETE", undefined);
}

export type QMSNotificationSeverity = "INFO" | "ACTION_REQUIRED" | "WARNING";

export interface QMSNotificationOut {
  id: string;
  user_id: string;
  message: string;
  severity: QMSNotificationSeverity;
  created_by_user_id: string | null;
  action_url?: string | null;
  action_label?: string | null;
  entity_type?: string | null;
  entity_id?: string | null;
  created_at: string;
  read_at: string | null;
}

export interface QMSNotificationSummaryOut {
  unread_count: number;
  latest_created_at: string | null;
}

export async function qmsListNotifications(params?: {
  include_read?: boolean;
  limit?: number;
}): Promise<QMSNotificationOut[]> {
  const suffix = toQuery({ include_read: params?.include_read ?? false, limit: params?.limit ?? 20 });
  return fetchJson<QMSNotificationOut[]>(`/quality/notifications/me${suffix}`);
}

export async function qmsGetNotificationSummary(): Promise<QMSNotificationSummaryOut> {
  const token = getToken();
  const headers = new Headers({
    Accept: "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  });
  const cachedEtag = readStoredNotificationSummaryEtag();
  if (cachedEtag) {
    headers.set("If-None-Match", cachedEtag);
  }

  const res = await fetch(`${API_BASE}/quality/notifications/me/summary`, {
    method: "GET",
    headers,
    credentials: "include",
  });

  if (res.status === 304) {
    return readStoredNotificationSummary() ?? { unread_count: 0, latest_created_at: null };
  }

  if (res.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }

  if (res.status === 503) {
    const text = await res.text().catch(() => "");
    throw new Error(text || "Service unavailable. Please retry or contact support.");
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    if (res.status === 403 && /subscription is locked|go to billing/i.test(text)) {
      return readStoredNotificationSummary() ?? { unread_count: 0, latest_created_at: null };
    }
    throw new Error(`QMS API ${res.status}: ${text || res.statusText}`);
  }

  const summary = (await res.json()) as QMSNotificationSummaryOut;
  writeStoredNotificationSummary(summary, res.headers.get("ETag"));
  return summary;
}

export async function qmsMarkAllNotificationsRead(): Promise<{ updated: number }> {
  return sendJson<{ updated: number }>("/quality/notifications/me/read-all", "POST", {});
}

export async function qmsMarkNotificationRead(notificationId: string): Promise<QMSNotificationOut> {
  return sendJson<QMSNotificationOut>(`/quality/notifications/${notificationId}/read`, "POST", {});
}

export interface AuditorStatsOut {
  user_id: string;
  audits_total: number;
  audits_open: number;
  audits_closed: number;
  lead_audits: number;
  observer_audits: number;
  assistant_audits: number;
}

export async function qmsGetAuditorStats(userId: string): Promise<AuditorStatsOut> {
  return fetchJson<AuditorStatsOut>(`/quality/auditors/${userId}/stats`);
}

export async function downloadAuditEvidencePack(auditId: string): Promise<Blob> {
  return downloadEvidencePack(`/quality/audits/${encodeURIComponent(auditId)}/evidence-pack`);
}

export async function downloadCarEvidencePack(carId: string): Promise<Blob> {
  return downloadEvidencePack(`/quality/cars/${encodeURIComponent(carId)}/evidence-pack`);
}
