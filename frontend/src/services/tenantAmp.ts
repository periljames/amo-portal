import { getToken, handleAuthFailure } from "./auth";
import { portalFetch } from "./offlineHttp";

export type AircraftTypeTemplate = {
  id: string;
  family_id: string;
  code: string;
  manufacturer: string;
  model: string;
  variant: string | null;
  series: string | null;
  type_certificate: string | null;
  icao_type_designator: string | null;
  category: string;
  status: string;
  created_at: string;
};

export type AircraftTypeRevision = {
  id: string;
  template_id: string;
  revision_code: string;
  title: string;
  status: "DRAFT" | "PUBLISHED" | "SUPERSEDED" | "WITHDRAWN";
  effective_date: string | null;
  content_hash: string | null;
  change_summary: string | null;
};

export type TenantProgramme = {
  id: string;
  amo_id: string;
  code: string;
  title: string;
  authority: string | null;
  approval_reference: string | null;
  status: string;
  created_at: string;
};

export type TenantProgrammeRevision = {
  id: string;
  programme_id: string;
  revision_code: string;
  status: "DRAFT" | "PUBLISHED" | "SUPERSEDED" | "WITHDRAWN";
  aircraft_type_revision_id: string;
  effectivity_rule_version_id: string | null;
  base_content_pack_revision_id: string | null;
  source_reference: string;
  source_revision: string;
  source_currentness_at_approval: string | null;
  approval_reference: string | null;
  content_hash: string | null;
  change_summary: string | null;
  created_at: string;
  published_at: string | null;
};

export type BaselineCandidate = {
  pack_id: string;
  pack_code: string;
  manufacturer: string;
  family: string;
  series: string | null;
  revision_id: string;
  revision_code: string;
  content_hash: string | null;
};

export type BaselineResolution = {
  aircraft_type_revision_id: string;
  template_id: string;
  template_code: string;
  model: string;
  variant: string | null;
  series: string | null;
  series_confidence: "EXPLICIT" | "DERIVED" | "UNRESOLVED";
  series_reason: string;
  state: "RESOLVED" | "CONFIRM_DERIVED_SERIES" | "AMBIGUOUS" | "UNRESOLVED";
  candidates: BaselineCandidate[];
};

export type AmpComparisonTask = {
  id: string;
  source_content_task_id: string | null;
  decision: "INHERIT" | "TIGHTEN" | "ADD" | "LEGACY";
  task_code: string;
  title: string;
  ata_chapter: string | null;
  programme_section: string | null;
  task_type: string | null;
  oem_intervals_json: Record<string, unknown> | null;
  amp_intervals_json: Record<string, unknown>;
  oem_raw_interval_text: string | null;
  effectivity_expression_json: Record<string, unknown>;
  raw_effectivity_text: string | null;
  source_requirements_json: Array<Record<string, unknown>>;
  source_reference: string;
  source_revision: string | null;
  source_page_ref: string | null;
  justification: string | null;
  approval_reference: string | null;
  is_mandatory: boolean;
  comparison_state: "SAME_AS_OEM" | "MORE_RESTRICTIVE" | "OPERATOR_ADDED" | "LEGACY_UNMAPPED";
};

export type AmpComparisonPage = {
  total: number;
  offset: number;
  limit: number;
  items: AmpComparisonTask[];
  counts: Record<string, number>;
};

export type ValidationIssue = {
  severity: "BLOCK" | "WARN" | "INFO";
  code: string;
  message: string;
  task_code?: string | null;
};

export type AmpValidation = {
  status: "PASS" | "WARN" | "BLOCKED";
  blocking_count: number;
  warning_count: number;
  issues: ValidationIssue[];
  summary: Record<string, number | string | boolean | null>;
  validation_run_id: string | null;
};

export type AircraftDefaults = {
  state: "RESOLVED" | "AMBIGUOUS" | "NO_TENANT_AMP" | "SERIES_CONFIRMATION_REQUIRED";
  oem: BaselineResolution;
  requires_series_confirmation: boolean;
  programme_candidates: Array<{
    programme_id: string;
    programme_code: string;
    programme_title: string;
    revision_id: string;
    revision_code: string;
    base_content_pack_revision_id: string | null;
    content_hash: string | null;
    approval_reference: string | null;
    source_currentness_at_approval: string | null;
    task_counts: Record<string, number>;
  }>;
  selected_programme_revision_id: string | null;
  selected_oem_baseline_revision_id: string | null;
  prefill: {
    type_revision_id: string;
    programme_revision_id: string;
    series: string | null;
    oem_baseline_revision_id: string | null;
  } | null;
};

function headers(): Headers {
  const result = new Headers({ Accept: "application/json", "Content-Type": "application/json" });
  const token = getToken();
  if (token) result.set("Authorization", `Bearer ${token}`);
  return result;
}

async function parseError(response: Response): Promise<Error> {
  const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
  if (typeof payload?.detail === "string") return new Error(payload.detail);
  if (payload?.detail && typeof payload.detail === "object") {
    const detail = payload.detail as { message?: string; reasons?: string[]; code?: string };
    const suffix = detail.reasons?.length ? ` ${detail.reasons.join("; ")}` : "";
    return new Error(`${detail.message || detail.code || "AMP validation failed"}${suffix}`);
  }
  return new Error(`AMP API ${response.status}: ${response.statusText}`);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await portalFetch(path, {
    ...init,
    headers: init?.headers ?? headers(),
    credentials: "include",
    offline: { cache: !init?.method || init.method === "GET", queueMutation: false },
  });
  if (response.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }
  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}

export const listAircraftTypes = () => request<AircraftTypeTemplate[]>("/architecture/catalogue/types");

export const listAircraftTypeRevisions = (templateId: string) =>
  request<AircraftTypeRevision[]>(`/architecture/catalogue/types/${encodeURIComponent(templateId)}/revisions`);

export const listTenantProgrammes = () => request<TenantProgramme[]>("/architecture/programmes");

export const createTenantProgramme = (payload: {
  code: string;
  title: string;
  authority?: string | null;
}) => request<TenantProgramme>("/architecture/programmes", { method: "POST", body: JSON.stringify(payload) });

export const listTenantProgrammeRevisions = (programmeId: string) =>
  request<TenantProgrammeRevision[]>(`/architecture/programmes/${encodeURIComponent(programmeId)}/revisions`);

export const resolveBaseline = (aircraftTypeRevisionId: string) =>
  request<BaselineResolution>(`/architecture/programmes/baseline-resolution?aircraft_type_revision_id=${encodeURIComponent(aircraftTypeRevisionId)}`);

export const resolveAircraftDefaults = (aircraftTypeRevisionId: string) =>
  request<AircraftDefaults>(`/architecture/programmes/aircraft-setup-defaults?aircraft_type_revision_id=${encodeURIComponent(aircraftTypeRevisionId)}`);

export const createAmpDraftFromOem = (
  programmeId: string,
  payload: {
    revision_code: string;
    aircraft_type_revision_id: string;
    base_content_pack_revision_id?: string | null;
    change_summary?: string | null;
    supersedes_revision_id?: string | null;
    confirm_derived_series?: boolean;
  },
) => request<TenantProgrammeRevision>(`/architecture/programmes/${encodeURIComponent(programmeId)}/revisions/from-oem`, {
  method: "POST",
  body: JSON.stringify(payload),
});

export const getAmpComparison = (
  revisionId: string,
  query: { search?: string; decision?: string; ata?: string; offset?: number; limit?: number } = {},
) => {
  const params = new URLSearchParams();
  if (query.search?.trim()) params.set("search", query.search.trim());
  if (query.decision && query.decision !== "ALL") params.set("decision", query.decision);
  if (query.ata) params.set("ata", query.ata);
  params.set("offset", String(query.offset ?? 0));
  params.set("limit", String(query.limit ?? 100));
  return request<AmpComparisonPage>(`/architecture/programmes/revisions/${encodeURIComponent(revisionId)}/comparison?${params.toString()}`);
};

export const updateAmpTask = (
  revisionId: string,
  taskId: string,
  payload: {
    decision: "INHERIT" | "TIGHTEN";
    intervals_json?: Record<string, unknown> | null;
    justification?: string | null;
    approval_reference?: string | null;
  },
) => request<AmpComparisonTask>(`/architecture/programmes/revisions/${encodeURIComponent(revisionId)}/tasks/${encodeURIComponent(taskId)}`, {
  method: "PATCH",
  body: JSON.stringify(payload),
});

export const addAmpTask = (
  revisionId: string,
  payload: {
    task_code: string;
    title: string;
    ata_chapter?: string | null;
    intervals_json: Record<string, unknown>;
    effectivity_expression_json?: Record<string, unknown>;
    source_reference: string;
    justification: string;
    approval_reference?: string | null;
    metadata_json?: Record<string, unknown>;
  },
) => request(`/architecture/programmes/revisions/${encodeURIComponent(revisionId)}/tasks`, {
  method: "POST",
  body: JSON.stringify(payload),
});

export const deleteAmpTask = (revisionId: string, taskId: string) =>
  request<void>(`/architecture/programmes/revisions/${encodeURIComponent(revisionId)}/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" });

export const validateAmpRevision = (revisionId: string) =>
  request<AmpValidation>(`/architecture/programmes/revisions/${encodeURIComponent(revisionId)}/validate`, { method: "POST", body: "{}" });

export const publishAmpRevision = (revisionId: string, expectedContentHash: string, approvalReference: string) =>
  request<TenantProgrammeRevision>(`/architecture/programmes/revisions/${encodeURIComponent(revisionId)}/publish`, {
    method: "POST",
    body: JSON.stringify({ expected_content_hash: expectedContentHash, approval_reference: approvalReference }),
  });
