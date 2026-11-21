// src/services/qmsExternal.ts
import { apiRequest, qmsPath } from "./apiClient";
import type { QmsListResponse } from "../types/qms";

export function getQmsExternalInterface(amoCode: string): Promise<QmsListResponse> {
  return apiRequest<QmsListResponse>(qmsPath(amoCode, "/external-interface"));
}


// Governed correspondence and commitment operations extend the canonical external API.
export type ExternalKind = "REGULATOR" | "CUSTOMER" | "AUTHORITY";
export type ExternalRecord = {
  id: string; title: string; description: string; status: string;
  owner_user_id: string; created_by: string; due_date: string | null;
  payload: {
    kind: ExternalKind; version: number; source_reference: string; received_on: string;
    last_response_id?: string; approved_response_id?: string; submitted_response_id?: string;
  };
};
export type ExternalChild = {
  id: string; title: string; description: string; status: string;
  owner_user_id?: string; created_by: string; due_date?: string | null;
  payload: {
    external_id: string; approved_by?: string; submitted_by?: string;
    submission_evidence_ids?: string[]; evidence_record_ids?: string[];
  };
};
export type ExternalDetail = { record: ExternalRecord; responses: ExternalChild[]; commitments: ExternalChild[] };
function externalGovernancePath(amoCode: string, suffix: string) {
  return qmsPath(amoCode, "/external-interface/governance" + suffix);
}
function externalGovernancePost<T>(amoCode: string, suffix: string, payload: object): Promise<T> {
  return apiRequest<T>(externalGovernancePath(amoCode, suffix), {
    method: "POST", body: JSON.stringify(payload), cacheTtlMs: 0, timeoutMs: 20000,
  });
}
function externalPath(kind: ExternalKind, recordId: string) {
  return "/records/" + encodeURIComponent(kind) + "/" + encodeURIComponent(recordId);
}
export const listExternalOwners = (amoCode: string) =>
  apiRequest<{ items: Array<{ id: string; name: string }> }>(externalGovernancePath(amoCode, "/participants"));
export const listExternalRecords = (amoCode: string, kind: ExternalKind, offset = 0) =>
  apiRequest<{ items: ExternalRecord[]; total: number }>(
    externalGovernancePath(amoCode, "/records?kind=" + kind + "&limit=25&offset=" + offset),
    { cacheTtlMs: 0 },
  );
export const readExternalRecord = (amoCode: string, kind: ExternalKind, recordId: string) =>
  apiRequest<ExternalDetail>(externalGovernancePath(amoCode, externalPath(kind, recordId)), { cacheTtlMs: 0 });
export const createExternalRecord = (amoCode: string, payload: object) =>
  externalGovernancePost<{ record: ExternalRecord }>(amoCode, "/records", payload);
export const draftExternalResponse = (amoCode: string, kind: ExternalKind, id: string, payload: object) =>
  externalGovernancePost<{ record: ExternalRecord; response: ExternalChild }>(amoCode, externalPath(kind, id) + "/responses", payload);
export const approveExternalResponse = (amoCode: string, kind: ExternalKind, id: string, payload: object) =>
  externalGovernancePost<{ record: ExternalRecord }>(amoCode, externalPath(kind, id) + "/approve", payload);
export const submitExternalResponse = (amoCode: string, kind: ExternalKind, id: string, payload: object) =>
  externalGovernancePost<{ record: ExternalRecord }>(amoCode, externalPath(kind, id) + "/submit", payload);
export const addExternalCommitment = (amoCode: string, kind: ExternalKind, id: string, payload: object) =>
  externalGovernancePost<{ record: ExternalRecord; commitment: ExternalChild }>(amoCode, externalPath(kind, id) + "/commitments", payload);
export const completeExternalCommitment = (amoCode: string, kind: ExternalKind, id: string, itemId: string, payload: object) =>
  externalGovernancePost<{ record: ExternalRecord }>(amoCode, externalPath(kind, id) + "/commitments/" + encodeURIComponent(itemId) + "/complete", payload);
export const verifyExternalCommitment = (amoCode: string, kind: ExternalKind, id: string, itemId: string, payload: object) =>
  externalGovernancePost<{ record: ExternalRecord }>(amoCode, externalPath(kind, id) + "/commitments/" + encodeURIComponent(itemId) + "/verify", payload);
export const closeExternalRecord = (amoCode: string, kind: ExternalKind, id: string, payload: object) =>
  externalGovernancePost<{ record: ExternalRecord }>(amoCode, externalPath(kind, id) + "/close", payload);
