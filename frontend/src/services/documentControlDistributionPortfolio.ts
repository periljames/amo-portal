import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";

export type DistributionPortfolioView =
  | "campaigns"
  | "pending-acknowledgements"
  | "overdue-acknowledgements"
  | "physical-copies"
  | "recalls";

export type DistributionCampaignPortfolioItem = {
  id: string;
  kind: "CAMPAIGN";
  document: { id: string; code: string; title: string };
  revision_id: string;
  title: string;
  status: string;
  due_at?: string | null;
  issued_at?: string | null;
  acknowledgement_required: boolean;
  recipients: { total: number; acknowledged: number; pending: number; overdue: number };
  target_path: string;
};

export type DistributionAcknowledgementPortfolioItem = {
  id: string;
  kind: "ACKNOWLEDGEMENT";
  document: { id: string; code: string; title: string };
  revision_id: string;
  campaign_id: string;
  title: string;
  status: string;
  due_at?: string | null;
  notified_at?: string | null;
  recipient: { id?: string | null; name: string };
  reminder_count: number;
  target_path: string;
};

export type ControlledCopyPortfolioItem = {
  id: string;
  kind: "CONTROLLED_COPY";
  document: { id: string; code: string; title: string };
  revision_id: string;
  copy_number: string;
  format: string;
  status: string;
  custody_status: string;
  holder?: string | null;
  location: string;
  due_at?: string | null;
  issued_at?: string | null;
  target_path: string;
};

export type DistributionPortfolioItem =
  | DistributionCampaignPortfolioItem
  | DistributionAcknowledgementPortfolioItem
  | ControlledCopyPortfolioItem;

export type DistributionPortfolioResponse = {
  view: DistributionPortfolioView;
  items: DistributionPortfolioItem[];
  pagination: { page: number; per_page: number; total: number; returned: number };
  facets: Record<DistributionPortfolioView, number> & Record<string, number>;
  generated_at: string;
};

export async function getDistributionPortfolio(
  tenant: string,
  options: {
    view?: DistributionPortfolioView;
    q?: string;
    status?: string;
    page?: number;
    perPage?: number;
  } = {},
): Promise<DistributionPortfolioResponse> {
  const query = new URLSearchParams();
  if (options.view) query.set("view", options.view);
  if (options.q) query.set("q", options.q);
  if (options.status) query.set("status", options.status);
  if (options.page) query.set("page", String(options.page));
  if (options.perPage) query.set("per_page", String(options.perPage));

  const response = await fetch(
    `${getApiBaseUrl()}/doc-control/workspace/t/${encodeURIComponent(tenant)}/distribution-portfolio?${query.toString()}`,
    { headers: authHeaders(), credentials: "same-origin" },
  );
  if (!response.ok) {
    let message = `The distribution workspace could not be loaded (${response.status}).`;
    try {
      const payload = await response.json();
      message = typeof payload?.detail === "string" ? payload.detail : payload?.detail?.message || message;
    } catch {
      // Keep the operational fallback.
    }
    throw new Error(message);
  }
  return response.json() as Promise<DistributionPortfolioResponse>;
}
