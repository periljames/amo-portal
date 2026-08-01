import { authHeaders } from "./auth";
import { apiGet, apiPost } from "./crs";

export type EnterpriseRecordDocumentLink = {
  link_id?: string | null;
  manual_id: string;
  document_code?: string | null;
  document_title?: string | null;
  revision_id?: string | null;
  relation_type: string;
  blocking: boolean;
};

export type EnterpriseRecord = {
  canonical_id: string;
  record_kind: "MODULE_RECORD" | "GENERATED_RECORD";
  source_module: string;
  record_type: string;
  source_record_id: string;
  reference: string;
  title: string;
  summary?: string | null;
  status: string;
  sync_state: "CURRENT" | "CHANGED" | "MISSING" | "ERROR" | string;
  sync_message?: string | null;
  source_table?: string | null;
  source_route?: string | null;
  source_updated_at?: string | null;
  last_verified_at?: string | null;
  owner_user_id?: string | null;
  blocking: boolean;
  required_state?: string | null;
  required_state_satisfied: boolean;
  requires_attention: boolean;
  linked_documents: EnterpriseRecordDocumentLink[];
  link_count: number;
  relation_types: string[];
  generated_record_id?: string | null;
  download_url?: string | null;
};

export type EnterpriseRecordsHealth = {
  canonical_records: number;
  module_records: number;
  generated_records: number;
  current: number;
  changed: number;
  missing: number;
  errors: number;
  attention_required: number;
  linked_to_multiple_documents: number;
};

export type EnterpriseRecordsResponse = {
  items: EnterpriseRecord[];
  health: EnterpriseRecordsHealth;
  filters: {
    source_modules: string[];
    record_types: string[];
  };
  pagination: {
    page: number;
    per_page: number;
    total: number;
    returned: number;
  };
  capabilities: {
    refresh: boolean;
    review_generated_records: boolean;
    control: boolean;
  };
};

export type EnterpriseRecordRefreshResponse = {
  canonical_sources_considered: number;
  refreshed: number;
  changed_links: number;
  missing: number;
  errors: number;
};

function tenantPath(tenant: string): string {
  return encodeURIComponent(tenant.toLowerCase());
}

export async function getEnterpriseRecords(
  tenant: string,
  filters: {
    sourceModule?: string;
    recordType?: string;
    status?: string;
    syncState?: string;
    query?: string;
    page?: number;
    perPage?: number;
  } = {},
): Promise<EnterpriseRecordsResponse> {
  const params = new URLSearchParams();
  if (filters.sourceModule) params.set("source_module", filters.sourceModule);
  if (filters.recordType) params.set("record_type", filters.recordType);
  if (filters.status) params.set("status", filters.status);
  if (filters.syncState) params.set("sync_state", filters.syncState);
  if (filters.query?.trim()) params.set("query", filters.query.trim());
  params.set("page", String(filters.page || 1));
  params.set("per_page", String(filters.perPage || 75));
  return apiGet<EnterpriseRecordsResponse>(
    `/doc-control/workspace/t/${tenantPath(tenant)}/enterprise-records?${params.toString()}`,
    { headers: authHeaders() },
  );
}

export async function refreshEnterpriseRecords(
  tenant: string,
  payload: { source_module?: string; canonical_ids?: string[] } = {},
): Promise<EnterpriseRecordRefreshResponse> {
  return apiPost<EnterpriseRecordRefreshResponse>(
    `/doc-control/workspace/t/${tenantPath(tenant)}/enterprise-records/refresh`,
    JSON.stringify({
      source_module: payload.source_module || null,
      canonical_ids: payload.canonical_ids || [],
    }),
    { headers: authHeaders({ "Content-Type": "application/json" }) },
  );
}
