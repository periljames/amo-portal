import { authHeaders } from "./auth";
import { apiGet, apiPost } from "./crs";

export type Watchlist = {
  id: number;
  name: string;
  status: string;
  criteria_json: Record<string, any>;
  run_count: number;
  last_run_at?: string | null;
  next_run_at?: string | null;
};

export const getPlanningDashboard = () => apiGet<any>("/records/planning/dashboard", { headers: authHeaders() });
export const getProductionDashboard = () => apiGet<any>("/records/production/dashboard", { headers: authHeaders() });

export const listWatchlists = () => apiGet<Watchlist[]>("/records/watchlists", { headers: authHeaders() });
export const createWatchlist = (payload: Partial<Watchlist> & { name: string; criteria_json: Record<string, any> }) =>
  apiPost<Watchlist>("/records/watchlists", payload, { headers: authHeaders() });
export const runWatchlist = (id: number) => apiPost<any>(`/records/watchlists/${id}/run`, {}, { headers: authHeaders() });

export const listPublicationReview = () => apiGet<any[]>("/records/publications/review", { headers: authHeaders() });
export const decidePublicationReview = (matchId: number, payload: any) =>
  apiPost<any>(`/records/publications/review/${matchId}/decision`, payload, { headers: authHeaders() });

export const listComplianceActions = () => apiGet<any[]>("/records/compliance-actions", { headers: authHeaders() });
export const createComplianceAction = (payload: any) => apiPost<any>("/records/compliance-actions", payload, { headers: authHeaders() });
export const updateComplianceActionStatus = (id: number, payload: any) =>
  apiPost<any>(`/records/compliance-actions/${id}/status`, payload, { headers: authHeaders() });
