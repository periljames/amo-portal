import { apiRequest } from "./apiClient";
import type { QMSAuditRegisterRowOut } from "./qms";

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
  onlyWithCars?: boolean;
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

function setIfPresent(query: URLSearchParams, key: string, value: string | undefined): void {
  const clean = value?.trim();
  if (clean) query.set(key, clean);
}

export function qmsGetAuditRegisterPage(params: QmsAuditRegisterPageParams = {}): Promise<QmsAuditRegisterPage> {
  const query = new URLSearchParams();
  setIfPresent(query, "domain", params.domain);
  setIfPresent(query, "audit_id", params.auditId);
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
