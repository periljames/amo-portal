import { currentOfflineScope, listOfflineMutations } from "./offlinePersistence";
import {
  listChecklistExecutionGovernance,
  type ChecklistExecutionGovernanceRow,
} from "./qmsChecklistExecutionGovernance";
import {
  uploadInternalAuditEvidence,
  type AuditEvidenceArtifact,
  type AuditEvidenceContext,
} from "./qmsAuditEvidence";

export type OfflineEvidenceState =
  | "LOCAL_ONLY"
  | "QUEUED"
  | "UPLOADING"
  | "UPLOAD_FAILED"
  | "CONFLICT"
  | "CORRUPT";

export type OfflineAuditEvidenceEntry = {
  id: string;
  scope: string;
  amoCode: string;
  auditId: string;
  checklistItemId: string;
  findingId: string | null;
  filename: string;
  contentType: string;
  sizeBytes: number;
  sha256: string;
  description: string | null;
  context: AuditEvidenceContext | null;
  clientMutationId: string;
  capturedBaseVersion: number;
  capturedAt: string;
  state: OfflineEvidenceState;
  retryCount: number;
  lastError: string | null;
};

type StoredEntry = OfflineAuditEvidenceEntry & {
  metadataIv: string;
  metadataCiphertext: string;
  fileIv: string;
  fileCiphertext: ArrayBuffer;
};

const DB_NAME = "amo-qms-offline-evidence";
const DB_VERSION = 1;
const ENTRY_STORE = "evidence";
const KEY_STORE = "keys";
const KEY_ID = "internal-audit-evidence-aes-gcm-v1";
const MAX_LOCAL_BYTES = 50 * 1024 * 1024;
const CHANGE_EVENT = "amo:qms-offline-evidence-changed";

function bytesToBase64(bytes: Uint8Array): string {
  let raw = "";
  bytes.forEach((byte) => { raw += String.fromCharCode(byte); });
  return btoa(raw);
}

function base64ToBytes(value: string): Uint8Array<ArrayBuffer> {
  const raw = atob(value);
  const buffer = new ArrayBuffer(raw.length);
  const bytes = new Uint8Array(buffer);
  for (let index = 0; index < raw.length; index += 1) bytes[index] = raw.charCodeAt(index);
  return bytes;
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("IndexedDB request failed."));
  });
}

function transactionDone(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error || new Error("IndexedDB transaction failed."));
    transaction.onabort = () => reject(transaction.error || new Error("IndexedDB transaction aborted."));
  });
}

function ensureStorageAvailable(): void {
  if (
    typeof window === "undefined"
    || typeof indexedDB === "undefined"
    || typeof crypto === "undefined"
    || !crypto.subtle
  ) {
    throw new Error("Secure offline evidence storage is not available in this browser.");
  }
}

async function openDb(): Promise<IDBDatabase> {
  ensureStorageAvailable();
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(ENTRY_STORE)) {
        const store = db.createObjectStore(ENTRY_STORE, { keyPath: "id" });
        store.createIndex("scope_audit", ["scope", "auditId"], { unique: false });
        store.createIndex("scope_audit_item", ["scope", "auditId", "checklistItemId"], { unique: false });
        store.createIndex("state", "state", { unique: false });
        store.createIndex("capturedAt", "capturedAt", { unique: false });
      }
      if (!db.objectStoreNames.contains(KEY_STORE)) {
        db.createObjectStore(KEY_STORE, { keyPath: "id" });
      }
    };
    request.onsuccess = () => {
      request.result.onversionchange = () => request.result.close();
      resolve(request.result);
    };
    request.onerror = () => reject(request.error || new Error("Unable to open secure offline evidence storage."));
  });
}

async function encryptionKey(db: IDBDatabase): Promise<CryptoKey> {
  const readTx = db.transaction(KEY_STORE, "readonly");
  const existing = await requestResult(readTx.objectStore(KEY_STORE).get(KEY_ID)) as { id: string; key: CryptoKey } | undefined;
  await transactionDone(readTx);
  if (existing?.key) return existing.key;

  const key = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
  const writeTx = db.transaction(KEY_STORE, "readwrite");
  writeTx.objectStore(KEY_STORE).put({ id: KEY_ID, key, createdAt: Date.now() });
  await transactionDone(writeTx);
  return key;
}

async function encryptText(key: CryptoKey, value: unknown): Promise<{ iv: string; data: string }> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const plaintext = new TextEncoder().encode(JSON.stringify(value));
  const ciphertext = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, plaintext);
  return { iv: bytesToBase64(iv), data: bytesToBase64(new Uint8Array(ciphertext)) };
}

async function decryptText<T>(key: CryptoKey, iv: string, data: string): Promise<T> {
  const plaintext = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: base64ToBytes(iv) },
    key,
    base64ToBytes(data),
  );
  return JSON.parse(new TextDecoder().decode(plaintext)) as T;
}

async function encryptFile(key: CryptoKey, file: File): Promise<{ iv: string; data: ArrayBuffer }> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const plaintext = await file.arrayBuffer();
  const data = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, plaintext);
  return { iv: bytesToBase64(iv), data };
}

async function decryptFile(key: CryptoKey, row: StoredEntry): Promise<File> {
  const plaintext = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: base64ToBytes(row.fileIv) },
    key,
    row.fileCiphertext,
  );
  return new File([plaintext], row.filename, { type: row.contentType || "application/octet-stream", lastModified: Date.parse(row.capturedAt) || Date.now() });
}

async function sha256(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, "0")).join("");
}

function notifyChanged(): void {
  if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent(CHANGE_EVENT));
}

export function onOfflineAuditEvidenceChanged(listener: () => void): () => void {
  if (typeof window === "undefined") return () => undefined;
  window.addEventListener(CHANGE_EVENT, listener);
  return () => window.removeEventListener(CHANGE_EVENT, listener);
}

function publicEntry(row: StoredEntry): OfflineAuditEvidenceEntry {
  return {
    id: row.id,
    scope: row.scope,
    amoCode: row.amoCode,
    auditId: row.auditId,
    checklistItemId: row.checklistItemId,
    findingId: row.findingId,
    filename: row.filename,
    contentType: row.contentType,
    sizeBytes: row.sizeBytes,
    sha256: row.sha256,
    description: row.description,
    context: row.context,
    clientMutationId: row.clientMutationId,
    capturedBaseVersion: row.capturedBaseVersion,
    capturedAt: row.capturedAt,
    state: row.state,
    retryCount: row.retryCount,
    lastError: row.lastError,
  };
}

async function putStored(row: StoredEntry): Promise<void> {
  const db = await openDb();
  try {
    const tx = db.transaction(ENTRY_STORE, "readwrite");
    tx.objectStore(ENTRY_STORE).put(row);
    await transactionDone(tx);
  } finally {
    db.close();
  }
  notifyChanged();
}

async function deleteStored(id: string): Promise<void> {
  const db = await openDb();
  try {
    const tx = db.transaction(ENTRY_STORE, "readwrite");
    tx.objectStore(ENTRY_STORE).delete(id);
    await transactionDone(tx);
  } finally {
    db.close();
  }
  notifyChanged();
}

async function scopedRows(
  amoCode: string,
  auditId: string,
  checklistItemId?: string | null,
): Promise<StoredEntry[]> {
  const scope = currentOfflineScope();
  const db = await openDb();
  try {
    const tx = db.transaction(ENTRY_STORE, "readonly");
    const store = tx.objectStore(ENTRY_STORE);
    const rows = checklistItemId
      ? await requestResult(store.index("scope_audit_item").getAll(IDBKeyRange.only([scope, auditId, checklistItemId])))
      : await requestResult(store.index("scope_audit").getAll(IDBKeyRange.only([scope, auditId])));
    await transactionDone(tx);
    return (rows as StoredEntry[])
      .filter((row) => row.scope === scope && row.amoCode === amoCode)
      .sort((a, b) => a.capturedAt.localeCompare(b.capturedAt));
  } finally {
    db.close();
  }
}

export async function enqueueOfflineAuditEvidence(input: {
  amoCode: string;
  auditId: string;
  checklistItemId: string;
  findingId?: string | null;
  file: File;
  description?: string | null;
  context?: AuditEvidenceContext | null;
  clientMutationId: string;
  baseVersion: number;
}): Promise<OfflineAuditEvidenceEntry> {
  if (input.file.size > MAX_LOCAL_BYTES) throw new Error("Evidence exceeds the 50 MB offline storage limit.");
  const scope = currentOfflineScope();
  if (scope.startsWith("anonymous:")) throw new Error("Sign in before saving controlled audit evidence offline.");

  const db = await openDb();
  try {
    const key = await encryptionKey(db);
    const capturedAt = new Date().toISOString();
    const hash = await sha256(input.file);
    const metadata = await encryptText(key, {
      description: input.description?.trim() || null,
      findingId: input.findingId || null,
      context: input.context || null,
    });
    const encryptedFile = await encryptFile(key, input.file);
    const row: StoredEntry = {
      id: input.clientMutationId,
      scope,
      amoCode: input.amoCode,
      auditId: input.auditId,
      checklistItemId: input.checklistItemId,
      // Sensitive context is retained only inside metadataCiphertext at rest.
      findingId: null,
      filename: input.file.name,
      contentType: input.file.type || "application/octet-stream",
      sizeBytes: input.file.size,
      sha256: hash,
      description: null,
      context: null,
      clientMutationId: input.clientMutationId,
      capturedBaseVersion: input.baseVersion,
      capturedAt,
      state: "QUEUED",
      retryCount: 0,
      lastError: null,
      metadataIv: metadata.iv,
      metadataCiphertext: metadata.data,
      fileIv: encryptedFile.iv,
      fileCiphertext: encryptedFile.data,
    };
    const tx = db.transaction(ENTRY_STORE, "readwrite");
    tx.objectStore(ENTRY_STORE).put(row);
    await transactionDone(tx);
    notifyChanged();
    return {
      ...publicEntry(row),
      findingId: input.findingId || null,
      description: input.description?.trim() || null,
      context: input.context || null,
    };
  } finally {
    db.close();
  }
}

export async function listOfflineAuditEvidence(
  amoCode: string,
  auditId: string,
  checklistItemId?: string | null,
): Promise<OfflineAuditEvidenceEntry[]> {
  return (await scopedRows(amoCode, auditId, checklistItemId)).map(publicEntry);
}

async function updateState(row: StoredEntry, state: OfflineEvidenceState, error: string | null): Promise<StoredEntry> {
  const next = {
    ...row,
    state,
    retryCount: state === "UPLOAD_FAILED" || state === "CONFLICT" || state === "CORRUPT"
      ? row.retryCount + 1
      : row.retryCount,
    lastError: error?.slice(0, 1200) || null,
  };
  await putStored(next);
  return next;
}

function errorStatus(error: unknown): number | null {
  if (!error || typeof error !== "object") return null;
  const status = (error as { status?: unknown }).status;
  return typeof status === "number" ? status : null;
}

export async function replayOfflineAuditEvidence(
  amoCode: string,
  auditId: string,
): Promise<{ uploaded: AuditEvidenceArtifact[]; failed: number; conflicts: number; deferred: number }> {
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    return { uploaded: [], failed: 0, conflicts: 0, deferred: 0 };
  }
  const rows = await scopedRows(amoCode, auditId);
  if (!rows.length) return { uploaded: [], failed: 0, conflicts: 0, deferred: 0 };

  const governance = await listChecklistExecutionGovernance(amoCode, auditId);
  const byItem = new Map<string, ChecklistExecutionGovernanceRow>(
    governance.items.map((item) => [item.checklist_item_id, item]),
  );
  const uploaded: AuditEvidenceArtifact[] = [];
  let failed = 0;
  let conflicts = 0;
  let deferred = 0;
  const pendingChecklistMutations = (await listOfflineMutations()).filter((entry) =>
    entry.entityType === "qms-audit-checklist-item"
    && (entry.status === "queued" || entry.status === "syncing")
    && entry.path.includes(`/audits/${encodeURIComponent(auditId)}/checklist-items/`)
  );

  for (let row of rows) {
    if (currentOfflineScope() !== row.scope) break;
    if (row.state === "CORRUPT") { failed += 1; continue; }

    const hasEarlierChecklistMutation = pendingChecklistMutations.some((entry) =>
      entry.entityId === row.checklistItemId
      || entry.path.includes(`/checklist-items/${encodeURIComponent(row.checklistItemId)}/`)
    );
    if (hasEarlierChecklistMutation) {
      // Preserve local operation ordering: a queued response/finding is based on
      // the version that existed before this evidence was captured. Let the
      // structured mutation commit first, then upload evidence against the new
      // authoritative version. This prevents the two local queues from
      // invalidating each other on reconnect.
      deferred += 1;
      continue;
    }

    const item = byItem.get(row.checklistItemId);
    if (!item) {
      row = await updateState(row, "CONFLICT", "The checklist item is no longer available to the active audit.");
      conflicts += 1;
      continue;
    }

    const db = await openDb();
    let file: File;
    let metadata: { description?: string | null; findingId?: string | null; context?: AuditEvidenceContext | null };
    try {
      const key = await encryptionKey(db);
      metadata = await decryptText<{ description?: string | null; findingId?: string | null; context?: AuditEvidenceContext | null }>(
        key,
        row.metadataIv,
        row.metadataCiphertext,
      );
      file = await decryptFile(key, row);
    } catch (error) {
      await updateState(row, "CORRUPT", error instanceof Error ? error.message : "Local evidence could not be decrypted.");
      failed += 1;
      continue;
    } finally {
      db.close();
    }

    row = await updateState(row, "UPLOADING", null);
    try {
      const result = await uploadInternalAuditEvidence(
        amoCode,
        auditId,
        row.checklistItemId,
        file,
        {
          baseVersion: item.entity_version,
          clientMutationId: row.clientMutationId,
          description: metadata.description || null,
          findingId: metadata.findingId || null,
          context: metadata.context || null,
          capturedAt: row.capturedAt,
        },
      );
      if (result.artifact.sha256.toLowerCase() !== row.sha256.toLowerCase()) {
        await updateState(row, "CORRUPT", "Server evidence hash does not match the locally captured file.");
        failed += 1;
        continue;
      }
      uploaded.push(result.artifact);
      if (result.replayed) {
        // A retry may be acknowledging a commit whose original response was lost.
        // Refresh the authoritative checklist row before advancing the next queued
        // evidence item instead of trusting a missing/stale replay version.
        const refreshed = await listChecklistExecutionGovernance(amoCode, auditId);
        const authoritative = refreshed.items.find((entry) => entry.checklist_item_id === row.checklistItemId);
        if (!authoritative) {
          await updateState(row, "CONFLICT", "The replayed evidence exists, but the authoritative checklist state could not be refreshed.");
          conflicts += 1;
          continue;
        }
        item.entity_version = authoritative.entity_version;
      } else {
        item.entity_version = result.committed_version;
      }
      await deleteStored(row.id);
    } catch (error) {
      const status = errorStatus(error);
      const message = error instanceof Error ? error.message : "Evidence synchronization failed.";
      if (status === 409 || status === 412 || status === 422) {
        await updateState(row, "CONFLICT", message);
        conflicts += 1;
      } else {
        await updateState(row, "UPLOAD_FAILED", message);
        failed += 1;
      }
    }
  }
  return { uploaded, failed, conflicts, deferred };
}

export async function discardOfflineAuditEvidence(id: string): Promise<void> {
  await deleteStored(id);
}