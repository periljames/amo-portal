import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";

export type CompliancePortfolioView =
  | "reviews"
  | "external-sources"
  | "relationships"
  | "applicability"
  | "superseded-references";

export type CompliancePortfolioItem = {
  id: string;
  kind: "PERIODIC_REVIEW" | "EXTERNAL_SOURCE" | "RELATIONSHIP" | "APPLICABILITY" | "SUPERSEDED_REFERENCE";
  document: { id: string; code: string; title: string };
  status: string;
  target_path: string;
  revision_id?: string | null;
  due_at?: string | null;
  owner?: string | null;
  outcome?: string | null;
  provider?: string;
  authority?: string | null;
  update_method?: string;
  source_status?: string;
  last_checked_at?: string | null;
  next_check_due_at?: string | null;
  received_revision?: string | null;
  received_at?: string | null;
  currency_status?: string | null;
  applicability_status?: string | null;
  assessment_required?: boolean;
  relationship_type?: string;
  relationship_source?: string;
  target?: string;
  target_id?: string | null;
  page_number?: number | null;
  section_label?: string | null;
  confidence_percent?: number;
  exact_token?: string | null;
  rule_type?: string;
  target_type?: string;
  source?: string;
  effective_from?: string | null;
  effective_to?: string | null;
  referenced_document?: { id: string; code: string; title: string };
  referenced_revision_id?: string;
  current_revision_id?: string;
};

export type CompliancePortfolioResponse = {
  view: CompliancePortfolioView;
  items: CompliancePortfolioItem[];
  pagination: { page: number; per_page: number; total: number; returned: number };
  facets: Record<CompliancePortfolioView, number> & Record<string, number>;
  generated_at: string;
};

export type ExternalAssessmentContext = {
  source: {
    id: string;
    manual_id: string;
    provider: string;
    authority?: string | null;
    subscription_reference?: string | null;
    access_url?: string | null;
    status: string;
    last_checked_at?: string | null;
    next_check_due_at?: string | null;
  };
  received_revision?: {
    id: string;
    revision_label: string;
    publication_date?: string | null;
    received_at?: string | null;
    currency_status: string;
    applicability_status: string;
    checksum_sha256?: string | null;
    notes?: string | null;
    evidence: Array<Record<string, unknown>>;
  } | null;
  current_revision?: {
    id: string;
    revision_label: string;
    publication_date?: string | null;
    currency_status: string;
    applicability_status: string;
  } | null;
  affected_internal_documents: Array<{ id: string; code: string; title: string; document_class: string }>;
  assessment_required: boolean;
  work_item_status: "NEW_REVISION_REQUIRES_ASSESSMENT" | "ASSESSMENT_COMPLETE";
};

async function request<T>(url: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(authHeaders());
  if (init.body) headers.set("Content-Type", "application/json");
  const response = await fetch(url, { ...init, headers, credentials: "same-origin" });
  if (!response.ok) {
    let message = `The compliance request could not be completed (${response.status}).`;
    try {
      const payload = await response.json();
      message = typeof payload?.detail === "string" ? payload.detail : payload?.detail?.message || message;
    } catch {
      // Keep the operational fallback.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export async function getCompliancePortfolio(
  tenant: string,
  options: {
    view?: CompliancePortfolioView;
    q?: string;
    status?: string;
    page?: number;
    perPage?: number;
  } = {},
): Promise<CompliancePortfolioResponse> {
  const query = new URLSearchParams();
  if (options.view) query.set("view", options.view);
  if (options.q) query.set("q", options.q);
  if (options.status) query.set("status", options.status);
  if (options.page) query.set("page", String(options.page));
  if (options.perPage) query.set("per_page", String(options.perPage));

  return request<CompliancePortfolioResponse>(
    `${getApiBaseUrl()}/doc-control/workspace/t/${encodeURIComponent(tenant)}/compliance-portfolio?${query.toString()}`,
  );
}

export function getExternalAssessmentContext(tenant: string, sourceId: string): Promise<ExternalAssessmentContext> {
  return request(`${getApiBaseUrl()}/doc-control/workspace/t/${encodeURIComponent(tenant)}/external-sources/${encodeURIComponent(sourceId)}/assessment`);
}

export function assessExternalRevision(
  tenant: string,
  sourceId: string,
  payload: { receipt_id: string; applicability_status: "APPLICABLE" | "PARTIALLY_APPLICABLE" | "NOT_APPLICABLE"; notes: string },
): Promise<ExternalAssessmentContext> {
  return request(`${getApiBaseUrl()}/doc-control/workspace/t/${encodeURIComponent(tenant)}/external-sources/${encodeURIComponent(sourceId)}/assessment`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
