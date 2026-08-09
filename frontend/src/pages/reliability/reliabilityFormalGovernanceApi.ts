import { getToken, handleAuthFailure, markSessionActivity } from "../../services/auth";
import { getApiBaseUrl } from "../../services/config";
import type { FormalPeriodType, FormalReport } from "./reliabilityFormalReportingApi";

const ROOT = `${getApiBaseUrl()}/reliability/formal-reporting`;

export type ReportingScheduleStatus =
  | "PLANNED"
  | "DUE"
  | "IN_PREPARATION"
  | "IN_REVIEW"
  | "COMPLETE"
  | "OVERDUE"
  | "CANCELLED";

export type ReportingSchedule = {
  id: string;
  profile_id?: string | null;
  programme_id?: string | null;
  report_id?: string | null;
  obligation_code: string;
  name: string;
  period_type: FormalPeriodType;
  period_start: string;
  period_end: string;
  due_date: string;
  cycle_config: Record<string, unknown>;
  status: ReportingScheduleStatus;
  effective_status: ReportingScheduleStatus;
  overdue: boolean;
  owner_user_id?: string | null;
  completeness: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type AmpRecommendationStatus =
  | "IDENTIFIED"
  | "ANALYSIS"
  | "RECOMMENDED"
  | "TECHNICAL_REVIEW"
  | "QUALITY_REVIEW"
  | "AUTHORITY_APPROVAL_REQUIRED"
  | "APPROVED"
  | "IMPLEMENTED"
  | "EFFECTIVENESS_MONITORING"
  | "CLOSED";

export type AmpRecommendation = {
  id: string;
  report_id?: string | null;
  programme_id?: string | null;
  programme_item_id?: number | null;
  title: string;
  summary: string;
  change_type: string;
  status: AmpRecommendationStatus;
  source_evidence: Array<Record<string, unknown>>;
  current_requirement: Record<string, unknown>;
  proposed_change: Record<string, unknown>;
  technical_basis: Record<string, unknown>;
  authority_approval_required: boolean;
  owner_user_id?: string | null;
  target_date?: string | null;
  effectiveness_due_date?: string | null;
  created_at: string;
  updated_at: string;
};

export type FormalDistribution = {
  id: string;
  report_id?: string;
  recipient_user_id?: string | null;
  recipient_role?: string | null;
  external_recipient_ref?: string | null;
  channel: "PORTAL";
  revision: number;
  report_hash: string;
  distributed_at: string;
};

function headers(json = false): Record<string, string> {
  const token = getToken();
  return {
    Accept: "application/json",
    ...(json ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function request<T>(path: string, options: RequestInit = {}, activity = "reliability-formal-governance"): Promise<T> {
  markSessionActivity(activity);
  const response = await fetch(`${ROOT}${path}`, {
    credentials: "include",
    ...options,
    headers: { ...headers(options.body !== undefined), ...(options.headers || {}) },
  });
  if (response.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }
  if (!response.ok) {
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const payload = (await response.json()) as { detail?: unknown };
      const detail = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail || payload);
      throw new Error(detail || `Request failed (${response.status})`);
    }
    throw new Error((await response.text()) || `Request failed (${response.status})`);
  }
  return (await response.json()) as T;
}

export async function listReportingSchedule(): Promise<ReportingSchedule[]> {
  const payload = await request<{ items: ReportingSchedule[] }>("/schedule?limit=500");
  return payload.items;
}

export async function createReportingSchedule(payload: {
  profile_id?: string | null;
  obligation_code: string;
  name: string;
  period_type: FormalPeriodType;
  period_start: string;
  period_end: string;
  due_date: string;
  cycle_config?: Record<string, unknown>;
}): Promise<ReportingSchedule> {
  return request<ReportingSchedule>("/schedule", {
    method: "POST",
    body: JSON.stringify({ ...payload, cycle_config: payload.cycle_config || {} }),
  });
}

export async function updateReportingSchedule(
  scheduleId: string,
  status: ReportingScheduleStatus,
  reportId?: string | null,
): Promise<ReportingSchedule> {
  return request<ReportingSchedule>(`/schedule/${encodeURIComponent(scheduleId)}/status`, {
    method: "PUT",
    body: JSON.stringify({ status, report_id: reportId || null }),
  });
}

export async function listAmpRecommendations(reportId?: string): Promise<AmpRecommendation[]> {
  const query = reportId ? `?report_id=${encodeURIComponent(reportId)}&limit=500` : "?limit=500";
  const payload = await request<{ items: AmpRecommendation[] }>(`/amp-recommendations${query}`);
  return payload.items;
}

export async function createAmpRecommendation(payload: {
  report_id?: string | null;
  title: string;
  summary: string;
  change_type: string;
  source_evidence: Array<Record<string, unknown>>;
  current_requirement?: Record<string, unknown>;
  proposed_change: Record<string, unknown>;
  technical_basis?: Record<string, unknown>;
  authority_approval_required?: boolean;
  target_date?: string | null;
  effectiveness_due_date?: string | null;
}): Promise<AmpRecommendation> {
  return request<AmpRecommendation>("/amp-recommendations", {
    method: "POST",
    body: JSON.stringify({
      ...payload,
      current_requirement: payload.current_requirement || {},
      technical_basis: payload.technical_basis || {},
      authority_approval_required: Boolean(payload.authority_approval_required),
    }),
  });
}

export async function transitionAmpRecommendation(
  recommendationId: string,
  toStatus: AmpRecommendationStatus,
  comment: string,
): Promise<AmpRecommendation> {
  return request<AmpRecommendation>(`/amp-recommendations/${encodeURIComponent(recommendationId)}/transition`, {
    method: "POST",
    body: JSON.stringify({ to_status: toStatus, comment }),
  });
}

export async function createSupersedingRevision(reportId: string, title?: string): Promise<FormalReport> {
  return request<FormalReport>(`/reports/${encodeURIComponent(reportId)}/superseding-revision`, {
    method: "POST",
    body: JSON.stringify({ title: title || null }),
  });
}

export async function listDistribution(reportId: string): Promise<FormalDistribution[]> {
  const payload = await request<{ items: FormalDistribution[] }>(`/reports/${encodeURIComponent(reportId)}/distribution`);
  return payload.items;
}

export async function distributeReport(
  reportId: string,
  payload: { recipient_user_id?: string | null; recipient_role?: string | null; external_recipient_ref?: string | null },
): Promise<FormalDistribution> {
  return request<FormalDistribution>(`/reports/${encodeURIComponent(reportId)}/distribution`, {
    method: "POST",
    body: JSON.stringify({ ...payload, channel: "PORTAL" }),
  });
}
