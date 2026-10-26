import { currentOfflineScope, listOfflineMutations } from "./offlinePersistence";
import { getOrCreateDeviceStorageKey } from "./deviceStorageKey";
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
const DB_VERSION = 2;
const ENTRY_STORE = "evidence";
const RETAINED_STORE = "retained";
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
      if (!db.objectStoreNames.contains(RETAINED_STORE)) {
        const retained = db.createObjectStore(RETAINED_STORE, { keyPath: ["scope", "amoCode", "auditId", "artifactId"] });
        retained.createIndex("scope_audit", ["scope", "amoCode", "auditId"]);
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
  return getOrCreateDeviceStorageKey(db, KEY_STORE, KEY_ID);
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

async function decryptFile(key: CryptoKey, row: Pick<StoredEntry, "filename" | "contentType" | "capturedAt" | "fileIv" | "fileCiphertext">): Promise<File> {
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

type RetainedEvidence = Pick<StoredEntry, "scope" | "amoCode" | "auditId" | "filename" | "contentType" | "capturedAt" | "sha256" | "sizeBytes" | "fileIv" | "fileCiphertext"> & { artifactId: string; retainedAt: number };

async function retainEncryptedEvidence(row: RetainedEvidence): Promise<void> {
  if (row.scope !== currentOfflineScope() || row.scope.startsWith("anonymous:")) return;
  const db = await openDb();
  try {
    const tx = db.transaction(RETAINED_STORE, "readwrite");
    const store = tx.objectStore(RETAINED_STORE);
    const prior = await requestResult<RetainedEvidence[]>(store.getAll());
    const older = prior.filter(entry => entry.scope === row.scope && !(entry.amoCode === row.amoCode && entry.auditId === row.auditId && entry.artifactId === row.artifactId)).sort((a, b) => a.retainedAt - b.retainedAt);
    let bytes = older.reduce((sum, entry) => sum + entry.sizeBytes, row.sizeBytes);
    while (bytes > MAX_LOCAL_BYTES && older.length) {
      const entry = older.shift()!;
      store.delete([entry.scope, entry.amoCode, entry.auditId, entry.artifactId]);
      bytes -= entry.sizeBytes;
    }
    store.put(row);
    await transactionDone(tx);
  } finally { db.close(); }
  notifyChanged();
}

export async function retainDownloadedAuditEvidence(amoCode: string, auditId: string, artifact: AuditEvidenceArtifact, blob: Blob): Promise<boolean> {
  if (blob.size > MAX_LOCAL_BYTES) return false;
  const scope = currentOfflineScope();
  if (scope.startsWith("anonymous:")) throw new Error("Sign in before retaining audit evidence.");
  const file = new File([blob], artifact.filename, { type: artifact.content_type || blob.type });
  if (await sha256(file) !== artifact.sha256.toLowerCase()) throw new Error("The downloaded evidence does not match its recorded checksum.");
  try {
    const db = await openDb();
    let encrypted: { iv: string; data: ArrayBuffer };
    try { encrypted = await encryptFile(await encryptionKey(db), file); } finally { db.close(); }
    await retainEncryptedEvidence({ scope, amoCode, auditId, artifactId: artifact.id, filename: artifact.filename,
      contentType: file.type, capturedAt: artifact.created_at || new Date().toISOString(), sha256: artifact.sha256,
      sizeBytes: file.size, fileIv: encrypted.iv, fileCiphertext: encrypted.data, retainedAt: Date.now() });
    return true;
  } catch { return false; }
}

export async function retainedAuditEvidenceIds(amoCode: string, auditId: string): Promise<string[]> {
  const db = await openDb();
  try {
    const keys = await requestResult<IDBValidKey[]>(db.transaction(RETAINED_STORE).objectStore(RETAINED_STORE).index("scope_audit").getAllKeys([currentOfflineScope(), amoCode, auditId]));
    return keys.map(key => String((key as IDBValidKey[])[3]));
  } finally { db.close(); }
}

export async function readRetainedAuditEvidence(amoCode: string, auditId: string, artifact: AuditEvidenceArtifact): Promise<File | null> {
  const scope = currentOfflineScope();
  const db = await openDb();
  try {
    const row = await requestResult<RetainedEvidence | undefined>(db.transaction(RETAINED_STORE).objectStore(RETAINED_STORE).get([scope, amoCode, auditId, artifact.id]));
    if (!row || row.scope !== scope || row.sha256 !== artifact.sha256 || currentOfflineScope() !== scope) return null;
    const file = await decryptFile(await encryptionKey(db), row);
    if (currentOfflineScope() !== scope || await sha256(file) !== artifact.sha256.toLowerCase()) return null;
    return file;
  } finally { db.close(); }
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

/** Groups of locally encrypted evidence; metadata only, never file bytes. */
export type PendingAuditEvidenceGroup = { amoCode: string; auditId: string; count: number; conflicts: number };

export async function listPendingAuditEvidenceGroups(): Promise<PendingAuditEvidenceGroup[]> {
  const scope = currentOfflineScope();
  const db = await openDb();
  try {
    const tx = db.transaction(ENTRY_STORE, "readonly");
    const done = transactionDone(tx);
    const index = tx.objectStore(ENTRY_STORE).index("scope_audit");
    const groups = new Map<string, PendingAuditEvidenceGroup>();
    await new Promise<void>((resolve, reject) => {
      const request = index.openCursor(IDBKeyRange.bound([scope, ""], [scope, "\uffff"]));
      request.onerror = () => reject(request.error || new Error("Could not inspect local evidence queue."));
      request.onsuccess = () => {
        const cursor = request.result;
        if (!cursor) { resolve(); return; }
        const row = cursor.value as StoredEntry;
        if (row.scope === scope) {
          const key = `${row.amoCode}:${row.auditId}`;
          const value = groups.get(key) || { amoCode: row.amoCode, auditId: row.auditId, count: 0, conflicts: 0 };
          value.count += 1;
          if (row.state === "CONFLICT" || row.state === "CORRUPT") value.conflicts += 1;
          groups.set(key, value);
        }
        cursor.continue();
      };
    });
    await done;
    return [...groups.values()];
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

/** One uploader per audit across browser tabs (when Web Locks are supported). */
export async function synchronizeOfflineAuditEvidence(
  amoCode: string,
  auditId: string,
): Promise<{ uploaded: AuditEvidenceArtifact[]; failed: number; conflicts: number; deferred: number }> {
  if (typeof navigator !== "undefined" && navigator.locks) {
    return (await navigator.locks.request(
      `amo:qms:evidence:${currentOfflineScope()}:${auditId}`,
      { ifAvailable: true },
      async (lock) => lock ? replayOfflineAuditEvidence(amoCode, auditId) : null,
    )) || { uploaded: [], failed: 0, conflicts: 0, deferred: 1 };
  }
  return replayOfflineAuditEvidence(amoCode, auditId);
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
    && ["queued", "syncing", "conflict", "failed"].includes(entry.status)
    && entry.path.includes(`/audits/${encodeURIComponent(auditId)}/checklist-items/`)
  );

  for (let row of rows) {
    if (currentOfflineScope() !== row.scope) break;
    // A rejected or corrupt file requires a deliberate auditor action;
    // never silently retry a governance conflict on every reconnect.
    if (row.state === "CORRUPT" || row.state === "CONFLICT") {
      conflicts += 1;
      continue;
    }

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
      // The upload queue is removed after acceptance; a bounded encrypted
      // reading copy is independent of pending work and may be safely evicted.
      await retainEncryptedEvidence({ ...row, artifactId: result.artifact.id, retainedAt: Date.now() }).catch(() => undefined);
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
