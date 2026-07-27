import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";

export type DocumentControlCapabilities = {
  read: boolean;
  control: boolean;
  approve: boolean;
};

export type DocumentControlMetrics = {
  document_records: number;
  revision_records: number;
  draft_revisions: number;
  effective_publications: number;
  open_change_requests: number;
  active_workflows: number;
  authority_pending: number;
  temporary_revisions_in_force: number;
  temporary_revisions_expiring_30_days: number;
  pending_acknowledgements: number;
  overdue_acknowledgements: number;
  reviews_due_60_days: number;
  external_currency_checks_due: number;
  issued_controlled_copies: number;
};

export type DocumentControlDashboard = {
  default_workspace: "CONTROL_DESK" | "LIBRARY";
  capabilities: DocumentControlCapabilities;
  metrics: DocumentControlMetrics;
  recent_activity: Array<{
    id: string;
    action: string;
    entity_type: string;
    entity_id: string;
    actor_id?: string | null;
    at?: string | null;
    diff?: Record<string, unknown>;
  }>;
};

export type DocumentControlProfile = {
  id: string | null;
  manual_id: string;
  document_class: "INTERNAL" | "EXTERNAL" | "RECORD";
  owner_department: string;
  owner_user_id?: string | null;
  language: string;
  criticality: "STANDARD" | "IMPORTANT" | "CRITICAL";
  regulated_flag: boolean;
  restricted_flag: boolean;
  requires_authority_approval: boolean;
  acknowledgement_required: boolean;
  review_interval_months: number;
  next_review_due?: string | null;
  access_scope: Record<string, unknown>;
  tags: string[];
  metadata: Record<string, unknown>;
  version: number;
};

export type DocumentRevisionSummary = {
  id: string;
  manual_id: string;
  issue_number?: string | null;
  revision_number: string;
  status: string;
  effective_date?: string | null;
  created_at?: string | null;
  published_at?: string | null;
  immutable: boolean;
  source_type?: string | null;
  source_filename?: string | null;
  source_page_count?: number | null;
  source_sha256?: string | null;
  requires_authority_approval: boolean;
  authority_approval_ref?: string | null;
};

export type DocumentReadTarget = {
  revision_id?: string | null;
  kind: "PUBLISHED" | "UNCONTROLLED" | "NONE";
  label: string;
  uncontrolled: boolean;
};

export type DocumentLibraryItem = {
  id: string;
  code: string;
  title: string;
  manual_type: string;
  owner_role: string;
  status: string;
  current_published_revision_id?: string | null;
  profile: DocumentControlProfile;
  latest_revision?: DocumentRevisionSummary | null;
  read_target: DocumentReadTarget;
  workflow?: DocumentWorkflow | null;
  open_change_requests: number;
  pending_acknowledgements: number;
};

export type DocumentLibraryResponse = {
  items: DocumentLibraryItem[];
  pagination: {
    page: number;
    per_page: number;
    total: number;
    returned: number;
  };
};

export type DocumentWorkflowBlocker = {
  code: string;
  message: string;
};

export type DocumentWorkflowDecision = {
  id: string;
  step_code: string;
  decision: string;
  actor_user_id?: string | null;
  from_state: string;
  to_state: string;
  comments?: string | null;
  evidence: Array<Record<string, unknown>>;
  created_at?: string | null;
};

export type DocumentWorkflow = {
  id: string;
  manual_id: string;
  revision_id: string;
  state: string;
  requires_authority: boolean;
  training_impact_required: boolean;
  training_readiness_status: string;
  qms_readiness_status: string;
  distribution_readiness_status: string;
  effective_at?: string | null;
  version: number;
  created_at?: string | null;
  updated_at?: string | null;
  blockers?: DocumentWorkflowBlocker[];
  decisions?: DocumentWorkflowDecision[];
};

export type DocumentChangeRequest = {
  id: string;
  manual_id: string;
  revision_id?: string | null;
  source_module: string;
  source_entity_type?: string | null;
  source_entity_id?: string | null;
  title: string;
  description: string;
  priority: string;
  status: string;
  proposer?: PersonSummary | null;
  owner?: PersonSummary | null;
  due_at?: string | null;
  impact: Record<string, unknown>;
  training_impact_required: boolean;
  qms_blocking: boolean;
  resolution?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  closed_at?: string | null;
};

export type PersonSummary = {
  id: string;
  name: string;
  email: string;
  role: string;
  department?: string | null;
  active: boolean;
};

export type AuthoritySubmission = {
  id: string;
  manual_id: string;
  revision_id: string;
  workflow_id?: string | null;
  authority_name: string;
  submission_reference: string;
  status: string;
  submitted_at?: string | null;
  submitted_by_user_id?: string | null;
  response_due_at?: string | null;
  approved_at?: string | null;
  response_summary?: string | null;
  evidence: Array<Record<string, unknown>>;
  created_at?: string | null;
  updated_at?: string | null;
};

export type TemporaryRevision = {
  id: string;
  manual_id: string;
  base_revision_id: string;
  revision_id?: string | null;
  tr_number: string;
  title: string;
  reason: string;
  affected_sections: Array<Record<string, unknown>>;
  filing_instructions?: string | null;
  effective_date: string;
  expiry_date: string;
  status: string;
  approval_status: string;
  distribution_campaign_id?: string | null;
  incorporated_revision_id?: string | null;
  created_by_user_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type DistributionCampaign = {
  id: string;
  manual_id: string;
  revision_id: string;
  temporary_revision_id?: string | null;
  title: string;
  audience: Record<string, unknown>;
  acknowledgement_required: boolean;
  due_at?: string | null;
  status: string;
  issued_at?: string | null;
  issued_by_user_id?: string | null;
  metadata: Record<string, unknown>;
  recipients: Record<string, number>;
  created_at?: string | null;
  updated_at?: string | null;
};

export type DocumentReviewPlan = {
  id: string;
  manual_id: string;
  revision_id?: string | null;
  owner_user_id?: string | null;
  due_at: string;
  status: string;
  outcome?: string | null;
  findings: Array<Record<string, unknown>>;
  actions: Array<Record<string, unknown>>;
  completed_at?: string | null;
  completed_by_user_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type ControlledCopy = {
  id: string;
  manual_id: string;
  revision_id: string;
  copy_number: string;
  format: string;
  holder_user_id?: string | null;
  holder_name?: string | null;
  location_text: string;
  status: string;
  issued_at?: string | null;
  issued_by_user_id?: string | null;
  due_back_at?: string | null;
  withdrawn_at?: string | null;
  metadata: Record<string, unknown>;
};

export type ExternalSource = {
  id: string;
  manual_id: string;
  provider: string;
  authority?: string | null;
  subscription_reference?: string | null;
  access_url?: string | null;
  update_method: string;
  status: string;
  last_checked_at?: string | null;
  next_check_due_at?: string | null;
  metadata: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
};

export type ApplicabilityRule = {
  id: string;
  manual_id: string;
  revision_id?: string | null;
  rule_type: string;
  target_type: string;
  target_id?: string | null;
  target_value?: string | null;
  effective_from?: string | null;
  effective_to?: string | null;
  status: string;
  source: string;
  criteria: Record<string, unknown>;
  created_by_user_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type IntegrationLink = {
  id: string;
  manual_id: string;
  revision_id?: string | null;
  change_request_id?: string | null;
  workflow_id?: string | null;
  source_module: string;
  entity_type: string;
  entity_id: string;
  relation_type: string;
  blocking: boolean;
  status_snapshot?: string | null;
  metadata: Record<string, unknown>;
  created_by_user_id?: string | null;
  created_at?: string | null;
};

export type DocumentDetailResponse = {
  document: DocumentLibraryItem;
  revisions: DocumentRevisionSummary[];
  changes: DocumentChangeRequest[];
  workflows: DocumentWorkflow[];
  authority_submissions: AuthoritySubmission[];
  temporary_revisions: TemporaryRevision[];
  distribution_campaigns: DistributionCampaign[];
  reviews: DocumentReviewPlan[];
  controlled_copies: ControlledCopy[];
  external_sources: ExternalSource[];
  applicability: ApplicabilityRule[];
  integrations: IntegrationLink[];
  history: Array<{
    id: string;
    action: string;
    entity_type: string;
    entity_id: string;
    actor_id?: string | null;
    at?: string | null;
    diff?: Record<string, unknown>;
  }>;
  capabilities: { control: boolean };
};

export type ReadTargetResponse = {
  manual_id: string;
  revision_id: string;
  kind: "PUBLISHED" | "UNCONTROLLED";
  uncontrolled: boolean;
  reader_path: string;
  revision: DocumentRevisionSummary;
};

type QueryValue = string | number | boolean | undefined | null;

function workspacePath(tenantSlug: string, suffix: string): string {
  return `/doc-control/workspace/t/${encodeURIComponent(tenantSlug)}${suffix}`;
}

function buildQuery(values: Record<string, QueryValue>): string {
  const query = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  });
  const text = query.toString();
  return text ? `?${text}` : "";
}

async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(authHeaders());
  if (init.body !== undefined && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers,
    credentials: "same-origin",
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      const detail = payload?.detail;
      if (typeof detail === "string") message = detail;
      else if (detail?.message) message = String(detail.message);
      else if (detail) message = JSON.stringify(detail);
    } catch {
      // Keep HTTP fallback.
    }
    const error = new Error(message) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function getDocumentControlDashboard(tenantSlug: string): Promise<DocumentControlDashboard> {
  return apiRequest(workspacePath(tenantSlug, "/dashboard"));
}

export function listDocumentControlDocuments(
  tenantSlug: string,
  params: { q?: string; documentClass?: string; status?: string; page?: number; perPage?: number } = {},
): Promise<DocumentLibraryResponse> {
  return apiRequest(`${workspacePath(tenantSlug, "/documents")}${buildQuery({
    q: params.q,
    document_class: params.documentClass,
    status: params.status,
    page: params.page,
    per_page: params.perPage,
  })}`);
}

export function getDocumentControlDocument(tenantSlug: string, manualId: string): Promise<DocumentDetailResponse> {
  return apiRequest(workspacePath(tenantSlug, `/documents/${encodeURIComponent(manualId)}`));
}

export function getDocumentReadTarget(tenantSlug: string, manualId: string): Promise<ReadTargetResponse> {
  return apiRequest(workspacePath(tenantSlug, `/documents/${encodeURIComponent(manualId)}/read-target`));
}

export function upsertDocumentProfile(
  tenantSlug: string,
  manualId: string,
  payload: Omit<DocumentControlProfile, "id" | "manual_id" | "version"> & { expected_version?: number },
): Promise<DocumentControlProfile> {
  return apiRequest(workspacePath(tenantSlug, `/documents/${encodeURIComponent(manualId)}/profile`), {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function listDocumentChangeRequests(
  tenantSlug: string,
  params: { status?: string; manualId?: string } = {},
): Promise<DocumentChangeRequest[]> {
  return apiRequest(`${workspacePath(tenantSlug, "/change-requests")}${buildQuery({ status: params.status, manual_id: params.manualId })}`);
}

export function createDocumentChangeRequest(
  tenantSlug: string,
  payload: Record<string, unknown>,
): Promise<DocumentChangeRequest> {
  return apiRequest(workspacePath(tenantSlug, "/change-requests"), { method: "POST", body: JSON.stringify(payload) });
}

export function updateDocumentChangeRequest(
  tenantSlug: string,
  changeId: string,
  payload: Record<string, unknown>,
): Promise<DocumentChangeRequest> {
  return apiRequest(workspacePath(tenantSlug, `/change-requests/${encodeURIComponent(changeId)}`), { method: "PATCH", body: JSON.stringify(payload) });
}

export function listDocumentWorkflows(
  tenantSlug: string,
  params: { state?: string; manualId?: string } = {},
): Promise<DocumentWorkflow[]> {
  return apiRequest(`${workspacePath(tenantSlug, "/workflows")}${buildQuery({ state: params.state, manual_id: params.manualId })}`);
}

export function createDocumentWorkflow(tenantSlug: string, payload: Record<string, unknown>): Promise<DocumentWorkflow> {
  return apiRequest(workspacePath(tenantSlug, "/workflows"), { method: "POST", body: JSON.stringify(payload) });
}

export function transitionDocumentWorkflow(
  tenantSlug: string,
  workflowId: string,
  payload: Record<string, unknown>,
): Promise<DocumentWorkflow> {
  return apiRequest(workspacePath(tenantSlug, `/workflows/${encodeURIComponent(workflowId)}/transition`), { method: "POST", body: JSON.stringify(payload) });
}

export function listAuthoritySubmissions(
  tenantSlug: string,
  params: { status?: string; manualId?: string } = {},
): Promise<AuthoritySubmission[]> {
  return apiRequest(`${workspacePath(tenantSlug, "/authority-submissions")}${buildQuery({ status: params.status, manual_id: params.manualId })}`);
}

export function createAuthoritySubmission(tenantSlug: string, payload: Record<string, unknown>): Promise<AuthoritySubmission> {
  return apiRequest(workspacePath(tenantSlug, "/authority-submissions"), { method: "POST", body: JSON.stringify(payload) });
}

export function updateAuthoritySubmission(
  tenantSlug: string,
  submissionId: string,
  payload: Record<string, unknown>,
): Promise<AuthoritySubmission> {
  return apiRequest(workspacePath(tenantSlug, `/authority-submissions/${encodeURIComponent(submissionId)}`), { method: "PATCH", body: JSON.stringify(payload) });
}

export function listTemporaryRevisions(
  tenantSlug: string,
  params: { status?: string; manualId?: string } = {},
): Promise<TemporaryRevision[]> {
  return apiRequest(`${workspacePath(tenantSlug, "/temporary-revisions")}${buildQuery({ status: params.status, manual_id: params.manualId })}`);
}

export function createTemporaryRevision(tenantSlug: string, payload: Record<string, unknown>): Promise<TemporaryRevision> {
  return apiRequest(workspacePath(tenantSlug, "/temporary-revisions"), { method: "POST", body: JSON.stringify(payload) });
}

export function transitionTemporaryRevision(
  tenantSlug: string,
  temporaryRevisionId: string,
  payload: Record<string, unknown>,
): Promise<TemporaryRevision> {
  return apiRequest(workspacePath(tenantSlug, `/temporary-revisions/${encodeURIComponent(temporaryRevisionId)}/transition`), { method: "POST", body: JSON.stringify(payload) });
}

export function listDistributionCampaigns(
  tenantSlug: string,
  params: { status?: string; manualId?: string } = {},
): Promise<DistributionCampaign[]> {
  return apiRequest(`${workspacePath(tenantSlug, "/distribution-campaigns")}${buildQuery({ status: params.status, manual_id: params.manualId })}`);
}

export function createDistributionCampaign(tenantSlug: string, payload: Record<string, unknown>): Promise<DistributionCampaign> {
  return apiRequest(workspacePath(tenantSlug, "/distribution-campaigns"), { method: "POST", body: JSON.stringify(payload) });
}

export function issueDistributionCampaign(
  tenantSlug: string,
  campaignId: string,
  payload: Record<string, unknown>,
): Promise<DistributionCampaign> {
  return apiRequest(workspacePath(tenantSlug, `/distribution-campaigns/${encodeURIComponent(campaignId)}/issue`), { method: "POST", body: JSON.stringify(payload) });
}

export function acknowledgeDistributionCampaign(
  tenantSlug: string,
  campaignId: string,
  payload: Record<string, unknown> = {},
): Promise<{ status: string; acknowledged_at?: string | null; campaign_status: string; remaining: number }> {
  return apiRequest(workspacePath(tenantSlug, `/distribution-campaigns/${encodeURIComponent(campaignId)}/acknowledge`), { method: "POST", body: JSON.stringify(payload) });
}

export function listDocumentReviews(
  tenantSlug: string,
  params: { status?: string; manualId?: string } = {},
): Promise<DocumentReviewPlan[]> {
  return apiRequest(`${workspacePath(tenantSlug, "/reviews")}${buildQuery({ status: params.status, manual_id: params.manualId })}`);
}

export function createDocumentReview(tenantSlug: string, payload: Record<string, unknown>): Promise<DocumentReviewPlan> {
  return apiRequest(workspacePath(tenantSlug, "/reviews"), { method: "POST", body: JSON.stringify(payload) });
}

export function completeDocumentReview(
  tenantSlug: string,
  reviewId: string,
  payload: Record<string, unknown>,
): Promise<DocumentReviewPlan> {
  return apiRequest(workspacePath(tenantSlug, `/reviews/${encodeURIComponent(reviewId)}/complete`), { method: "POST", body: JSON.stringify(payload) });
}

export function listControlledCopies(
  tenantSlug: string,
  params: { status?: string; manualId?: string } = {},
): Promise<ControlledCopy[]> {
  return apiRequest(`${workspacePath(tenantSlug, "/controlled-copies")}${buildQuery({ status: params.status, manual_id: params.manualId })}`);
}

export function createControlledCopy(tenantSlug: string, payload: Record<string, unknown>): Promise<ControlledCopy> {
  return apiRequest(workspacePath(tenantSlug, "/controlled-copies"), { method: "POST", body: JSON.stringify(payload) });
}

export function createControlledCopyEvent(
  tenantSlug: string,
  copyId: string,
  payload: Record<string, unknown>,
): Promise<ControlledCopy> {
  return apiRequest(workspacePath(tenantSlug, `/controlled-copies/${encodeURIComponent(copyId)}/events`), { method: "POST", body: JSON.stringify(payload) });
}

export function listExternalSources(tenantSlug: string, manualId?: string): Promise<ExternalSource[]> {
  return apiRequest(`${workspacePath(tenantSlug, "/external-sources")}${buildQuery({ manual_id: manualId })}`);
}

export function createExternalSource(tenantSlug: string, payload: Record<string, unknown>): Promise<ExternalSource> {
  return apiRequest(workspacePath(tenantSlug, "/external-sources"), { method: "POST", body: JSON.stringify(payload) });
}

export function createExternalRevisionReceipt(
  tenantSlug: string,
  sourceId: string,
  payload: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  return apiRequest(workspacePath(tenantSlug, `/external-sources/${encodeURIComponent(sourceId)}/receipts`), { method: "POST", body: JSON.stringify(payload) });
}

export function listApplicabilityRules(
  tenantSlug: string,
  params: { manualId?: string; targetType?: string; targetId?: string } = {},
): Promise<ApplicabilityRule[]> {
  return apiRequest(`${workspacePath(tenantSlug, "/applicability")}${buildQuery({ manual_id: params.manualId, target_type: params.targetType, target_id: params.targetId })}`);
}

export function createApplicabilityRule(tenantSlug: string, payload: Record<string, unknown>): Promise<ApplicabilityRule> {
  return apiRequest(workspacePath(tenantSlug, "/applicability"), { method: "POST", body: JSON.stringify(payload) });
}

export function listIntegrationLinks(
  tenantSlug: string,
  params: { manualId?: string; sourceModule?: string; entityType?: string; entityId?: string } = {},
): Promise<IntegrationLink[]> {
  return apiRequest(`${workspacePath(tenantSlug, "/integration-links")}${buildQuery({
    manual_id: params.manualId,
    source_module: params.sourceModule,
    entity_type: params.entityType,
    entity_id: params.entityId,
  })}`);
}

export function createIntegrationLink(tenantSlug: string, payload: Record<string, unknown>): Promise<IntegrationLink> {
  return apiRequest(workspacePath(tenantSlug, "/integration-links"), { method: "POST", body: JSON.stringify(payload) });
}

export function getMasterRegisterReport(tenantSlug: string): Promise<{ generated_at: string; tenant: string; items: Array<Record<string, unknown>> }> {
  return apiRequest(workspacePath(tenantSlug, "/reports/master-register"));
}

export function getOverdueDocumentControlReport(tenantSlug: string): Promise<Record<string, unknown>> {
  return apiRequest(workspacePath(tenantSlug, "/reports/overdue"));
}
