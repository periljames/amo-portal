import { getCachedUser } from "../../services/auth";
import { authoritativePdfSourceChecksum } from "../../services/pdfWorkingCopyAuthority";

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

function closeQuietly(database: IDBDatabase): void {
  try { database.close(); } catch { /* already closed */ }
}

function authorizedDraft(
  identity: PdfWorkingCopyIdentity,
  result: StoredPdfWorkingCopy | null,
): StoredPdfWorkingCopy | null {
  if (!result) return null;
  const authoritative = authoritativePdfSourceChecksum(identity.tenant, identity.manualId, identity.revisionId);
  const stored = String(result.sourceSha256 || "").trim().toLowerCase();
  if (!authoritative || !stored || stored !== authoritative) return null;
  return result;
}

export async function readPdfWorkingCopy(identity: PdfWorkingCopyIdentity): Promise<StoredPdfWorkingCopy | null> {
  // Draft bytes are never exposed until the capability request has registered
  // the immutable source checksum for this exact tenant/document/revision.
  if (!authoritativePdfSourceChecksum(identity.tenant, identity.manualId, identity.revisionId)) return null;
  const database = await openDatabase();
  const key = pdfWorkingCopyKey(identity);
  return new Promise<StoredPdfWorkingCopy | null>((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, "readonly");
    const request = transaction.objectStore(STORE_NAME).get(key);
    let result: StoredPdfWorkingCopy | null = null;
    request.onsuccess = () => { result = (request.result as StoredPdfWorkingCopy | undefined) || null; };
    request.onerror = () => reject(request.error || new Error("The PDF working copy could not be read"));
    transaction.oncomplete = () => { closeQuietly(database); resolve(authorizedDraft(identity, result)); };
    transaction.onerror = () => { closeQuietly(database); reject(transaction.error || new Error("PDF working-copy storage failed")); };
    transaction.onabort = () => { closeQuietly(database); reject(transaction.error || new Error("PDF working-copy storage was cancelled")); };
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
  const authoritative = authoritativePdfSourceChecksum(identity.tenant, identity.manualId, identity.revisionId);
  const requestedChecksum = String(sourceSha256 || "").trim().toLowerCase();
  if (!authoritative || !requestedChecksum || requestedChecksum !== authoritative) {
    throw new Error("The PDF working copy cannot be saved without the authoritative source checksum");
  }
  const normalized = normalizedIdentity(identity);
  const row: StoredPdfWorkingCopy = {
    key: pdfWorkingCopyKey({ ...identity, userId: normalized.userId }),
    ...normalized,
    filename,
    sourceSha256: authoritative,
    savedAt: new Date().toISOString(),
    byteLength: bytes.byteLength,
    bytes,
  };
  const database = await openDatabase();
  return new Promise<StoredPdfWorkingCopy>((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, "readwrite");
    const request = transaction.objectStore(STORE_NAME).put(row);
    request.onerror = () => reject(request.error || new Error("The PDF working copy could not be written"));
    transaction.oncomplete = () => { closeQuietly(database); resolve(row); };
    transaction.onerror = () => { closeQuietly(database); reject(transaction.error || new Error("PDF working-copy storage failed")); };
    transaction.onabort = () => { closeQuietly(database); reject(transaction.error || new Error("PDF working-copy storage was cancelled")); };
  });
}

export async function deletePdfWorkingCopy(identity: PdfWorkingCopyIdentity): Promise<void> {
  const database = await openDatabase();
  const key = pdfWorkingCopyKey(identity);
  return new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, "readwrite");
    const request = transaction.objectStore(STORE_NAME).delete(key);
    request.onerror = () => reject(request.error || new Error("The PDF working copy could not be deleted"));
    transaction.oncomplete = () => { closeQuietly(database); resolve(); };
    transaction.onerror = () => { closeQuietly(database); reject(transaction.error || new Error("PDF working-copy storage failed")); };
    transaction.onabort = () => { closeQuietly(database); reject(transaction.error || new Error("PDF working-copy storage was cancelled")); };
  });
}
