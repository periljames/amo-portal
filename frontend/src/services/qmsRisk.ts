// src/services/qmsRisk.ts
import { apiRequest, qmsPath } from "./apiClient";
import type { QmsListResponse } from "../types/qms";

export function getQmsRisk(amoCode: string): Promise<QmsListResponse> {
  return apiRequest<QmsListResponse>(qmsPath(amoCode, "/risk"));
}


/** Governed risk and opportunity actions backed by the canonical QMS records. */
export type RiskKind = "RISK" | "OPPORTUNITY";
export type RiskParticipant = { id: string; name: string };
export type GovernedRisk = {
  id: string; title: string; description: string; status: string; owner_user_id: string;
  due_date?: string | null;
  payload: {
    kind: RiskKind; version: number; source_system: string;
    source_reference?: string | null; accepted_by?: string; acceptance_reason?: string;
    assessment_history?: Array<{
      type: "INITIAL" | "RESIDUAL"; matrix_version: string; likelihood: string;
      consequence: string; rating: string; basis: string; actor_user_id: string;
      evidence_record_ids: string[];
    }>;
  };
};
export type RiskChild = {
  id: string; title: string; description: string; status: string;
  owner_user_id?: string | null; due_date?: string | null;
  payload: { parent_id: string; kind: RiskKind; effectiveness_measure?: string };
};
export type RiskDetail = { record: GovernedRisk; controls: RiskChild[]; actions: RiskChild[] };
export type GovernedRiskMatrix = {
  version?: string;
  likelihood_levels?: string[];
  consequence_levels?: string[];
  rating_levels?: string[];
  rating_cells?: Record<string, Record<string, string>>;
};
function govPath(amoCode: string, suffix: string): string {
  return qmsPath(amoCode, "/risk/governance" + suffix);
}
function riskPost<T>(amoCode: string, suffix: string, payload: Record<string, unknown>): Promise<T> {
  return apiRequest<T>(govPath(amoCode, suffix), {
    method: "POST", body: JSON.stringify(payload), cacheTtlMs: 0, timeoutMs: 20000,
  });
}
function riskRecordPath(kind: RiskKind, riskId: string): string {
  return "/records/" + encodeURIComponent(kind) + "/" + encodeURIComponent(riskId);
}
export function getGovernedRiskMatrix(amoCode: string) {
  return apiRequest<{ matrix: GovernedRiskMatrix; authority: string }>(govPath(amoCode, "/matrix"), { cacheTtlMs: 0 });
}
export function getRiskParticipants(amoCode: string) {
  return apiRequest<{ items: RiskParticipant[] }>(govPath(amoCode, "/participants"), { cacheTtlMs: 10000 });
}
export function listGovernedRisks(amoCode: string, kind: RiskKind, offset = 0) {
  return apiRequest<{ kind: RiskKind; items: GovernedRisk[]; total: number; offset: number; limit: number }>(
    govPath(amoCode, "/records?kind=" + kind + "&limit=25&offset=" + offset), { cacheTtlMs: 0 }
  );
}
export function readGovernedRisk(amoCode: string, kind: RiskKind, riskId: string) {
  return apiRequest<RiskDetail>(govPath(amoCode, riskRecordPath(kind, riskId)), { cacheTtlMs: 0 });
}
export function createGovernedRisk(amoCode: string, payload: {
  kind: RiskKind; title: string; description: string; owner_user_id: string;
  reassess_by: string; source_reference?: string; source_system: "QUALITY" | "SMS_LINKED";
}) {
  return riskPost<{ record: GovernedRisk }>(amoCode, "/records", payload);
}
export function assessGovernedRisk(amoCode: string, kind: RiskKind, riskId: string, fields: Record<string, unknown>) {
  return riskPost<{ record: GovernedRisk }>(amoCode, riskRecordPath(kind, riskId) + "/assess", fields);
}
export function addGovernedRiskControl(amoCode: string, kind: RiskKind, riskId: string, fields: Record<string, unknown>) {
  return riskPost<{ record: GovernedRisk; control: RiskChild }>(amoCode, riskRecordPath(kind, riskId) + "/controls", fields);
}
export function addGovernedRiskTreatment(amoCode: string, kind: RiskKind, riskId: string, fields: Record<string, unknown>) {
  return riskPost<{ record: GovernedRisk; action: RiskChild }>(amoCode, riskRecordPath(kind, riskId) + "/actions", fields);
}
export function acceptGovernedResidual(amoCode: string, kind: RiskKind, riskId: string, fields: Record<string, unknown>) {
  return riskPost<{ record: GovernedRisk }>(amoCode, riskRecordPath(kind, riskId) + "/accept", fields);
}
export function reopenGovernedRisk(amoCode: string, kind: RiskKind, riskId: string, fields: Record<string, unknown>) {
  return riskPost<{ record: GovernedRisk }>(amoCode, riskRecordPath(kind, riskId) + "/reassess", fields);
}

export function completeRiskTreatment(
  amoCode: string, kind: RiskKind, riskId: string, actionId: string,
  statement: string, evidence_record_ids: string[],
) {
  return riskPost<{ action_id: string; status: string }>(
    amoCode, riskRecordPath(kind, riskId) + "/actions/" + encodeURIComponent(actionId) + "/complete",
    { statement, evidence_record_ids },
  );
}
export function verifyRiskTreatment(
  amoCode: string, kind: RiskKind, riskId: string, actionId: string,
  accepted: boolean, reason: string,
) {
  return riskPost<{ action_id: string; status: string }>(
    amoCode, riskRecordPath(kind, riskId) + "/actions/" + encodeURIComponent(actionId) + "/verify",
    { accepted, reason },
  );
}
