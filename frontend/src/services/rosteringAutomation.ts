import { apiJson, jsonBody, queryString } from "./typedApi";
import type {
  RosterAutomationPreview,
  RosterAutomationPreviewRequest,
  RosterGenerationPolicy,
  RosterGenerationPolicyUpdate,
  RosterGenerationRun,
  RosterSetupReadiness,
} from "../types/rosteringAutomation";

const ROOT = "/rostering";

export function getRosterSetupReadiness(): Promise<RosterSetupReadiness> {
  return apiJson(`${ROOT}/setup/readiness`, { offline: { cacheTtlMs: 60_000 } });
}

export function getRosterAutomationPolicy(): Promise<RosterGenerationPolicy> {
  return apiJson(`${ROOT}/automation-policy`, { offline: { cacheTtlMs: 60_000 } });
}

export function updateRosterAutomationPolicy(payload: RosterGenerationPolicyUpdate): Promise<RosterGenerationPolicy> {
  return apiJson(`${ROOT}/automation-policy`, { method: "PATCH", body: jsonBody(payload) });
}

export function previewRosterAutomation(payload: RosterAutomationPreviewRequest = {}): Promise<RosterAutomationPreview> {
  return apiJson(`${ROOT}/automation/preview`, { method: "POST", body: jsonBody(payload) });
}

export function runRosterAutomation(payload: RosterAutomationPreviewRequest & {
  idempotency_key: string;
  confirm_preview: boolean;
}): Promise<RosterGenerationRun> {
  return apiJson(`${ROOT}/automation/run`, { method: "POST", body: jsonBody(payload) });
}

export function listRosterAutomationRuns(limit = 20): Promise<RosterGenerationRun[]> {
  return apiJson(`${ROOT}/automation/runs${queryString({ limit })}`, { offline: { cacheTtlMs: 30_000 } });
}
