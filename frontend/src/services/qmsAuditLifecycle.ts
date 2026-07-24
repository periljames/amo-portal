import { getToken, handleAuthFailure } from "./auth";
import { getApiBaseUrl } from "./config";
import { beginBackgroundLoading, beginLoading, endBackgroundLoading, endLoading } from "./loading";
import type { QMSAuditOut } from "./qms";

export type QualityAuditStageState =
  | "NOT_READY"
  | "READY"
  | "IN_PROGRESS"
  | "BLOCKED"
  | "COMPLETE"
  | "LOCKED";

export interface QualityAuditStageAction {
  id: string;
  label: string;
  enabled: boolean;
  helper: string | null;
  path: string | null;
  method: string | null;
}

export interface QualityAuditStage {
  id: "war-room" | "checklist" | "findings" | "cars" | "evidence" | "report" | "closeout";
  label: string;
  state: QualityAuditStageState;
  complete: boolean;
  active: boolean;
  metric: string | null;
  helper: string | null;
  blockers: string[];
  warnings: string[];
  completed_at: string | null;
  completed_by_user_id: string | null;
  primary_action: QualityAuditStageAction | null;
}

export interface QualityAuditWorkflowV2 {
  audit_id: string;
  current_stage_id: QualityAuditStage["id"];
  current_stage_label: string;
  lifecycle_status: string;
  percent_complete: number;
  findings_total: number;
  findings_open: number;
  cars_total: number;
  cars_open: number;
  evidence_total: number;
  evidence_pending: number;
  checklist_uploaded: boolean;
  checklist_complete: boolean;
  report_uploaded: boolean;
  report_issued: boolean;
  stages: QualityAuditStage[];
}

export interface QualityAuditWorkspaceV2 {
  audit: QMSAuditOut;
  workflow: QualityAuditWorkflowV2;
}

export interface QualityAuditDocument {
  id: string;
  audit_id: string;
  version_number: number;
  parent_version_id: string | null;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  lifecycle_status: string;
  created_at: string;
  created_by_user_id: string | null;
  committed_at: string | null;
  issued_at: string | null;
  issued_by_user_id: string | null;
  source_type: string | null;
  fillable: "UNKNOWN" | "YES" | "NO" | null;
  field_count: number | null;
  issue_label: string | null;
  distribution_status: string | null;
  download_url: string;
}

export interface QualityAuditChecklistMetadata {
  available: boolean;
  current: QualityAuditDocument | null;
  source: QualityAuditDocument | null;
  versions: QualityAuditDocument[];
  portal_item_count: number;
  portal_completed_count: number;
  explicitly_completed: boolean;
  read_only: boolean;
  read_only_reason: string | null;
}

export interface QualityAuditReportMetadata {
  available: boolean;
  current_draft: QualityAuditDocument | null;
  issued: QualityAuditDocument | null;
  versions: QualityAuditDocument[];
  read_only: boolean;
  read_only_reason: string | null;
}

export interface QualityAuditPreviousAudit {
  id: string;
  audit_ref: string;
  title: string;
  status: string;
  planned_start: string | null;
  actual_end: string | null;
  lead_auditor_name: string | null;
  findings_total: number;
  open_carryovers: number;
  possible_repeat_findings: number;
  match_reason: string;
  report: {
    available: boolean;
    document_id: string | null;
    filename: string | null;
    issued_at: string | null;
    issue_label: string | null;
    download_url: string | null;
  };
  workspace_path: string;
}

export interface QualityAuditCarryoverFinding {
  finding_id: string;
  finding_ref: string | null;
  level: string;
  requirement_ref: string | null;
  description: string;
  target_close_date: string | null;
  car_id: string | null;
  car_number: string | null;
  car_status: string | null;
  overdue: boolean;
}

export interface QualityAuditNoticeEvent {
  id: string;
  action: string;
  label: string;
  occurred_at: string;
  actor_user_id: string | null;
  actor_name: string | null;
  detail: string | null;
}

export interface QualityAuditActionItem {
  id: string;
  label: string;
  state: "PENDING" | "READY" | "COMPLETE" | "BLOCKED" | "WARNING";
  owner_label: string | null;
  due_at: string | null;
  helper: string | null;
  action_path: string | null;
}

export interface QualityAuditWarRoomContext {
  audit: QMSAuditOut;
  workflow: QualityAuditWorkflowV2;
  readiness: {
    ready: boolean;
    blockers: string[];
    warnings: string[];
  };
  previous_audits: QualityAuditPreviousAudit[];
  carryover_findings: QualityAuditCarryoverFinding[];
  notice_history: QualityAuditNoticeEvent[];
  action_queue: QualityAuditActionItem[];
  checklist: QualityAuditChecklistMetadata;
  report: QualityAuditReportMetadata;
}

export interface QualityAuditEvidenceReview {
  id: string;
  audit_id: string;
  entity_type: string;
  entity_id: string;
  status: "PENDING" | "ACCEPTED" | "REJECTED";
  note: string | null;
  reviewed_by_user_id: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

type RequestMethod = "GET" | "POST" | "PATCH" | "DELETE";
type RequestMode = "background" | "foreground";

async function readError(response: Response): Promise<string> {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    const payload = await response.json().catch(() => null) as Record<string, unknown> | null;
    if (payload) {
      const detail = payload.detail;
      if (typeof detail === "string" && detail.trim()) return detail.trim();
      if (detail && typeof detail === "object") {
        const message = (detail as Record<string, unknown>).message;
        const blockers = (detail as Record<string, unknown>).blockers;
        if (typeof message === "string") {
          return Array.isArray(blockers) && blockers.length
            ? `${message} ${blockers.map(String).join(" ")}`
            : message;
        }
        return JSON.stringify(detail);
      }
      if (Array.isArray(detail)) return JSON.stringify(detail);
      for (const key of ["message", "error", "error_code"] as const) {
        const value = payload[key];
        if (typeof value === "string" && value.trim()) return value.trim();
      }
    }
  }
  return (await response.text().catch(() => "")).trim();
}

async function lifecycleRequest<T>(
  path: string,
  options: {
    method?: RequestMethod;
    body?: unknown;
    formData?: FormData;
    mode?: RequestMode;
    timeoutMs?: number;
  } = {},
): Promise<T> {
  const method = options.method ?? "GET";
  const mode = options.mode ?? (method === "GET" ? "background" : "foreground");
  const timeoutMs = options.timeoutMs ?? (method === "GET" ? 25_000 : 60_000);
  const token = getToken();
  const controller = new AbortController();
  let timedOut = false;

  if (mode === "background") beginBackgroundLoading();
  else beginLoading();

  const timeout = globalThis.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  try {
    const hasJson = options.body !== undefined && !options.formData;
    const response = await fetch(`${getApiBaseUrl()}${path}`, {
      method,
      headers: {
        Accept: "application/json",
        ...(hasJson ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      ...(options.formData
        ? { body: options.formData }
        : hasJson
          ? { body: JSON.stringify(options.body) }
          : {}),
      credentials: "include",
      signal: controller.signal,
    });

    if (response.status === 401) {
      handleAuthFailure("expired");
      throw new Error("Session expired. Please sign in again.");
    }
    if (!response.ok) {
      const detail = await readError(response);
      throw new Error(detail || `Quality lifecycle request failed with status ${response.status}.`);
    }
    if (response.status === 204) return undefined as T;
    return await response.json() as T;
  } catch (error) {
    if (timedOut) throw new Error(`Quality lifecycle request timed out after ${Math.ceil(timeoutMs / 1000)} seconds.`);
    throw error;
  } finally {
    globalThis.clearTimeout(timeout);
    if (mode === "background") endBackgroundLoading();
    else endLoading();
  }
}

function auditPath(auditId: string, suffix = ""): string {
  return `/quality/audits/${encodeURIComponent(auditId)}${suffix}`;
}

export function absoluteQualityUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  return `${getApiBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`;
}

export async function qmsGetAuditWorkspaceV2(auditId: string): Promise<QualityAuditWorkspaceV2> {
  return lifecycleRequest<QualityAuditWorkspaceV2>(auditPath(auditId, "/workspace"));
}

export async function qmsGetAuditWarRoomContext(auditId: string): Promise<QualityAuditWarRoomContext> {
  return lifecycleRequest<QualityAuditWarRoomContext>(auditPath(auditId, "/war-room-context"));
}

export async function qmsGetAuditChecklistMetadata(auditId: string): Promise<QualityAuditChecklistMetadata> {
  return lifecycleRequest<QualityAuditChecklistMetadata>(auditPath(auditId, "/documents/checklist"));
}

export async function qmsGetAuditReportMetadata(auditId: string): Promise<QualityAuditReportMetadata> {
  return lifecycleRequest<QualityAuditReportMetadata>(auditPath(auditId, "/documents/report"));
}

export async function qmsStartAuditLifecycle(auditId: string, note?: string): Promise<QualityAuditWorkspaceV2> {
  return lifecycleRequest<QualityAuditWorkspaceV2>(auditPath(auditId, "/lifecycle/start"), {
    method: "POST",
    body: { note: note?.trim() || null },
  });
}

export async function qmsCompleteAuditChecklist(auditId: string, note?: string): Promise<QualityAuditWorkspaceV2> {
  return lifecycleRequest<QualityAuditWorkspaceV2>(auditPath(auditId, "/lifecycle/checklist/complete"), {
    method: "POST",
    body: { note: note?.trim() || null },
  });
}

export async function qmsCompleteAuditFieldwork(auditId: string, note?: string): Promise<QualityAuditWorkspaceV2> {
  return lifecycleRequest<QualityAuditWorkspaceV2>(auditPath(auditId, "/lifecycle/fieldwork/complete"), {
    method: "POST",
    body: { note: note?.trim() || null },
  });
}

export async function qmsCloseAuditLifecycle(auditId: string, note?: string): Promise<QualityAuditWorkspaceV2> {
  return lifecycleRequest<QualityAuditWorkspaceV2>(auditPath(auditId, "/lifecycle/closeout"), {
    method: "POST",
    body: { note: note?.trim() || null },
  });
}

export async function qmsUploadChecklistSource(
  auditId: string,
  file: File,
  options: { fillable?: "UNKNOWN" | "YES" | "NO"; fieldCount?: number | null } = {},
): Promise<QualityAuditDocument> {
  const form = new FormData();
  form.append("file", file, file.name);
  form.append("fillable", options.fillable ?? "UNKNOWN");
  if (options.fieldCount !== null && options.fieldCount !== undefined) form.append("field_count", String(options.fieldCount));
  return lifecycleRequest<QualityAuditDocument>(auditPath(auditId, "/documents/checklist/source"), {
    method: "POST",
    formData: form,
  });
}

export async function qmsSaveChecklistDraft(
  auditId: string,
  file: File,
  options: { fillable?: "UNKNOWN" | "YES" | "NO"; fieldCount?: number | null } = {},
): Promise<QualityAuditDocument> {
  const form = new FormData();
  form.append("file", file, file.name);
  form.append("fillable", options.fillable ?? "UNKNOWN");
  if (options.fieldCount !== null && options.fieldCount !== undefined) form.append("field_count", String(options.fieldCount));
  return lifecycleRequest<QualityAuditDocument>(auditPath(auditId, "/documents/checklist/draft"), {
    method: "POST",
    formData: form,
  });
}

export async function qmsCommitChecklistVersion(
  auditId: string,
  versionId: string,
  options: { fillable?: "UNKNOWN" | "YES" | "NO"; fieldCount?: number | null; note?: string | null } = {},
): Promise<QualityAuditDocument> {
  return lifecycleRequest<QualityAuditDocument>(auditPath(auditId, "/documents/checklist/commit"), {
    method: "POST",
    body: {
      version_id: versionId,
      fillable: options.fillable ?? "UNKNOWN",
      field_count: options.fieldCount ?? null,
      note: options.note?.trim() || null,
    },
  });
}

export async function qmsUploadReportDraft(auditId: string, file: File): Promise<QualityAuditDocument> {
  const form = new FormData();
  form.append("file", file, file.name);
  return lifecycleRequest<QualityAuditDocument>(auditPath(auditId, "/documents/report/draft"), {
    method: "POST",
    formData: form,
  });
}

export async function qmsIssueReportVersion(
  auditId: string,
  versionId: string,
  issueLabel: string,
  note?: string,
): Promise<QualityAuditDocument> {
  return lifecycleRequest<QualityAuditDocument>(auditPath(auditId, "/documents/report/issue"), {
    method: "POST",
    body: {
      version_id: versionId,
      issue_label: issueLabel.trim(),
      note: note?.trim() || null,
    },
  });
}

export async function qmsReviewAuditEvidence(
  auditId: string,
  payload: {
    entity_type: "CHECKLIST_VERSION" | "FINDING_ATTACHMENT" | "CAR_ATTACHMENT" | "REPORT_VERSION" | "OTHER";
    entity_id: string;
    status: "PENDING" | "ACCEPTED" | "REJECTED";
    note?: string | null;
  },
): Promise<QualityAuditEvidenceReview> {
  return lifecycleRequest<QualityAuditEvidenceReview>(auditPath(auditId, "/evidence/reviews"), {
    method: "POST",
    body: {
      ...payload,
      note: payload.note?.trim() || null,
    },
  });
}

export async function qmsDownloadLifecycleDocument(document: QualityAuditDocument): Promise<void> {
  const token = getToken();
  const response = await fetch(absoluteQualityUrl(document.download_url), {
    method: "GET",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    credentials: "include",
  });
  if (response.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }
  if (!response.ok) throw new Error(await readError(response) || "Controlled document could not be downloaded.");
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = document.filename;
  anchor.click();
  globalThis.setTimeout(() => URL.revokeObjectURL(url), 1_000);
}
