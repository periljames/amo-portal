import { authHeaders } from "./auth";
import { apiGet, apiPost, apiPostForm, apiPut } from "./crs";

export type DocumentationNodeType =
  | "ROOT"
  | "MANAGEMENT_SYSTEM"
  | "MANUAL"
  | "POLICY"
  | "PROCEDURE"
  | "WORK_INSTRUCTION"
  | "FORM"
  | "CHECKLIST"
  | "REGISTER"
  | "EXTERNAL_DOCUMENT"
  | "RECORD_SERIES";

export type DocumentationExecutionProfile = {
  id: string;
  manual_id: string;
  execution_type: "NONE" | "PDF_ACROFORM" | "CHECKLIST" | "PORTAL_FORM" | "DOWNLOADABLE_TEMPLATE" | "HYBRID";
  submission_mode: "DOWNLOAD_ONLY" | "FILL_AND_SUBMIT" | "DOWNLOAD_AND_UPLOAD" | "PORTAL_SUBMISSION";
  record_series_node_id?: string | null;
  retention_years?: number | null;
  naming_pattern: string;
  allow_download: boolean;
  allow_save_draft: boolean;
  requires_signature: boolean;
  requires_review: boolean;
  schema: Record<string, unknown>;
  access_scope: Record<string, unknown>;
  metadata: Record<string, unknown>;
  version: number;
};

export type DocumentationTreeNode = {
  id: string;
  parent_id?: string | null;
  node_type: DocumentationNodeType;
  code: string;
  title: string;
  path: string;
  depth: number;
  order_index: number;
  manual_id?: string | null;
  status: string;
  metadata: Record<string, unknown>;
  document?: {
    manual_type: string;
    status: string;
    current_published_revision_id?: string | null;
    latest_revision_id?: string | null;
    latest_revision?: string | null;
    source_type?: string | null;
  } | null;
  execution?: DocumentationExecutionProfile | null;
};

export type DocumentationTree = {
  tenant_id: string;
  root_id?: string | null;
  items: DocumentationTreeNode[];
  reference_health: Record<string, number>;
  capabilities: { read: boolean; control: boolean };
};

export type DocumentationConnection = {
  id: string;
  kind: "GOVERNED_RELATIONSHIP" | "DETECTED_REFERENCE";
  direction: "OUTGOING" | "INCOMING";
  relationship_type: string;
  relationship_source?: string | null;
  status: string;
  source_manual_id: string;
  target_manual_id?: string | null;
  related_node: DocumentationTreeNode;
  exact_token?: string | null;
  exact_quote?: string | null;
  raw_token?: string | null;
  page_number?: number | null;
  source_page_number?: number | null;
  section_label?: string | null;
  source_quote?: string | null;
  confidence_percent: number;
};

export type DocumentationAssociatedRecord = {
  id: string;
  record_number: string;
  status: string;
  artifact_filename: string;
  template_manual_id: string;
  template?: { code: string; title: string } | null;
  record_series_node_id?: string | null;
  submitted_by_user_id?: string | null;
  submitted_at?: string | null;
  retention_years?: number | null;
  download_url: string;
};

export type DocumentationNodeConnections = {
  tenant_id: string;
  node: DocumentationTreeNode;
  breadcrumbs: DocumentationTreeNode[];
  children: DocumentationTreeNode[];
  record_series?: DocumentationTreeNode | null;
  record_sources: DocumentationTreeNode[];
  workflow_nodes: DocumentationTreeNode[];
  governed_relationships: DocumentationConnection[];
  detected_references: DocumentationConnection[];
  records: {
    items: DocumentationAssociatedRecord[];
    total: number;
    scope: "ALL" | "OWN";
    limit: number;
  };
  capabilities: { read: boolean; control: boolean; records_scope: "ALL" | "OWN" };
};

export type DocumentationIndexState = {
  id?: string | null;
  manual_id?: string | null;
  revision_id?: string | null;
  source_sha256?: string | null;
  index_version?: number;
  status?: string | null;
  detected_count?: number;
  resolved_count?: number;
  unresolved_count?: number;
  broken_count?: number;
  error_summary?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
};

export type DocumentationReference = {
  id: string;
  raw_token: string;
  normalized_token: string;
  relationship_type: string;
  resolution_policy: string;
  status: string;
  confidence_percent: number;
  source: {
    manual_id: string;
    revision_id: string;
    section_id?: string | null;
    block_id?: string | null;
    page_number?: number | null;
    char_start?: number | null;
    char_end?: number | null;
    bbox?: { x?: number; y?: number; width?: number; height?: number };
    quote: string;
    context?: string | null;
  };
  target?: {
    manual_id: string;
    revision_id: string;
    code: string;
    title: string;
    manual_type: string;
    node_type?: DocumentationNodeType | null;
    hierarchy_path?: string | null;
    reader_url: string;
    pdf_url: string;
    execution?: DocumentationExecutionProfile | null;
  } | null;
  candidates: Array<{ manual_id: string; code: string; title: string }>;
};

export type PublicationReferencesResponse = {
  items: DocumentationReference[];
  index?: DocumentationIndexState | null;
};

export type LinkedResourceDetail = {
  reference: {
    id: string;
    raw_token: string;
    relationship_type: string;
    status: string;
    source_manual_id: string;
    source_revision_id: string;
    source_page_number?: number | null;
    source_context?: string | null;
    source_document?: { code: string; title: string } | null;
  };
  target: {
    manual_id: string;
    revision_id: string;
    code: string;
    title: string;
    manual_type: string;
    issue_number?: string | null;
    revision_number: string;
    effective_date?: string | null;
    status: string;
    immutable: boolean;
    source_type?: string | null;
    source_filename?: string | null;
    page_count?: number | null;
    reader_url: string;
    pdf_url: string;
    download_url: string;
    node?: { id: string; node_type: DocumentationNodeType; path: string } | null;
    execution?: DocumentationExecutionProfile | null;
  };
  capabilities: { download: boolean; execute: boolean; save_draft: boolean };
};

export type DocumentationRecord = {
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
  download_url: string;
};

function tenantPath(tenant: string): string {
  return encodeURIComponent(tenant.toLowerCase());
}

export async function getDocumentationTree(tenant: string): Promise<DocumentationTree> {
  return apiGet<DocumentationTree>(`/doc-control/workspace/t/${tenantPath(tenant)}/knowledge/tree`, { headers: authHeaders() });
}

export async function getDocumentationNodeConnections(
  tenant: string,
  nodeId: string,
): Promise<DocumentationNodeConnections> {
  return apiGet<DocumentationNodeConnections>(
    `/doc-control/workspace/t/${tenantPath(tenant)}/knowledge/nodes/${encodeURIComponent(nodeId)}/connections`,
    { headers: authHeaders() },
  );
}

export async function reconcileDocumentationTree(tenant: string): Promise<DocumentationTree> {
  return apiPost<DocumentationTree>(`/doc-control/workspace/t/${tenantPath(tenant)}/knowledge/reconcile`, undefined, { headers: authHeaders() });
}

export async function updateDocumentationNode(
  tenant: string,
  nodeId: string,
  payload: {
    parent_id?: string | null;
    node_type: DocumentationNodeType;
    code: string;
    title: string;
    order_index: number;
    aliases: string[];
    expected_updated_at?: string | null;
  },
): Promise<DocumentationTree> {
  return apiPut<DocumentationTree>(
    `/doc-control/workspace/t/${tenantPath(tenant)}/knowledge/nodes/${encodeURIComponent(nodeId)}`,
    JSON.stringify(payload),
    { headers: authHeaders({ "Content-Type": "application/json" }) },
  );
}

export async function updateDocumentationExecutionProfile(
  tenant: string,
  manualId: string,
  payload: Omit<DocumentationExecutionProfile, "id" | "manual_id"> & { expected_version?: number | null },
): Promise<DocumentationExecutionProfile> {
  return apiPut<DocumentationExecutionProfile>(
    `/doc-control/workspace/t/${tenantPath(tenant)}/knowledge/documents/${encodeURIComponent(manualId)}/execution-profile`,
    JSON.stringify(payload),
    { headers: authHeaders({ "Content-Type": "application/json" }) },
  );
}

export async function reindexDocumentationRevision(tenant: string, revisionId: string, wait = false): Promise<DocumentationIndexState> {
  return apiPost<DocumentationIndexState>(
    `/doc-control/workspace/t/${tenantPath(tenant)}/knowledge/revisions/${encodeURIComponent(revisionId)}/reindex?wait=${wait ? "true" : "false"}`,
    undefined,
    { headers: authHeaders() },
  );
}

export async function getPublicationReferences(
  tenant: string,
  manualId: string,
  revisionId: string,
  filters?: { page?: number; sectionId?: string },
): Promise<PublicationReferencesResponse> {
  const params = new URLSearchParams();
  if (filters?.page) params.set("page", String(filters.page));
  if (filters?.sectionId) params.set("section_id", filters.sectionId);
  const query = params.size ? `?${params.toString()}` : "";
  return apiGet<PublicationReferencesResponse>(
    `/manuals/t/${tenantPath(tenant)}/${encodeURIComponent(manualId)}/rev/${encodeURIComponent(revisionId)}/references${query}`,
    { headers: authHeaders() },
  );
}

export async function getLinkedResource(tenant: string, referenceId: string): Promise<LinkedResourceDetail> {
  return apiGet<LinkedResourceDetail>(
    `/manuals/t/${tenantPath(tenant)}/linked-resources/${encodeURIComponent(referenceId)}`,
    { headers: authHeaders() },
  );
}

export async function submitLinkedPdfResource(
  tenant: string,
  referenceId: string,
  artifact: File,
  payload: Record<string, unknown> = {},
): Promise<DocumentationRecord> {
  const body = new FormData();
  body.append("artifact", artifact);
  body.append("payload_json", JSON.stringify(payload));
  return apiPostForm<DocumentationRecord>(
    `/manuals/t/${tenantPath(tenant)}/linked-resources/${encodeURIComponent(referenceId)}/submit`,
    body,
    { headers: authHeaders() },
  );
}

export type ReferenceMonitorResponse = {
  items: Array<{
    id: string;
    raw_token: string;
    status: string;
    confidence_percent: number;
    relationship_type: string;
    source_manual: { id: string; code: string; title: string };
    source_revision_id: string;
    source_page_number?: number | null;
    source_context?: string | null;
    target_manual?: { id: string; code?: string | null; title?: string | null } | null;
    candidates: Array<{ manual_id: string; code: string; title: string }>;
    updated_at?: string | null;
  }>;
  jobs: DocumentationIndexState[];
};

export async function getReferenceMonitor(tenant: string, status?: string): Promise<ReferenceMonitorResponse> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return apiGet<ReferenceMonitorResponse>(
    `/doc-control/workspace/t/${tenantPath(tenant)}/knowledge/reference-monitor${query}`,
    { headers: authHeaders() },
  );
}

export async function resolveDocumentationReference(
  tenant: string,
  referenceId: string,
  payload: {
    target_manual_id: string;
    target_revision_id?: string | null;
    relationship_type: string;
    resolution_policy: "CURRENT_EFFECTIVE" | "PINNED_REVISION";
    comments: string;
  },
): Promise<{ id: string; status: string; target_manual_id: string; target_revision_id: string }> {
  return apiPost(
    `/doc-control/workspace/t/${tenantPath(tenant)}/knowledge/references/${encodeURIComponent(referenceId)}/resolve`,
    JSON.stringify(payload),
    { headers: authHeaders({ "Content-Type": "application/json" }) },
  );
}
