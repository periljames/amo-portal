import { apiJson, jsonBody, queryString } from "./typedApi";
import type {
  RosterAssignmentConsentRead,
  RosterConsentPersonnelDecision,
  RosterConsentSupervisorDecision,
  RosterDutyExtensionCreate,
  RosterDutyExtensionRead,
  RosterRegulatoryExemptionCreate,
  RosterRegulatoryExemptionRead,
  RosterWorkflowGateResponse,
} from "../types/rosteringCompliance";

export function listMyRosterConsents(): Promise<RosterAssignmentConsentRead[]> {
  return apiJson("/rostering/consents/me", { offline: { cacheTtlMs: 30_000 } });
}

export function listSupervisorPendingRosterConsents(): Promise<RosterAssignmentConsentRead[]> {
  return apiJson("/rostering/consents/supervisor/pending", { offline: { cacheTtlMs: 20_000 } });
}

export function listVersionRosterConsents(versionId: string): Promise<RosterAssignmentConsentRead[]> {
  return apiJson(`/rostering/consents/versions/${encodeURIComponent(versionId)}`, {
    offline: { cacheTtlMs: 20_000 },
  });
}

export function respondRosterConsent(
  consentId: string,
  payload: RosterConsentPersonnelDecision,
): Promise<RosterAssignmentConsentRead> {
  return apiJson(`/rostering/consents/${encodeURIComponent(consentId)}/respond`, {
    method: "POST",
    body: jsonBody(payload),
  });
}

export function decideRosterConsentAsSupervisor(
  consentId: string,
  payload: RosterConsentSupervisorDecision,
): Promise<RosterAssignmentConsentRead> {
  return apiJson(`/rostering/consents/${encodeURIComponent(consentId)}/supervisor-decision`, {
    method: "POST",
    body: jsonBody(payload),
  });
}

export function getRosterWorkflowGates(versionId: string): Promise<RosterWorkflowGateResponse> {
  return apiJson(`/rostering/versions/${encodeURIComponent(versionId)}/workflow-gates`, {
    offline: { cacheTtlMs: 15_000 },
  });
}

export function listRegulatoryExemptions(): Promise<RosterRegulatoryExemptionRead[]> {
  return apiJson("/rostering/regulatory-exemptions", { offline: { cacheTtlMs: 60_000 } });
}

export function createRegulatoryExemption(
  payload: RosterRegulatoryExemptionCreate,
): Promise<RosterRegulatoryExemptionRead> {
  return apiJson("/rostering/regulatory-exemptions", {
    method: "POST",
    body: jsonBody(payload),
  });
}

export function verifyRegulatoryExemption(exemptionId: string): Promise<RosterRegulatoryExemptionRead> {
  return apiJson(`/rostering/regulatory-exemptions/${encodeURIComponent(exemptionId)}/verify`, {
    method: "POST",
  });
}

export function revokeRegulatoryExemption(
  exemptionId: string,
  reason: string,
): Promise<RosterRegulatoryExemptionRead> {
  return apiJson(`/rostering/regulatory-exemptions/${encodeURIComponent(exemptionId)}/revoke`, {
    method: "POST",
    body: jsonBody({ reason }),
  });
}

export function listDutyExtensions(versionId?: string | null): Promise<RosterDutyExtensionRead[]> {
  return apiJson(`/rostering/duty-extensions${queryString({ version_id: versionId || null })}`, {
    offline: { cacheTtlMs: 20_000 },
  });
}

export function proposeDutyExtension(payload: RosterDutyExtensionCreate): Promise<RosterDutyExtensionRead> {
  return apiJson("/rostering/duty-extensions", {
    method: "POST",
    body: jsonBody(payload),
  });
}
