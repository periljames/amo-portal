import { getApiBaseUrl } from "./config";
import type {
  ExternalAuditorFieldworkItem,
  ExternalAuditorFieldworkModel,
  ExternalAuditorMutationResult,
  ExternalChecklistResponse,
} from "./qmsAuditExternalAccess";
import {
  clearExternalAuditMutations,
  type ExternalAuditOutboxMutation,
} from "./qmsExternalAuditOutbox";

export class ExternalAuditMutationError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ExternalAuditMutationError";
    this.status = status;
  }
}

function clientMutationId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? `qms-external-fieldwork-${crypto.randomUUID()}`
    : `qms-external-fieldwork-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function deviceIdentity(): { deviceId: string; deviceSequence: number } {
  const deviceIdKey = "amo:qms:external-fieldwork-device-id";
  const deviceSequenceKey = "amo:qms:external-fieldwork-sequence";
  let deviceId = typeof window !== "undefined" ? window.localStorage.getItem(deviceIdKey) : null;
  if (!deviceId) {
    deviceId = typeof crypto !== "undefined" && "randomUUID" in crypto
      ? `qms-external-device-${crypto.randomUUID()}`
      : `qms-external-device-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    if (typeof window !== "undefined") window.localStorage.setItem(deviceIdKey, deviceId);
  }
  const prior = typeof window !== "undefined" ? Number(window.localStorage.getItem(deviceSequenceKey) || "0") : 0;
  const deviceSequence = Math.max(Number.isSafeInteger(prior) ? prior + 1 : 1, Date.now());
  if (typeof window !== "undefined") window.localStorage.setItem(deviceSequenceKey, String(deviceSequence));
  return { deviceId, deviceSequence };
}

export function buildExternalAuditorMutation(
  item: ExternalAuditorFieldworkItem,
  payload: {
    canonicalResponseStatus: ExternalChecklistResponse;
    auditorNotes?: string | null;
    evidenceReferences?: Array<Record<string, unknown> | string>;
    reason: string;
  },
): ExternalAuditOutboxMutation {
  const device = deviceIdentity();
  return {
    checklistItemId: item.checklist_item_id,
    clientMutationId: clientMutationId(),
    deviceId: device.deviceId,
    deviceSequence: device.deviceSequence,
    clientTimestamp: new Date().toISOString(),
    baseVersion: item.entity_version,
    operation: "CHECKLIST_UPDATE",
    canonicalResponseStatus: payload.canonicalResponseStatus,
    auditorNotes: payload.auditorNotes ?? null,
    evidenceReferences: payload.evidenceReferences ?? [],
    reason: payload.reason,
  };
}

export async function commitExternalAuditorMutation(
  model: Pick<ExternalAuditorFieldworkModel, "csrf_token" | "audit_id" | "participant_id">,
  mutation: ExternalAuditOutboxMutation,
): Promise<ExternalAuditorMutationResult> {
  const response = await fetch(`${getApiBaseUrl()}/quality/audit-access/fieldwork/checklist-items/${encodeURIComponent(mutation.checklistItemId)}/mutations`, {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-QMS-CSRF": model.csrf_token,
    },
    body: JSON.stringify({
      client_mutation_id: mutation.clientMutationId,
      device_id: mutation.deviceId,
      device_sequence: mutation.deviceSequence,
      client_timestamp: mutation.clientTimestamp,
      base_version: mutation.baseVersion,
      operation: mutation.operation,
      canonical_response_status: mutation.canonicalResponseStatus,
      auditor_notes: mutation.auditorNotes,
      evidence_references: mutation.evidenceReferences,
      reason: mutation.reason,
    }),
  });
  if (!response.ok) {
    // A revoked, expired or no-longer-purpose-bound guest identity must not leave
    // confidential queued fieldwork lingering on the device. Purge only this
    // audit/participant scope; unrelated offline work remains isolated.
    if ([401, 403, 404].includes(response.status)) {
      await clearExternalAuditMutations({ auditId: model.audit_id, participantId: model.participant_id }).catch(() => undefined);
    }
    const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = payload?.detail;
    let message = `External checklist update failed with status ${response.status}.`;
    if (typeof detail === "string") message = detail;
    else if (detail && typeof detail === "object" && typeof (detail as { message?: unknown }).message === "string") message = String((detail as { message: unknown }).message);
    throw new ExternalAuditMutationError(message, response.status);
  }
  return response.json() as Promise<ExternalAuditorMutationResult>;
}
