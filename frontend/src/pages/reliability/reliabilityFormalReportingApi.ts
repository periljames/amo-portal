import { getToken, handleAuthFailure, markSessionActivity } from "../../services/auth";
import { getApiBaseUrl } from "../../services/config";

const API_BASE = getApiBaseUrl();
const ROOT = `${API_BASE}/reliability/formal-reporting`;

export type FormalReportStatus =
  | "DRAFT"
  | "DATA_REVIEW"
  | "TECHNICAL_REVIEW"
  | "QUALITY_REVIEW"
  | "APPROVAL_PENDING"
  | "APPROVED"
  | "PUBLISHED"
  | "SUPERSEDED"
  | "WITHDRAWN";

export type FormalPeriodType =
  | "MONTHLY"
  | "QUARTERLY"
  | "HALF_YEAR"
  | "ANNUAL"
  | "YEAR_TO_DATE"
  | "ROLLING_3_MONTH"
  | "ROLLING_6_MONTH"
  | "ROLLING_12_MONTH"
  | "CUSTOM";

export type RequirementAssessmentStatus =
  | "SATISFIED"
  | "NOT_APPLICABLE"
  | "WITHHELD"
  | "GAP"
  | "SUPERSEDED";

export type FormalProfile = {
  id: string;
  code: "KCAA" | "EASA" | "FAA" | "OPERATOR" | string;
  version: string;
  name: string;
  authority: string;
  jurisdiction: string;
  effective_date?: string | null;
  revision?: string | null;
  status: string;
  required_sections: Array<{ code: string; title: string; required?: boolean }>;
  mandatory_kpis: string[];
  historical_windows: number[];
  approval_workflow: Record<string, unknown>;
  publication_rules: Record<string, unknown>;
  source_manifest: Array<Record<string, unknown>>;
};

export type FormalSection = {
  id: string;
  code: string;
  sequence: number;
  title: string;
  required: boolean;
  status: "DRAFT" | "READY" | "WITHHELD" | "NOT_APPLICABLE";
  computed_data: Record<string, unknown>;
  commentary: Array<Record<string, unknown>>;
  evidence_refs: Array<Record<string, unknown>>;
  warnings: string[];
};

export type FormalRequirementAssessment = {
  id: string;
  requirement_id: string;
  section_code: string;
  applicable: boolean;
  status: RequirementAssessmentStatus;
  requirement: {
    requirement_key?: string;
    authority?: string;
    source_reference?: string;
    paragraph_reference?: string | null;
    source_url?: string;
    controlled_summary?: string;
    obligation_status?: "MANDATORY" | "ADVISORY" | string;
    revision?: string;
  };
  evidence_refs: Array<Record<string, unknown>>;
  calculation_refs: Array<Record<string, unknown>>;
  source_refs: Array<Record<string, unknown>>;
  reviewer_note?: string | null;
};

export type CompletenessCheck = {
  code: string;
  passed: boolean;
  raw_passed: boolean;
  overridden: boolean;
  blocking: boolean;
  message: string;
};

export type FormalCompleteness = {
  passed?: boolean;
  checked_at?: string;
  checks?: CompletenessCheck[];
  blocking_failures?: string[];
  override_count?: number;
};

export type FormalReport = {
  id: string;
  report_number: string;
  revision: number;
  title: string;
  period_type: FormalPeriodType;
  period_start: string;
  period_end: string;
  status: FormalReportStatus;
  profile_id: string;
  profile_code: string;
  profile_version: string;
  data_cutoff_at?: string | null;
  effectivity: Record<string, unknown>;
  effectivity_frozen_at?: string | null;
  html_sha256?: string | null;
  pdf_sha256?: string | null;
  published_at?: string | null;
  supersedes_report_id?: string | null;
  created_at: string;
  regulatory_manifest?: Array<Record<string, unknown>>;
  source_population?: Record<string, unknown>;
  formula_revisions?: Array<Record<string, unknown>>;
  data_quality?: Record<string, unknown>;
  completeness?: FormalCompleteness;
  sections?: FormalSection[];
  requirements?: FormalRequirementAssessment[];
};

export type FormalReportList = {
  total: number;
  limit: number;
  offset: number;
  reports: FormalReport[];
};

function authHeaders(json = false): Record<string, string> {
  const token = getToken();
  return {
    Accept: "application/json",
    ...(json ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  activity = "reliability-formal-reporting"
): Promise<T> {
  markSessionActivity(activity);
  const response = await fetch(`${ROOT}${path}`, {
    credentials: "include",
    ...options,
    headers: {
      ...authHeaders(options.body !== undefined),
      ...(options.headers || {}),
    },
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

export async function listFormalProfiles(): Promise<FormalProfile[]> {
  const payload = await request<{ profiles: FormalProfile[] }>("/profiles", {}, "reliability-formal-profile-list");
  return payload.profiles;
}

export async function listFormalReports(limit = 100, offset = 0): Promise<FormalReportList> {
  return request<FormalReportList>(`/reports?limit=${limit}&offset=${offset}`, {}, "reliability-formal-report-list");
}

export async function getFormalReport(reportId: string): Promise<FormalReport> {
  return request<FormalReport>(`/reports/${encodeURIComponent(reportId)}`, {}, "reliability-formal-report-open");
}

export async function createFormalReport(payload: {
  profile_id: string;
  programme_id?: string | null;
  report_number: string;
  revision?: number;
  title: string;
  period_type: FormalPeriodType;
  period_start: string;
  period_end: string;
}): Promise<FormalReport> {
  return request<FormalReport>("/reports", {
    method: "POST",
    body: JSON.stringify(payload),
  }, "reliability-formal-report-create");
}

export async function freezeFormalReport(
  reportId: string,
  payload: {
    aircraft_serial_numbers: string[];
    aircraft_types?: string[];
    effectivity?: Record<string, unknown>;
  }
): Promise<FormalReport> {
  return request<FormalReport>(`/reports/${encodeURIComponent(reportId)}/freeze`, {
    method: "POST",
    body: JSON.stringify({
      aircraft_serial_numbers: payload.aircraft_serial_numbers,
      aircraft_types: payload.aircraft_types || [],
      effectivity: payload.effectivity || {},
    }),
  }, "reliability-formal-report-freeze");
}

export async function updateFormalSection(
  reportId: string,
  sectionCode: string,
  payload: {
    status: FormalSection["status"];
    commentary: Array<Record<string, unknown>>;
    evidence_refs?: Array<Record<string, unknown>>;
    warnings?: string[];
  }
): Promise<FormalReport> {
  return request<FormalReport>(
    `/reports/${encodeURIComponent(reportId)}/sections/${encodeURIComponent(sectionCode)}`,
    {
      method: "PUT",
      body: JSON.stringify({
        status: payload.status,
        commentary: payload.commentary,
        evidence_refs: payload.evidence_refs || [],
        warnings: payload.warnings || [],
      }),
    },
    "reliability-formal-section-update"
  );
}

export async function updateFormalRequirement(
  reportId: string,
  assessmentId: string,
  payload: {
    applicable: boolean;
    status: RequirementAssessmentStatus;
    reviewer_note?: string | null;
    evidence_refs?: Array<Record<string, unknown>>;
    calculation_refs?: Array<Record<string, unknown>>;
    source_refs?: Array<Record<string, unknown>>;
  }
): Promise<FormalReport> {
  return request<FormalReport>(
    `/reports/${encodeURIComponent(reportId)}/requirements/${encodeURIComponent(assessmentId)}`,
    {
      method: "PUT",
      body: JSON.stringify({
        applicable: payload.applicable,
        status: payload.status,
        reviewer_note: payload.reviewer_note || null,
        evidence_refs: payload.evidence_refs || [],
        calculation_refs: payload.calculation_refs || [],
        source_refs: payload.source_refs || [],
      }),
    },
    "reliability-formal-requirement-update"
  );
}

export async function renderFormalReport(reportId: string): Promise<FormalReport> {
  return request<FormalReport>(`/reports/${encodeURIComponent(reportId)}/render`, {
    method: "POST",
  }, "reliability-formal-report-render");
}

export async function runFormalCompleteness(reportId: string): Promise<FormalCompleteness> {
  return request<FormalCompleteness>(`/reports/${encodeURIComponent(reportId)}/completeness`, {
    method: "POST",
  }, "reliability-formal-completeness");
}

export async function transitionFormalReport(
  reportId: string,
  toStatus: FormalReportStatus,
  comment?: string
): Promise<FormalReport> {
  return request<FormalReport>(`/reports/${encodeURIComponent(reportId)}/transition`, {
    method: "POST",
    body: JSON.stringify({ to_status: toStatus, comment: comment || null }),
  }, "reliability-formal-transition");
}

export function formalReportViewUrl(reportId: string): string {
  return `${ROOT}/reports/${encodeURIComponent(reportId)}/view`;
}

export function formalReportPdfUrl(reportId: string): string {
  return `${ROOT}/reports/${encodeURIComponent(reportId)}/pdf`;
}
