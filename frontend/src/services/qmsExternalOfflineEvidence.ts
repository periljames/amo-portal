import type { ExternalAuditorFieldworkItem, ExternalAuditorFieldworkModel } from "./qmsAuditExternalAccess";
import { getExternalAuditorFieldwork } from "./qmsAuditExternalAccess";
import { createEvidenceMutationId, uploadExternalAuditorEvidence, type AuditEvidenceArtifact } from "./qmsAuditEvidence";
import { listExternalAuditMutations, type ExternalAuditOutboxScope } from "./qmsExternalAuditOutbox";

export type ExternalOfflineEvidenceEntry = {
  id: string;
  auditId: string;
  participantId: string;
  checklistItemId: string;
  filename: string;
  contentType: string;
  sizeBytes: number;
  sha256: string;
  capturedAt: string;
  state: "QUEUED" | "UPLOADING" | "UPLOAD_FAILED" | "CONFLICT" | "CORRUPT";
  retryCount: number;
  lastError: string | null;
};

type StoredEntry = ExternalOfflineEvidenceEntry & {
  metadataIv: string;
  metadataCiphertext: string;
  fileIv: string;
  fileCiphertext: ArrayBuffer;
};

const DB_NAME = "amo-qms-external-audit-evidence";
const DB_VERSION = 1;
const ENTRY_STORE = "evidence";
const KEY_STORE = "keys";
const KEY_ID = "external-audit-evidence-aes-gcm-v1";
const MAX_BYTES = 50 * 1024 * 1024;

function b64(bytes: Uint8Array): string {
  let raw = "";
  bytes.forEach((byte) => { raw += String.fromCharCode(byte); });
  return btoa(raw);
}

function fromB64(value: string): Uint8Array<ArrayBuffer> {
  const raw = atob(value);
  const buffer = new ArrayBuffer(raw.length);
  const bytes = new Uint8Array(buffer);
  for (let index = 0; index < raw.length; index += 1) bytes[index] = raw.charCodeAt(index);
  return bytes;
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("External offline evidence storage failed."));
  });
}

function transactionDone(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error || new Error("External offline evidence transaction failed."));
    transaction.onabort = () => reject(transaction.error || new Error("External offline evidence transaction aborted."));
  });
}

async function openDb(): Promise<IDBDatabase> {
  if (typeof indexedDB === "undefined" || !globalThis.crypto?.subtle) {
    throw new Error("Secure offline evidence storage is unavailable in this browser.");
  }
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(ENTRY_STORE)) {
        const store = db.createObjectStore(ENTRY_STORE, { keyPath: "id" });
        store.createIndex("scope", ["auditId", "participantId"], { unique: false });
        store.createIndex("scope_item", ["auditId", "participantId", "checklistItemId"], { unique: false });
      }
      if (!db.objectStoreNames.contains(KEY_STORE)) db.createObjectStore(KEY_STORE, { keyPath: "id" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Unable to open secure external evidence storage."));
  });
}

async function keyFor(db: IDBDatabase): Promise<CryptoKey> {
  const read = db.transaction(KEY_STORE, "readonly");
  const existing = await requestResult(read.objectStore(KEY_STORE).get(KEY_ID)) as { id: string; key: CryptoKey } | undefined;
  await transactionDone(read);
  if (existing?.key) return existing.key;
  const key = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
  const write = db.transaction(KEY_STORE, "readwrite");
  write.objectStore(KEY_STORE).put({ id: KEY_ID, key, createdAt: Date.now() });
  await transactionDone(write);
  return key;
}

async function sha256(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, "0")).join("");
}

async function encryptJson(key: CryptoKey, value: unknown): Promise<{ iv: string; data: string }> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const plaintext = new TextEncoder().encode(JSON.stringify(value));
  const encrypted = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, plaintext);
  return { iv: b64(iv), data: b64(new Uint8Array(encrypted)) };
}

async function decryptJson<T>(key: CryptoKey, iv: string, data: string): Promise<T> {
  const decrypted = await crypto.subtle.decrypt({ name: "AES-GCM", iv: fromB64(iv) }, key, fromB64(data));
  return JSON.parse(new TextDecoder().decode(decrypted)) as T;
}

async function encryptFile(key: CryptoKey, file: File): Promise<{ iv: string; data: ArrayBuffer }> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encrypted = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, await file.arrayBuffer());
  return { iv: b64(iv), data: encrypted };
}

async function decryptFile(key: CryptoKey, row: StoredEntry): Promise<File> {
  const decrypted = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: fromB64(row.fileIv) },
    key,
    row.fileCiphertext,
  );
  return new File([decrypted], row.filename, {
    type: row.contentType || "application/octet-stream",
    lastModified: Date.parse(row.capturedAt) || Date.now(),
  });
}

async function rows(scope: ExternalAuditOutboxScope, checklistItemId?: string): Promise<StoredEntry[]> {
  const db = await openDb();
  try {
    const tx = db.transaction(ENTRY_STORE, "readonly");
    const store = tx.objectStore(ENTRY_STORE);
    const result = checklistItemId
      ? await requestResult(store.index("scope_item").getAll(IDBKeyRange.only([scope.auditId, scope.participantId, checklistItemId])))
      : await requestResult(store.index("scope").getAll(IDBKeyRange.only([scope.auditId, scope.participantId])));
    await transactionDone(tx);
    return (result as StoredEntry[]).sort((left, right) => left.capturedAt.localeCompare(right.capturedAt));
  } finally {
    db.close();
  }
}

function publicRow(row: StoredEntry): ExternalOfflineEvidenceEntry {
  const {
    metadataIv: _metadataIv,
    metadataCiphertext: _metadataCiphertext,
    fileIv: _fileIv,
    fileCiphertext: _fileCiphertext,
    ...entry
  } = row;
  return entry;
}

async function put(row: StoredEntry): Promise<void> {
  const db = await openDb();
  try {
    const tx = db.transaction(ENTRY_STORE, "readwrite");
    tx.objectStore(ENTRY_STORE).put(row);
    await transactionDone(tx);
  } finally {
    db.close();
  }
}

async function remove(id: string): Promise<void> {
  const db = await openDb();
  try {
    const tx = db.transaction(ENTRY_STORE, "readwrite");
    tx.objectStore(ENTRY_STORE).delete(id);
    await transactionDone(tx);
  } finally {
    db.close();
  }
}

async function updateState(row: StoredEntry, state: StoredEntry["state"], error: string | null): Promise<StoredEntry> {
  const next: StoredEntry = {
    ...row,
    state,
    retryCount: ["UPLOAD_FAILED", "CONFLICT", "CORRUPT"].includes(state) ? row.retryCount + 1 : row.retryCount,
    lastError: error?.slice(0, 1000) || null,
  };
  await put(next);
  return next;
}

export async function enqueueExternalOfflineEvidence(
  model: Pick<ExternalAuditorFieldworkModel, "audit_id" | "participant_id">,
  item: Pick<ExternalAuditorFieldworkItem, "checklist_item_id">,
  file: File,
  description?: string | null,
): Promise<ExternalOfflineEvidenceEntry> {
  if (file.size > MAX_BYTES) throw new Error("Evidence exceeds the 50 MB offline storage limit.");
  const db = await openDb();
  try {
    const key = await keyFor(db);
    const id = createEvidenceMutationId();
    const capturedAt = new Date().toISOString();
    const metadata = await encryptJson(key, { description: description?.trim() || null });
    const encryptedFile = await encryptFile(key, file);
    const row: StoredEntry = {
      id,
      auditId: model.audit_id,
      participantId: model.participant_id,
      checklistItemId: item.checklist_item_id,
      filename: file.name,
      contentType: file.type || "application/octet-stream",
      sizeBytes: file.size,
      sha256: await sha256(file),
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
    return publicRow(row);
  } finally {
    db.close();
  }
}

export async function listExternalOfflineEvidence(
  scope: ExternalAuditOutboxScope,
  checklistItemId?: string,
): Promise<ExternalOfflineEvidenceEntry[]> {
  return (await rows(scope, checklistItemId)).map(publicRow);
}

export async function clearExternalOfflineEvidence(scope: ExternalAuditOutboxScope): Promise<void> {
  const existing = await rows(scope);
  const db = await openDb();
  try {
    const tx = db.transaction(ENTRY_STORE, "readwrite");
    existing.forEach((row) => tx.objectStore(ENTRY_STORE).delete(row.id));
    await transactionDone(tx);
  } finally {
    db.close();
  }
}

export async function replayExternalOfflineEvidence(
  expectedScope: ExternalAuditOutboxScope,
): Promise<{ uploaded: AuditEvidenceArtifact[]; failed: number; conflicts: number; deferred: number }> {
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    return { uploaded: [], failed: 0, conflicts: 0, deferred: 0 };
  }

  const fresh = await getExternalAuditorFieldwork();
  if (fresh.audit_id !== expectedScope.auditId || fresh.participant_id !== expectedScope.participantId) {
    throw new Error("The external audit identity changed. Local evidence was not replayed into the new session.");
  }
  const pendingMutations = await listExternalAuditMutations(expectedScope);
  const currentByItem = new Map(fresh.items.map((item) => [item.checklist_item_id, item]));
  const uploaded: AuditEvidenceArtifact[] = [];
  let failed = 0;
  let conflicts = 0;
  let deferred = 0;

  for (let row of await rows(expectedScope)) {
    if (pendingMutations.some((entry) => entry.mutation.checklistItemId === row.checklistItemId)) {
      deferred += 1;
      continue;
    }
    const current = currentByItem.get(row.checklistItemId);
    if (!current) {
      await updateState(row, "CONFLICT", "This checklist item is no longer assigned to the active external auditor.");
      conflicts += 1;
      continue;
    }

    const db = await openDb();
    let file: File;
    let metadata: { description?: string | null };
    try {
      const key = await keyFor(db);
      metadata = await decryptJson<{ description?: string | null }>(key, row.metadataIv, row.metadataCiphertext);
      file = await decryptFile(key, row);
    } catch (error) {
      await updateState(row, "CORRUPT", error instanceof Error ? error.message : "Local evidence could not be decrypted.");
      failed += 1;
      db.close();
      continue;
    }
    db.close();

    row = await updateState(row, "UPLOADING", null);
    try {
      const result = await uploadExternalAuditorEvidence(
        fresh,
        current,
        file,
        metadata.description || null,
        row.id,
      );
      if (result.artifact.sha256.toLowerCase() !== row.sha256.toLowerCase()) {
        await updateState(row, "CORRUPT", "Server evidence hash does not match the locally captured file.");
        failed += 1;
        continue;
      }
      uploaded.push(result.artifact);
      current.entity_version = result.committed_version;
      await remove(row.id);
    } catch (error) {
      const message = error instanceof Error ? error.message : "External evidence synchronization failed.";
      const normalized = message.toLowerCase();
      if (normalized.includes("version") || normalized.includes("conflict") || normalized.includes("no longer")) {
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
