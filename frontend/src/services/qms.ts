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
import { getApiBaseUrl } from "./config";

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
  status: QMSAuditStatus;
  audit_ref: string;
  title: string;
  scope?: string | null;
  criteria?: string | null;
  auditee?: string | null;
  auditee_email?: string | null;
  auditee_user_id?: string | null;
  lead_auditor_user_id?: string | null;
  observer_auditor_user_id?: string | null;
  assistant_auditor_user_id?: string | null;
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
}

export interface QMSAuditScheduleOut {
  id: string;
  domain: string;
  kind: string;
  frequency: QMSAuditScheduleFrequency;
  title: string;
  scope?: string | null;
  criteria?: string | null;
  auditee?: string | null;
  auditee_email?: string | null;
  auditee_user_id?: string | null;
  lead_auditor_user_id?: string | null;
  observer_auditor_user_id?: string | null;
  assistant_auditor_user_id?: string | null;
  duration_days: number;
  next_due_date: string;
  last_run_at?: string | null;
  is_active: boolean;
  created_by_user_id?: string | null;
  created_at: string;
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
  created_at: string;
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

const API_BASE = getApiBaseUrl();

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

    xhr.send();
  });
}

async function downloadBinary(path: string): Promise<Blob> {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    method: "GET",
    headers: {
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
  return res.blob();
}

async function fetchJson<T>(path: string): Promise<T> {
  const token = getToken();
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
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

  if (res.status === 503) {
    const text = await res.text().catch(() => "");
    throw new Error(text || "Service unavailable. Please retry or contact support.");
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`QMS API ${res.status}: ${text || res.statusText}`);
  }
  return (await res.json()) as T;
}

async function sendJson<T>(
  path: string,
  method: "POST" | "PATCH" | "DELETE",
  body: unknown
): Promise<T> {
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
  findings_overdue_total: number;
}

export async function qmsGetDashboard(params?: {
  domain?: string;
}): Promise<QMSDashboardOut> {
  return fetchJson<QMSDashboardOut>(`/quality/qms/dashboard${toQuery(params ?? {})}`);
}


export interface QMSCockpitActionItemOut {
  id: string;
  kind: string;
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
  suppliers_active: number;
  suppliers_inactive: number;
  audit_closure_trend: {
    period_start: string;
    period_end: string;
    closed_count: number;
    audit_ids: string[];
  }[];
  action_queue: QMSCockpitActionItemOut[];
}

export async function qmsGetCockpitSnapshot(params?: {
  domain?: string;
}): Promise<QMSCockpitSnapshotOut> {
  return fetchJson<QMSCockpitSnapshotOut>(`/quality/qms/cockpit-snapshot${toQuery(params ?? {})}`);
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

export async function qmsListAuditSchedules(params?: {
  domain?: string;
  active?: boolean;
}): Promise<QMSAuditScheduleOut[]> {
  return fetchJson<QMSAuditScheduleOut[]>(
    `/quality/audits/schedules${toQuery(params ?? {})}`
  );
}

export async function qmsCreateAuditSchedule(payload: {
  domain: string;
  kind: string;
  frequency: QMSAuditScheduleFrequency;
  title: string;
  scope?: string | null;
  criteria?: string | null;
  auditee?: string | null;
  auditee_email?: string | null;
  auditee_user_id?: string | null;
  lead_auditor_user_id?: string | null;
  observer_auditor_user_id?: string | null;
  assistant_auditor_user_id?: string | null;
  duration_days: number;
  next_due_date: string;
}): Promise<QMSAuditScheduleOut> {
  return sendJson<QMSAuditScheduleOut>(
    "/quality/audits/schedules",
    "POST",
    payload
  );
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

export async function qmsListFindings(auditId: string): Promise<QMSFindingOut[]> {
  return fetchJson<QMSFindingOut[]>(`/quality/audits/${auditId}/findings`);
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
}): Promise<CAROut[]> {
  return fetchJson<CAROut[]>(`/quality/cars${toQuery(params ?? {})}`);
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
  finding_id?: string | null;
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

export async function qmsDeleteCar(carId: string): Promise<void> {
  await sendJson(`/quality/cars/${carId}`, "DELETE", {});
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

export interface CARAttachmentOut {
  id: string;
  car_id: string;
  filename: string;
  content_type: string | null;
  size_bytes: number | null;
  sha256: string | null;
  uploaded_at: string;
  download_url: string;
}

export async function qmsListCarInviteAttachments(token: string): Promise<CARAttachmentOut[]> {
  return fetchJson<CARAttachmentOut[]>(`/quality/cars/invite/${token}/attachments`);
}

export async function qmsUploadCarInviteAttachment(
  token: string,
  file: File
): Promise<CARAttachmentOut> {
  const formData = new FormData();
  formData.append("file", file);
  const authToken = getToken();
  const res = await fetch(`${getApiBaseUrl()}/quality/cars/invite/${token}/attachments`, {
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



export async function qmsListCarAttachments(carId: string): Promise<CARAttachmentOut[]> {
  return fetchJson<CARAttachmentOut[]>(`/quality/cars/${encodeURIComponent(carId)}/attachments`);
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
  created_at: string;
  read_at: string | null;
}

export async function qmsListNotifications(): Promise<QMSNotificationOut[]> {
  return fetchJson<QMSNotificationOut[]>("/quality/notifications/me");
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
