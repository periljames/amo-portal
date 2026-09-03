import { apiRequest } from "./apiClient";
import type { CAROut, CARProgram, CARStatus, QMSAuditRegisterRowOut } from "./qms";

export type QmsAuditRegisterPage = {
  rows: QMSAuditRegisterRowOut[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
  car_linked_findings: number;
  open_car_count: number;
};

export type QmsAuditRegisterPageParams = {
  domain?: string;
  auditId?: string;
  findingId?: string;
  onlyWithCars?: boolean;
  workflowStage?: "needs_review" | "with_auditee" | "implementation" | "effectiveness" | "closed";
  search?: string;
  ref?: string;
  finding?: string;
  audit?: string;
  findingType?: string;
  owner?: string;
  car?: string;
  limit?: number;
  offset?: number;
  signal?: AbortSignal;
};

export type QmsCarRegisterScope =
  | "all"
  | "active"
  | "overdue"
  | "due_soon"
  | "awaiting_auditee"
  | "awaiting_quality_review"
  | "awaiting_effectiveness_review"
  | "closed";

export type QmsCarRegisterPage = {
  items: CAROut[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
  summary: {
    total: number;
    open: number;
    overdue: number;
    in_review: number;
  };
};

export type QmsCarRegisterPageParams = {
  program?: CARProgram;
  status?: CARStatus;
  scope?: QmsCarRegisterScope;
  carId?: string;
  assignedToUserId?: string;
  auditId?: string;
  search?: string;
  dueSoonDays?: number;
  limit?: number;
  offset?: number;
  signal?: AbortSignal;
};

function setIfPresent(query: URLSearchParams, key: string, value: string | undefined): void {
  const clean = value?.trim();
  if (clean) query.set(key, clean);
}

export function qmsGetAuditRegisterPage(params: QmsAuditRegisterPageParams = {}): Promise<QmsAuditRegisterPage> {
  const query = new URLSearchParams();
  setIfPresent(query, "domain", params.domain);
  setIfPresent(query, "audit_id", params.auditId);
  setIfPresent(query, "finding_id", params.findingId);
  setIfPresent(query, "workflow_stage", params.workflowStage);
  setIfPresent(query, "search", params.search);
  setIfPresent(query, "ref", params.ref);
  setIfPresent(query, "finding", params.finding);
  setIfPresent(query, "audit", params.audit);
  setIfPresent(query, "finding_type", params.findingType);
  setIfPresent(query, "owner", params.owner);
  setIfPresent(query, "car", params.car);
  if (params.onlyWithCars) query.set("only_with_cars", "true");
  query.set("limit", String(params.limit ?? 25));
  query.set("offset", String(params.offset ?? 0));

  return apiRequest<QmsAuditRegisterPage>(`/quality/audits/register/paged?${query.toString()}`, {
    signal: params.signal,
    timeoutMs: 15_000,
    cacheTtlMs: 10_000,
    staleWhileOfflineMs: 5 * 60_000,
  });
}

export function qmsGetCarRegisterPage(params: QmsCarRegisterPageParams = {}): Promise<QmsCarRegisterPage> {
  const query = new URLSearchParams();
  setIfPresent(query, "program", params.program);
  setIfPresent(query, "status_", params.status);
  setIfPresent(query, "scope", params.scope);
  setIfPresent(query, "car_id", params.carId);
  setIfPresent(query, "assigned_to_user_id", params.assignedToUserId);
  setIfPresent(query, "audit_id", params.auditId);
  setIfPresent(query, "search", params.search);
  if (params.dueSoonDays != null) query.set("due_soon_days", String(params.dueSoonDays));
  query.set("limit", String(params.limit ?? 25));
  query.set("offset", String(params.offset ?? 0));

  return apiRequest<QmsCarRegisterPage>(`/quality/cars/register/paged?${query.toString()}`, {
    signal: params.signal,
    timeoutMs: 15_000,
    cacheTtlMs: 8_000,
    staleWhileOfflineMs: 5 * 60_000,
  });
}
