import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";

export type GovernanceAssignee = { id?: string | null; name: string; code?: string; email?: string; role?: string };
export type ResponsibilityAssignment = {
  id: string;
  manual_id: string;
  revision_id?: string | null;
  responsibility_type: string;
  assignee_type: "USER" | "DEPARTMENT" | "ORG_UNIT" | "ROLE";
  assignee: GovernanceAssignee;
  is_primary: boolean;
  delegated_from_id?: string | null;
  effective_from: string;
  effective_to?: string | null;
  assignment_source: string;
  confidence_percent: number;
  confirmation_status: string;
  provenance: Record<string, unknown>;
  confirmed_by_user_id?: string | null;
  confirmed_at?: string | null;
};

export type GovernanceRelationship = {
  id: string;
  source_manual_id: string;
  source_revision_id?: string | null;
  source_location_id?: string | null;
  target_entity_type: string;
  target_entity_id?: string | null;
  target_manual?: { id: string; code: string; title: string } | null;
  target_revision_id?: string | null;
  relationship_type: string;
  relationship_source: string;
  exact_token?: string | null;
  exact_quote?: string | null;
  page_number?: number | null;
  section_label?: string | null;
  confidence_percent: number;
  resolution_status: string;
  provenance: Record<string, unknown>;
};

export type DetectedReference = {
  id: string;
  raw_token: string;
  normalized_token: string;
  relationship_type: string;
  status: string;
  confidence_percent: number;
  detection_method: string;
  source_revision_id: string;
  source_page_number?: number | null;
  source_quote: string;
  source_context?: string | null;
  target_manual?: { id: string; code: string; title: string } | null;
  target_revision_id?: string | null;
  candidates: Array<Record<string, unknown>>;
};

export type GovernanceStructure = {
  id: string;
  parent_id?: string | null;
  parent?: { id: string; code: string; title: string; node_type: string } | null;
  code: string;
  title: string;
  node_type: string;
  path: string;
  depth: number;
  order_index: number;
  status: string;
  provenance: Record<string, unknown>;
  children: Array<{ id: string; code: string; title: string; node_type: string; status: string }>;
};

export type GovernanceDocument = {
  id: string;
  code: string;
  title: string;
  manual_type: string;
  status: string;
  profile: {
    document_class: string;
    owner_department: string;
    language: string;
    regulated_flag: boolean;
    restricted_flag: boolean;
    next_review_due?: string | null;
  };
  latest_revision?: {
    id: string;
    issue_number?: string | null;
    revision_number: string;
    status: string;
    effective_date?: string | null;
    source_type?: string | null;
    source_sha256?: string | null;
  } | null;
  read_target: { revision_id?: string | null; label: string; kind: string; uncontrolled: boolean };
};

export type GovernanceDetail = {
  document: GovernanceDocument;
  revisions: Array<Record<string, unknown>>;
  responsibilities: ResponsibilityAssignment[];
  effective_responsibilities: Record<string, ResponsibilityAssignment[]>;
  structure?: GovernanceStructure | null;
  relationships: GovernanceRelationship[];
  detected_references: DetectedReference[];
  index_jobs: Array<{ id: string; status: string; detected_count: number; resolved_count: number; unresolved_count: number; broken_count: number; error_summary?: string | null; updated_at?: string | null }>;
  assignment_options: {
    users: Array<{ id: string; name: string; email: string }>;
    departments: Array<{ id: string; code: string; name: string }>;
    org_units: Array<{ id: string; code: string; name: string; unit_type: string }>;
  };
  annotations: Array<Record<string, unknown>>;
  issues: Array<{ code: string; severity: string; count: number; items?: string[] }>;
  completeness: {
    missing_responsibilities: string[];
    unresolved_responsibilities: number;
    unresolved_relationships: number;
    structure_complete: boolean;
    indexing_status: string;
  };
  capabilities: { control: boolean; annotate: boolean; controlled_evidence: boolean };
};

export type GovernanceLibraryItem = {
  id: string;
  code: string;
  title: string;
  document_type: string;
  lifecycle_status: string;
  control_status: string;
  issue_number?: string | null;
  revision_number?: string | null;
  effective_date?: string | null;
  source_format?: string | null;
  owner?: ResponsibilityAssignment | null;
  responsible_department?: ResponsibilityAssignment | null;
  unresolved_ownership: number;
  unresolved_relationships: number;
  indexing_status: string;
  structure_path?: string | null;
  superseded: boolean;
};

export type GovernanceLibraryResponse = {
  items: GovernanceLibraryItem[];
  pagination: { page: number; per_page: number; total: number; returned: number };
};

export type GovernanceDashboard = {
  metrics: Record<string, number>;
  queues: Array<{ id: string; label: string; count: number; filter: Record<string, string> }>;
  capabilities: { control: boolean };
};

type QueryValue = string | number | boolean | undefined | null;

function path(tenant: string, suffix: string): string {
  return `/doc-control/workspace/t/${encodeURIComponent(tenant)}${suffix}`;
}

function query(values: Record<string, QueryValue>): string {
  const result = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "" && value !== false) result.set(key, String(value));
  });
  const text = result.toString();
  return text ? `?${text}` : "";
}

async function request<T>(url: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(authHeaders());
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(`${getApiBaseUrl()}${url}`, { ...init, headers, credentials: "same-origin" });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      message = typeof payload?.detail === "string" ? payload.detail : payload?.detail?.message || JSON.stringify(payload?.detail || payload);
    } catch {
      // Preserve HTTP fallback.
    }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function getGovernanceDashboard(tenant: string): Promise<GovernanceDashboard> {
  return request(path(tenant, "/governance/dashboard"));
}

export function listGovernanceDocuments(tenant: string, values: Record<string, QueryValue>): Promise<GovernanceLibraryResponse> {
  return request(`${path(tenant, "/governance/library")}${query(values)}`);
}

export function getDocumentGovernance(tenant: string, manualId: string): Promise<GovernanceDetail> {
  return request(path(tenant, `/documents/${encodeURIComponent(manualId)}/governance`));
}

export function createResponsibility(tenant: string, manualId: string, payload: Record<string, unknown>): Promise<ResponsibilityAssignment> {
  return request(path(tenant, `/documents/${encodeURIComponent(manualId)}/responsibilities`), {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function decideResponsibility(tenant: string, assignmentId: string, decision: "CONFIRMED" | "REJECTED", comments: string): Promise<ResponsibilityAssignment> {
  return request(path(tenant, `/responsibilities/${encodeURIComponent(assignmentId)}/decision`), {
    method: "PATCH",
    body: JSON.stringify({ decision, comments }),
  });
}

export function decideRelationship(tenant: string, relationshipId: string, decision: "CONFIRMED" | "REJECTED", comments: string): Promise<GovernanceRelationship> {
  return request(path(tenant, `/relationships/${encodeURIComponent(relationshipId)}/decision`), {
    method: "PATCH",
    body: JSON.stringify({ decision, comments }),
  });
}

export function decideDetectedReference(tenant: string, referenceId: string, decision: "CONFIRMED" | "REJECTED", comments: string): Promise<Record<string, unknown>> {
  return request(path(tenant, `/governance/references/${encodeURIComponent(referenceId)}/decision`), {
    method: "PATCH",
    body: JSON.stringify({ decision, comments }),
  });
}

export function reindexGovernedRevision(tenant: string, revisionId: string): Promise<Record<string, unknown>> {
  return request(path(tenant, `/knowledge/revisions/${encodeURIComponent(revisionId)}/reindex`), { method: "POST" });
}

export function startGovernanceBackfill(tenant: string, dryRun: boolean): Promise<Record<string, unknown>> {
  const key = `ui:${dryRun ? "dry-run" : "execute"}:${new Date().toISOString().slice(0, 13)}`;
  return request(path(tenant, "/governance/backfill"), {
    method: "POST",
    body: JSON.stringify({ idempotency_key: key, dry_run: dryRun, batch_limit: 50, retry_failed: true, reconcile_hierarchy: true }),
  });
}
