export type ExternalAuditOutboxScope = {
  auditId: string;
  participantId: string;
};

export type ExternalAuditOutboxMutation = {
  checklistItemId: string;
  clientMutationId: string;
  deviceId: string;
  deviceSequence: number;
  clientTimestamp: string;
  baseVersion: number;
  operation: "CHECKLIST_UPDATE";
  canonicalResponseStatus: "COMPLIANT" | "NONCOMPLIANT" | "OBSERVATION" | "NOT_APPLICABLE" | "NOT_VERIFIED";
  auditorNotes: string | null;
  evidenceReferences: Array<Record<string, unknown> | string>;
  reason: string;
};

export type ExternalAuditOutboxEntry = {
  id: string;
  scope: ExternalAuditOutboxScope;
  mutation: ExternalAuditOutboxMutation;
  createdAt: string;
  retryCount: number;
  lastError: string | null;
};

type StoredEntry = {
  id: string;
  auditId: string;
  participantId: string;
  iv: string;
  ciphertext: string;
  createdAt: string;
  retryCount: number;
  lastError: string | null;
};

const DB_NAME = "amo-qms-external-audit-outbox";
const DB_VERSION = 1;
const ENTRY_STORE = "mutations";
const KEY_STORE = "keys";
const KEY_ID = "external-audit-outbox-aes-gcm-v1";

function b64(bytes: Uint8Array): string {
  let raw = "";
  bytes.forEach((byte) => { raw += String.fromCharCode(byte); });
  return btoa(raw);
}

function fromB64(value: string): Uint8Array<ArrayBuffer> {
  const raw = atob(value);
  const bytes = new Uint8Array(raw.length);
  for (let index = 0; index < raw.length; index += 1) {
    bytes[index] = raw.charCodeAt(index);
  }
  return bytes;
}

function idbAvailable(): boolean {
  return typeof window !== "undefined" && typeof indexedDB !== "undefined" && typeof crypto !== "undefined" && !!crypto.subtle;
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
    transaction.onabort = () => reject(transaction.error || new Error("IndexedDB transaction was aborted."));
  });
}

async function openDb(): Promise<IDBDatabase> {
  if (!idbAvailable()) throw new Error("Secure offline audit storage is not available in this browser.");
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(ENTRY_STORE)) {
        const store = db.createObjectStore(ENTRY_STORE, { keyPath: "id" });
        store.createIndex("scope", ["auditId", "participantId"], { unique: false });
        store.createIndex("createdAt", "createdAt", { unique: false });
      }
      if (!db.objectStoreNames.contains(KEY_STORE)) db.createObjectStore(KEY_STORE, { keyPath: "id" });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Unable to open secure offline audit storage."));
  });
}

async function encryptionKey(db: IDBDatabase): Promise<CryptoKey> {
  const readTx = db.transaction(KEY_STORE, "readonly");
  const existing = await requestResult(readTx.objectStore(KEY_STORE).get(KEY_ID)) as { id: string; key: CryptoKey } | undefined;
  await transactionDone(readTx);
  if (existing?.key) return existing.key;

  const key = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
  const writeTx = db.transaction(KEY_STORE, "readwrite");
  writeTx.objectStore(KEY_STORE).put({ id: KEY_ID, key });
  await transactionDone(writeTx);
  return key;
}

async function encryptMutation(key: CryptoKey, mutation: ExternalAuditOutboxMutation): Promise<{ iv: string; ciphertext: string }> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const plaintext = new TextEncoder().encode(JSON.stringify(mutation));
  const encrypted = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, plaintext);
  return { iv: b64(iv), ciphertext: b64(new Uint8Array(encrypted)) };
}

async function decryptMutation(key: CryptoKey, row: StoredEntry): Promise<ExternalAuditOutboxMutation> {
  const plaintext = await crypto.subtle.decrypt({ name: "AES-GCM", iv: fromB64(row.iv) }, key, fromB64(row.ciphertext));
  return JSON.parse(new TextDecoder().decode(plaintext)) as ExternalAuditOutboxMutation;
}

export async function enqueueExternalAuditMutation(
  scope: ExternalAuditOutboxScope,
  mutation: ExternalAuditOutboxMutation,
): Promise<ExternalAuditOutboxEntry> {
  const db = await openDb();
  try {
    const key = await encryptionKey(db);
    const encrypted = await encryptMutation(key, mutation);
    const row: StoredEntry = {
      id: mutation.clientMutationId,
      auditId: scope.auditId,
      participantId: scope.participantId,
      iv: encrypted.iv,
      ciphertext: encrypted.ciphertext,
      createdAt: new Date().toISOString(),
      retryCount: 0,
      lastError: null,
    };
    const tx = db.transaction(ENTRY_STORE, "readwrite");
    tx.objectStore(ENTRY_STORE).put(row);
    await transactionDone(tx);
    return { id: row.id, scope, mutation, createdAt: row.createdAt, retryCount: 0, lastError: null };
  } finally {
    db.close();
  }
}

export async function listExternalAuditMutations(scope: ExternalAuditOutboxScope): Promise<ExternalAuditOutboxEntry[]> {
  const db = await openDb();
  try {
    const key = await encryptionKey(db);
    const tx = db.transaction(ENTRY_STORE, "readonly");
    const index = tx.objectStore(ENTRY_STORE).index("scope");
    const rows = await requestResult(index.getAll(IDBKeyRange.only([scope.auditId, scope.participantId]))) as StoredEntry[];
    await transactionDone(tx);
    const result: ExternalAuditOutboxEntry[] = [];
    for (const row of rows.sort((a, b) => a.createdAt.localeCompare(b.createdAt))) {
      try {
        result.push({
          id: row.id,
          scope,
          mutation: await decryptMutation(key, row),
          createdAt: row.createdAt,
          retryCount: row.retryCount || 0,
          lastError: row.lastError || null,
        });
      } catch {
        // A corrupt or undecryptable row must never be replayed as guessed data.
      }
    }
    return result;
  } finally {
    db.close();
  }
}

export async function removeExternalAuditMutation(id: string): Promise<void> {
  const db = await openDb();
  try {
    const tx = db.transaction(ENTRY_STORE, "readwrite");
    tx.objectStore(ENTRY_STORE).delete(id);
    await transactionDone(tx);
  } finally {
    db.close();
  }
}

export async function markExternalAuditMutationFailure(id: string, message: string): Promise<void> {
  const db = await openDb();
  try {
    const tx = db.transaction(ENTRY_STORE, "readwrite");
    const store = tx.objectStore(ENTRY_STORE);
    const row = await requestResult(store.get(id)) as StoredEntry | undefined;
    if (row) {
      row.retryCount = (row.retryCount || 0) + 1;
      row.lastError = message.slice(0, 1000);
      store.put(row);
    }
    await transactionDone(tx);
  } finally {
    db.close();
  }
}

export async function clearExternalAuditMutations(scope: ExternalAuditOutboxScope): Promise<void> {
  const db = await openDb();
  try {
    const tx = db.transaction(ENTRY_STORE, "readwrite");
    const index = tx.objectStore(ENTRY_STORE).index("scope");
    const keys = await requestResult(index.getAllKeys(IDBKeyRange.only([scope.auditId, scope.participantId])));
    keys.forEach((key) => tx.objectStore(ENTRY_STORE).delete(key));
    await transactionDone(tx);
  } finally {
    db.close();
  }
}
