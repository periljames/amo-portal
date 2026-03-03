import { authHeaders } from "./auth";
import { apiGet, apiPost } from "./crs";

export type PlanningDashboardResponse = {
  summary: {
    due_soon: number;
    overdue: number;
    open_deferrals: number;
    open_watchlist_reviews: number;
    open_compliance_actions: number;
  };
  priority_items: Array<{
    type: string;
    ref: string;
    tail?: string | null;
    due?: string | null;
    status: string;
  }>;
};

export type ProductionDashboardResponse = {
  summary: {
    active_work_orders: number;
    overdue_tasks: number;
    awaiting_certification: number;
  };
  bottlenecks: Array<{
    name: string;
    count: number;
    route: string;
  }>;
};

export type Watchlist = {
  id: number;
  name: string;
  status: string;
  criteria_json: Record<string, unknown>;
  run_count: number;
  last_run_at?: string | null;
  next_run_at?: string | null;
};

export type WatchlistRunResult = {
  watchlist_id: number;
  publications_ingested: number;
  matches_created: number;
};

export type PublicationReviewRow = {
  match_id: number;
  watchlist_id: number;
  publication_id: number;
  authority: string;
  source: string;
  document_type: string;
  doc_number: string;
  title: string;
  effectivity_summary?: string | null;
  matched_fleet: string[];
  classification: string;
  review_status: string;
  ageing_days: number;
  assigned_reviewer_user_id?: string | null;
  published_date?: string | null;
};

export type ComplianceAction = {
  id: number;
  publication_match_id: number;
  decision: string;
  status: string;
  due_date?: string | null;
  package_ref?: string | null;
  work_order_ref?: string | null;
  notes?: string | null;
};

export const getPlanningDashboard = () =>
  apiGet<PlanningDashboardResponse>("/records/planning/dashboard", { headers: authHeaders() });
export const getProductionDashboard = () =>
  apiGet<ProductionDashboardResponse>("/records/production/dashboard", { headers: authHeaders() });

export const listWatchlists = () => apiGet<Watchlist[]>("/records/watchlists", { headers: authHeaders() });
export const createWatchlist = (payload: { name: string; criteria_json: Record<string, unknown>; status?: string }) =>
  apiPost<Watchlist>("/records/watchlists", payload, { headers: authHeaders() });
export const runWatchlist = (id: number) =>
  apiPost<WatchlistRunResult>(`/records/watchlists/${id}/run`, {}, { headers: authHeaders() });

export const listPublicationReview = () =>
  apiGet<PublicationReviewRow[]>("/records/publications/review", { headers: authHeaders() });
export const decidePublicationReview = (
  matchId: number,
  payload: { review_status: string; classification: string; review_notes?: string },
) => apiPost<PublicationReviewRow>(`/records/publications/review/${matchId}/decision`, payload, { headers: authHeaders() });

export const listComplianceActions = () =>
  apiGet<ComplianceAction[]>("/records/compliance-actions", { headers: authHeaders() });
export const createComplianceAction = (payload: { publication_match_id: number; decision: string; status?: string; due_date?: string; notes?: string }) =>
  apiPost<ComplianceAction>("/records/compliance-actions", payload, { headers: authHeaders() });
export const updateComplianceActionStatus = (id: number, payload: { status: string; event_notes?: string }) =>
  apiPost<ComplianceAction>(`/records/compliance-actions/${id}/status`, payload, { headers: authHeaders() });
