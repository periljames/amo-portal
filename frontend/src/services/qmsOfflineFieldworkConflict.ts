import { assertOfflineReplayAllowed } from "./offlineCapabilities";
import {
  discardOfflineMutation,
  enqueueOfflineMutation,
  type OfflineOutboxEntry,
} from "./offlinePersistence";

type JsonObject = Record<string, unknown>;

export type QmsFieldworkConflictSnapshot = {
  serverVersion: number;
  baseVersion: number | null;
  serverRow: JsonObject | null;
  localBody: JsonObject;
};

function asObject(value: unknown): JsonObject | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as JsonObject
    : null;
}

function conflictDetail(entry: OfflineOutboxEntry): JsonObject | null {
  const outer = asObject(entry.conflict);
  return asObject(outer?.detail) ?? outer;
}

function parseBody(entry: OfflineOutboxEntry): JsonObject {
  if (!entry.body) return {};
  try {
    const parsed = JSON.parse(entry.body) as unknown;
    return asObject(parsed) ?? {};
  } catch {
    return {};
  }
}

export function isQmsFieldworkConflict(entry: OfflineOutboxEntry): boolean {
  return entry.status === "conflict"
    && entry.entityType === "qms-audit-checklist-item"
    && entry.errorCode === "FIELDWORK_VERSION_CONFLICT";
}

export function qmsFieldworkConflictSnapshot(entry: OfflineOutboxEntry): QmsFieldworkConflictSnapshot | null {
  if (!isQmsFieldworkConflict(entry)) return null;
  const detail = conflictDetail(entry);
  const serverVersion = Number(detail?.server_version);
  if (!Number.isSafeInteger(serverVersion) || serverVersion < 0) return null;
  const localBody = parseBody(entry);
  const baseVersion = Number(localBody.base_version);
  return {
    serverVersion,
    baseVersion: Number.isSafeInteger(baseVersion) && baseVersion >= 0 ? baseVersion : null,
    serverRow: asObject(detail?.server_row),
    localBody,
  };
}

function newMutationId(): string {
  const suffix = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `qms-fieldwork-${suffix}`;
}

/**
 * Reapply a human-reviewed QMS fieldwork conflict against the latest server
 * entity version. The old mutation remains untouched until the replacement is
 * durably queued, then it is discarded. This is never an automatic merge.
 */
export async function reapplyQmsFieldworkConflict(entry: OfflineOutboxEntry): Promise<OfflineOutboxEntry> {
  const snapshot = qmsFieldworkConflictSnapshot(entry);
  if (!snapshot) throw new Error("The latest server fieldwork version is unavailable. Refresh the audit before retrying.");

  const mutationId = newMutationId();
  const currentSequence = Number(snapshot.localBody.device_sequence);
  const nextSequence = Math.max(
    Number.isSafeInteger(currentSequence) && currentSequence >= 0 ? currentSequence + 1 : 0,
    Date.now(),
  );
  const nextBody: JsonObject = {
    ...snapshot.localBody,
    client_mutation_id: mutationId,
    device_sequence: nextSequence,
    client_timestamp: new Date().toISOString(),
    base_version: snapshot.serverVersion,
  };
  const body = JSON.stringify(nextBody);
  assertOfflineReplayAllowed(entry.path, entry.method, body);

  const replacement = await enqueueOfflineMutation({
    path: entry.path,
    method: entry.method,
    headers: entry.headers,
    body,
    entityType: entry.entityType,
    entityId: entry.entityId,
    idempotencyKey: mutationId,
    scope: entry.scope,
  });
  try {
    await discardOfflineMutation(entry.id);
  } catch (error) {
    // Avoid two replayable copies if the old conflict cannot be removed.
    await discardOfflineMutation(replacement.id).catch(() => undefined);
    throw error;
  }
  return replacement;
}

export async function keepServerVersionForQmsFieldwork(entry: OfflineOutboxEntry): Promise<void> {
  if (!isQmsFieldworkConflict(entry)) throw new Error("This is not a QMS fieldwork version conflict.");
  await discardOfflineMutation(entry.id);
}
