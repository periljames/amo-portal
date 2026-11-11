import { apiRequest, qmsPath } from "./apiClient";

export type QmsRiskStatus = "DRAFT" | "TREATMENT" | "PENDING_ACCEPTANCE" | "ACCEPTED" | "MONITORING";
export type QmsRiskSourceType = "AUDIT" | "CAR" | "FINDING" | "PROCESS" | "SUPPLIER";
export type QmsRisk = {
  id: string; title: string; description: string; status: QmsRiskStatus;
  owner_user_id: string; created_by: string;
  payload: {
    version: number; source_type: QmsRiskSourceType; source_id: string;
    safety_boundary: "QUALITY_ONLY" | "SMS_ESCALATION_REQUIRED";
    assessment: { likelihood: number; severity: number; score: number; consequence: string; basis: string };
    residual_request?: {
      likelihood: number; severity: number; score: number; treatment_summary: string;
      policy_reference: string; evidence_id: string;
    };
    residual_decision?: { accepted: boolean; rationale: string; decided_by: string };
    monitoring?: { reason: string; initiated_at: string };
  };
};
export type RiskControl = {
  id: string; title: string; description: string; status: "ASSIGNED" | "VERIFIED" | "INEFFECTIVE";
  owner_user_id: string; due_date: string;
  payload: { risk_id: string; expected_outcome: string; verification?: {
    evidence_id: string; effective: boolean; rationale: string; verified_by: string;
  } };
};
export type RiskDetail = { risk: QmsRisk; controls: RiskControl[] };
export type RiskOption = { id: string; title: string };
export type RiskOwner = { id: string; name: string };

const base = (tenant: string, path = "") => qmsPath(tenant, "/risk" + path);
const post = <T>(tenant: string, path: string, fields: Record<string, unknown>): Promise<T> =>
  apiRequest<T>(base(tenant, path), { method: "POST", body: JSON.stringify(fields), cacheTtlMs: 0, timeoutMs: 20000 });

export function listQmsRisks(tenant: string, offset = 0) {
  return apiRequest<{ items: QmsRisk[]; total: number; limit: number; offset: number }>(
    base(tenant, "/register?limit=25&offset=" + offset), { cacheTtlMs: 0 });
}
export function listQmsRiskOwners(tenant: string) {
  return apiRequest<{ items: RiskOwner[] }>(base(tenant, "/owners"), { cacheTtlMs: 30000 });
}
export function listQmsRiskSources(tenant: string, source: QmsRiskSourceType) {
  return apiRequest<{ items: RiskOption[] }>(base(tenant, "/sources?source_type=" + source), { cacheTtlMs: 10000 });
}
export function listQmsRiskEvidence(tenant: string) {
  return apiRequest<{ items: RiskOption[] }>(base(tenant, "/evidence"), { cacheTtlMs: 10000 });
}
export function readQmsRisk(tenant: string, riskId: string) {
  return apiRequest<RiskDetail>(base(tenant, "/register/" + encodeURIComponent(riskId)), { cacheTtlMs: 0 });
}
export function createQmsRisk(tenant: string, fields: Record<string, unknown>) {
  return post<{ risk: QmsRisk }>(tenant, "/register", fields);
}
export function addQmsRiskControl(tenant: string, riskId: string, fields: Record<string, unknown>) {
  return post<{ risk: QmsRisk; control: RiskControl }>(tenant, "/register/" + encodeURIComponent(riskId) + "/controls", fields);
}
export function verifyQmsRiskControl(
  tenant: string, riskId: string, controlId: string, fields: Record<string, unknown>,
) {
  return post<{ risk: QmsRisk; control_status: string }>(
    tenant, "/register/" + encodeURIComponent(riskId) + "/controls/" + encodeURIComponent(controlId) + "/verify", fields);
}
export function transitionQmsRisk(tenant: string, riskId: string, action: "reassess" | "submit-residual" | "decide-residual" | "monitor", fields: Record<string, unknown>) {
  return post<{ risk: QmsRisk }>(tenant, "/register/" + encodeURIComponent(riskId) + "/" + action, fields);
}
