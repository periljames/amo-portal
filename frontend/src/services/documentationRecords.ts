import { authHeaders } from "./auth";
import { apiGet, apiPost } from "./crs";

export type GeneratedDocumentationRecord = {
  id: string;
  record_number: string;
  template_manual_id: string;
  template_revision_id: string;
  source_reference_id?: string | null;
  record_series_node_id?: string | null;
  artifact_filename: string;
  artifact_sha256: string;
  status: string;
  retention_years?: number | null;
  submitted_by_user_id?: string | null;
  submitted_at?: string | null;
  reviewed_by_user_id?: string | null;
  reviewed_at?: string | null;
  download_url: string;
  template?: { code: string; title: string; manual_type: string } | null;
  template_revision?: { issue_number?: string | null; revision_number: string; effective_date?: string | null } | null;
  record_series?: { id: string; code: string; title: string; path: string } | null;
  source_context?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  integrity?: {
    status: "VERIFIED" | "MISSING" | "MISMATCH";
    expected_sha256: string;
    actual_sha256?: string | null;
    size_bytes?: number;
  };
  capabilities?: { review: boolean; control: boolean };
};

export type GeneratedDocumentationRecordsResponse = {
  items: GeneratedDocumentationRecord[];
  pagination: { page: number; per_page: number; total: number; returned: number };
  capabilities: { review: boolean; control: boolean };
};

function tenantPath(tenant: string): string {
  return encodeURIComponent(tenant.toLowerCase());
}

export async function getGeneratedDocumentationRecords(
  tenant: string,
  filters: {
    seriesId?: string;
    templateManualId?: string;
    status?: string;
    submittedByUserId?: string;
    page?: number;
    perPage?: number;
  } = {},
): Promise<GeneratedDocumentationRecordsResponse> {
  const params = new URLSearchParams();
  if (filters.seriesId) params.set("series_id", filters.seriesId);
  if (filters.templateManualId) params.set("template_manual_id", filters.templateManualId);
  if (filters.status) params.set("status", filters.status);
  if (filters.submittedByUserId) params.set("submitted_by_user_id", filters.submittedByUserId);
  params.set("page", String(filters.page || 1));
  params.set("per_page", String(filters.perPage || 50));
  return apiGet<GeneratedDocumentationRecordsResponse>(
    `/doc-control/workspace/t/${tenantPath(tenant)}/knowledge/records?${params.toString()}`,
    { headers: authHeaders() },
  );
}

export async function getGeneratedDocumentationRecord(
  tenant: string,
  recordId: string,
): Promise<GeneratedDocumentationRecord> {
  return apiGet<GeneratedDocumentationRecord>(
    `/doc-control/workspace/t/${tenantPath(tenant)}/knowledge/records/${encodeURIComponent(recordId)}`,
    { headers: authHeaders() },
  );
}

export async function reviewGeneratedDocumentationRecord(
  tenant: string,
  recordId: string,
  payload: {
    decision: "ACCEPT" | "RETURN";
    comments: string;
    evidence_references: string[];
  },
): Promise<{
  id: string;
  record_number: string;
  status: string;
  reviewed_by_user_id?: string | null;
  reviewed_at?: string | null;
  integrity: GeneratedDocumentationRecord["integrity"];
}> {
  return apiPost(
    `/doc-control/workspace/t/${tenantPath(tenant)}/knowledge/records/${encodeURIComponent(recordId)}/review`,
    JSON.stringify(payload),
    { headers: authHeaders({ "Content-Type": "application/json" }) },
  );
}
