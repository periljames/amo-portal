import { apiRequest } from "./api";

export type ReportRevision = {
  id?: string | null;
  issue_number?: string | null;
  revision_number?: string | null;
  status?: string | null;
  effective_date?: string | null;
};

export type ReportsPortfolioItem = {
  manual_id: string;
  code: string;
  title: string;
  manual_type: string;
  lifecycle_status: string;
  document_class: string;
  owner_department: string;
  regulated: boolean;
  restricted: boolean;
  latest_revision: ReportRevision | null;
  effective_revision: ReportRevision | null;
  next_review_due: string | null;
};

export type ReportsPortfolioResponse = {
  generated_at: string;
  tenant: string;
  summary: {
    acknowledgements: number;
    periodic_reviews: number;
    external_currency: number;
    controlled_copy_returns: number;
    document_reviews: number;
  };
  items: ReportsPortfolioItem[];
  pagination: {
    page: number;
    per_page: number;
    total: number;
    returned: number;
  };
};

function buildQuery(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") search.set(key, String(value));
  });
  const value = search.toString();
  return value ? `?${value}` : "";
}

export function getReportsPortfolio(
  tenant: string,
  params: {
    q?: string;
    documentClass?: string;
    lifecycleStatus?: string;
    page?: number;
    perPage?: number;
  } = {},
): Promise<ReportsPortfolioResponse> {
  const query = buildQuery({
    q: params.q,
    document_class: params.documentClass,
    lifecycle_status: params.lifecycleStatus,
    page: params.page,
    per_page: params.perPage,
  });
  return apiRequest(`/doc-control/workspace/t/${encodeURIComponent(tenant)}/reports-portfolio${query}`);
}
