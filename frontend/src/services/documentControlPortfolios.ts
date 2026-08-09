import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";

export type ChangesPortfolioView =
  | "my-changes"
  | "requests"
  | "draft"
  | "in-review"
  | "awaiting-quality"
  | "awaiting-management"
  | "authority"
  | "temporary-revisions"
  | "ready-for-release"
  | "closed";

export type ChangesPortfolioItem = {
  id: string;
  kind: "CHANGE_REQUEST" | "WORKFLOW" | "AUTHORITY_SUBMISSION" | "TEMPORARY_REVISION";
  document: { id: string; code: string; title: string };
  revision_id?: string | null;
  title: string;
  subtitle?: string | null;
  status: string;
  priority: string;
  due_at?: string | null;
  updated_at?: string | null;
  source: string;
  target_path: string;
  requires_authority?: boolean;
  training_impact_required?: boolean;
  qms_blocking?: boolean;
};

export type ChangesPortfolioResponse = {
  view: ChangesPortfolioView;
  items: ChangesPortfolioItem[];
  pagination: {
    page: number;
    per_page: number;
    total: number;
    returned: number;
  };
  facets: Record<ChangesPortfolioView, number> & Record<string, number>;
  generated_at: string;
};

export async function getChangesPortfolio(
  tenant: string,
  options: {
    view?: ChangesPortfolioView;
    q?: string;
    status?: string;
    page?: number;
    perPage?: number;
  } = {},
): Promise<ChangesPortfolioResponse> {
  const query = new URLSearchParams();
  if (options.view) query.set("view", options.view);
  if (options.q) query.set("q", options.q);
  if (options.status) query.set("status", options.status);
  if (options.page) query.set("page", String(options.page));
  if (options.perPage) query.set("per_page", String(options.perPage));

  const response = await fetch(
    `${getApiBaseUrl()}/doc-control/workspace/t/${encodeURIComponent(tenant)}/changes-portfolio?${query.toString()}`,
    { headers: authHeaders(), credentials: "same-origin" },
  );
  if (!response.ok) {
    let message = `The changes portfolio could not be loaded (${response.status}).`;
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
  return response.json() as Promise<ChangesPortfolioResponse>;
}
