import { getCachedUser } from "../../services/auth";

const DATABASE_NAME = "amo-controlled-pdf-working-copies";
const STORE_NAME = "workingCopies";
const DATABASE_VERSION = 1;
export const MAX_PDF_WORKING_COPY_BYTES = 100 * 1024 * 1024;

export type PdfWorkingCopyIdentity = {
  tenant: string;
  manualId: string;
  revisionId: string;
  userId?: string | null;
};

export type StoredPdfWorkingCopy = {
  key: string;
  userId: string;
  tenant: string;
  manualId: string;
  revisionId: string;
  filename: string;
  sourceSha256?: string | null;
  savedAt: string;
  byteLength: number;
  bytes: ArrayBuffer;
};

export function pdfWorkingCopyKey(identity: PdfWorkingCopyIdentity): string {
  const userId = String(identity.userId || getCachedUser()?.id || "anonymous");
  return [
    "pdf-working-copy:v1",
    encodeURIComponent(userId),
    encodeURIComponent(identity.tenant.toLowerCase()),
    encodeURIComponent(identity.manualId),
    encodeURIComponent(identity.revisionId),
  ].join(":");
}

function normalizedIdentity(identity: PdfWorkingCopyIdentity) {
  return {
    userId: String(identity.userId || getCachedUser()?.id || "anonymous"),
    tenant: identity.tenant.toLowerCase(),
    manualId: identity.manualId,
    revisionId: identity.revisionId,
  };
}

function openDatabase(): Promise<IDBDatabase> {
  if (typeof indexedDB === "undefined") return Promise.reject(new Error("IndexedDB is unavailable"));
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    request.onerror = () => reject(request.error || new Error("PDF working-copy storage could not be opened"));
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(STORE_NAME)) {
        const store = database.createObjectStore(STORE_NAME, { keyPath: "key" });
        store.createIndex("byUserTenant", ["userId", "tenant"], { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
  });
}

async function transact<T>(
  mode: IDBTransactionMode,
  operation: (store: IDBObjectStore, resolve: (value: T) => void, reject: (reason?: unknown) => void) => void,
): Promise<T> {
  const database = await openDatabase();
  return new Promise<T>((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, mode);
    const store = transaction.objectStore(STORE_NAME);
    let settled = false;
    const finish = (value: T) => { if (!settled) { settled = true; resolve(value); } };
    const fail = (reason?: unknown) => { if (!settled) { settled = true; reject(reason); } };
    transaction.onerror = () => fail(transaction.error || new Error("PDF working-copy storage failed"));
    transaction.onabort = () => fail(transaction.error || new Error("PDF working-copy storage was cancelled"));
    transaction.oncomplete = () => database.close();
    operation(store, finish, fail);
  }).finally(() => database.close());
}

export async function readPdfWorkingCopy(identity: PdfWorkingCopyIdentity): Promise<StoredPdfWorkingCopy | null> {
  const key = pdfWorkingCopyKey(identity);
  return transact<StoredPdfWorkingCopy | null>("readonly", (store, resolve, reject) => {
    const request = store.get(key);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve((request.result as StoredPdfWorkingCopy | undefined) || null);
  });
}

export async function savePdfWorkingCopy(
  identity: PdfWorkingCopyIdentity,
  filename: string,
  bytes: ArrayBuffer,
  sourceSha256?: string | null,
): Promise<StoredPdfWorkingCopy> {
  if (bytes.byteLength > MAX_PDF_WORKING_COPY_BYTES) {
    throw new Error("The PDF working copy exceeds the 100 MB local draft limit");
  }
  const normalized = normalizedIdentity(identity);
  const row: StoredPdfWorkingCopy = {
    key: pdfWorkingCopyKey({ ...identity, userId: normalized.userId }),
    ...normalized,
    filename,
    sourceSha256,
    savedAt: new Date().toISOString(),
    byteLength: bytes.byteLength,
    bytes,
  };
  await transact<void>("readwrite", (store, resolve, reject) => {
    const request = store.put(row);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve();
  });
  return row;
}

export async function deletePdfWorkingCopy(identity: PdfWorkingCopyIdentity): Promise<void> {
  const key = pdfWorkingCopyKey(identity);
  await transact<void>("readwrite", (store, resolve, reject) => {
    const request = store.delete(key);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve();
  });
}
