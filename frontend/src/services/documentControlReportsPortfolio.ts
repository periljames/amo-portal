import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";

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

export type ReportRegisterView =
  | "revisions"
  | "lep"
  | "distribution"
  | "acknowledgements"
  | "controlled-copies"
  | "external-sources"
  | "review-due"
  | "temporary-revisions"
  | "authority"
  | "archive"
  | "change-history"
  | "retention";

export type ReportRegisterItem = {
  id: string;
  kind: string;
  document: { id: string; code: string; title: string; type: string };
  record: string;
  status?: string | null;
  owner?: string | null;
  date?: string | null;
  due_at?: string | null;
  context?: string | null;
  target_path: string;
  details: Record<string, unknown>;
};

export type ReportsRegisterResponse = {
  view: ReportRegisterView;
  generated_at: string;
  items: ReportRegisterItem[];
  pagination: {
    page: number;
    per_page: number;
    total: number;
    returned: number;
  };
};

async function readJson<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) {
    let message = `${fallback} (${response.status}).`;
    try {
      const payload = await response.json();
      message = typeof payload?.detail === "string"
        ? payload.detail
        : payload?.detail?.message || message;
    } catch {
      // Keep the operational fallback.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export async function getReportsPortfolio(
  tenant: string,
  options: {
    q?: string;
    documentClass?: string;
    lifecycleStatus?: string;
    page?: number;
    perPage?: number;
  } = {},
): Promise<ReportsPortfolioResponse> {
  const query = new URLSearchParams();
  if (options.q) query.set("q", options.q);
  if (options.documentClass) query.set("document_class", options.documentClass);
  if (options.lifecycleStatus) query.set("lifecycle_status", options.lifecycleStatus);
  if (options.page) query.set("page", String(options.page));
  if (options.perPage) query.set("per_page", String(options.perPage));

  const suffix = query.toString() ? `?${query.toString()}` : "";
  const response = await fetch(
    `${getApiBaseUrl()}/doc-control/workspace/t/${encodeURIComponent(tenant)}/reports-portfolio${suffix}`,
    { headers: authHeaders(), credentials: "same-origin" },
  );
  return readJson<ReportsPortfolioResponse>(response, "The Reports workspace could not be loaded");
}

export async function getReportsRegister(
  tenant: string,
  options: {
    view: ReportRegisterView;
    q?: string;
    status?: string;
    dateFrom?: string;
    dateTo?: string;
    page?: number;
    perPage?: number;
  },
): Promise<ReportsRegisterResponse> {
  const query = new URLSearchParams({ view: options.view });
  if (options.q) query.set("q", options.q);
  if (options.status) query.set("status", options.status);
  if (options.dateFrom) query.set("date_from", options.dateFrom);
  if (options.dateTo) query.set("date_to", options.dateTo);
  if (options.page) query.set("page", String(options.page));
  if (options.perPage) query.set("per_page", String(options.perPage));

  const response = await fetch(
    `${getApiBaseUrl()}/doc-control/workspace/t/${encodeURIComponent(tenant)}/reports-register?${query.toString()}`,
    { headers: authHeaders(), credentials: "same-origin" },
  );
  return readJson<ReportsRegisterResponse>(response, "The selected evidence register could not be loaded");
}
