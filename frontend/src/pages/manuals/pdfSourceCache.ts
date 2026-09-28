import { authHeaders, getCachedUser } from "../../services/auth";
import { getApiBaseUrl } from "../../services/config";
import type { PdfWorkingCopyIdentity } from "./pdfWorkingCopyStore";

const LEGACY_CACHE_NAME = "amo-controlled-pdf-source-cache-v1";
const DB_NAME = "amo-controlled-pdf-offline";
const DB_VERSION = 2;
const DOCUMENT_STORE = "documents";
const CHUNK_STORE = "chunks";
const KEY_STORE = "keys";
const DEVICE_KEY_ID = "controlled-pdf-device-key-v1";
const CHUNK_BYTES = 4 * 1024 * 1024;
const CACHE_REOPEN_BATCH_CHUNKS = 8;
const MAX_SINGLE_DOCUMENT_BYTES = 512 * 1024 * 1024;
const MAX_USER_CACHE_BYTES = 1536 * 1024 * 1024;
const MAX_USER_CACHE_ENTRIES = 6;
const CACHE_MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000;

type OfflinePdfDocument = {
  key: string;
  owner: string;
  identityKey?: string;
  readerUrl?: string;
  sourceSha256: string;
  blobKey: string;
  cachedAt: number;
  lastOpenedAt: number;
  byteLength: number;
  chunkCount: number;
  contentType: string;
};

type OfflinePdfChunk = {
  id: string;
  blobKey: string;
  index: number;
  iv: ArrayBuffer;
  ciphertext: ArrayBuffer;
  plainLength: number;
};

const inFlight = new Map<string, Promise<boolean>>();
let databasePromise: Promise<IDBDatabase> | null = null;
let deviceKeyPromise: Promise<CryptoKey> | null = null;
let legacyCacheRemoved = false;

function ownerId(identity: PdfWorkingCopyIdentity): string {
  return String(identity.userId || getCachedUser()?.id || "anonymous");
}

function documentIdentityKey(identity: PdfWorkingCopyIdentity): string {
  return [
    ownerId(identity),
    identity.tenant.toLowerCase(),
    identity.manualId,
    identity.revisionId,
  ].map((value) => encodeURIComponent(value)).join("/");
}

function variantKey(readerUrl: string): string {
  let hash = 2166136261;
  for (let index = 0; index < readerUrl.length; index += 1) {
    hash ^= readerUrl.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash >>> 0).toString(36);
}

function cacheKey(
  identity: PdfWorkingCopyIdentity,
  sourceSha256: string,
  readerUrl: string,
): string {
  return [
    ownerId(identity),
    identity.tenant.toLowerCase(),
    identity.manualId,
    identity.revisionId,
    sourceSha256.toLowerCase(),
    variantKey(readerUrl),
  ].map((value) => encodeURIComponent(value)).join("/");
}

function authenticatedReaderUrl(
  path: string,
  identity: PdfWorkingCopyIdentity,
  sourceSha256: string,
): string {
  const absolute = /^https?:\/\//i.test(path) ? path : `${getApiBaseUrl()}${path}`;
  const origin = typeof window === "undefined" ? "https://amo.invalid" : window.location.origin;
  const url = new URL(absolute, origin);
  if (!url.searchParams.has("reader_user")) url.searchParams.set("reader_user", ownerId(identity));
  if (!url.searchParams.has("reader_source_sha256")) {
    url.searchParams.set("reader_source_sha256", sourceSha256.toLowerCase());
  }
  return url.toString();
}

function offlineStorageAvailable(): boolean {
  return typeof window !== "undefined"
    && typeof indexedDB !== "undefined"
    && Boolean(globalThis.crypto?.subtle);
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("Offline PDF storage request failed."));
  });
}

function transactionDone(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onabort = () => reject(transaction.error || new Error("Offline PDF storage was aborted."));
    transaction.onerror = () => reject(transaction.error || new Error("Offline PDF storage failed."));
  });
}

async function removeLegacyPlaintextCache(): Promise<void> {
  if (legacyCacheRemoved || typeof caches === "undefined") return;
  legacyCacheRemoved = true;
  await caches.delete(LEGACY_CACHE_NAME).catch(() => false);
}

function openDatabase(): Promise<IDBDatabase> {
  if (!offlineStorageAvailable()) return Promise.reject(new Error("Secure offline storage is unavailable."));
  if (databasePromise) return databasePromise;
  databasePromise = new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      let documents: IDBObjectStore;
      if (!database.objectStoreNames.contains(DOCUMENT_STORE)) {
        documents = database.createObjectStore(DOCUMENT_STORE, { keyPath: "key" });
        documents.createIndex("byOwner", "owner", { unique: false });
      } else {
        documents = request.transaction!.objectStore(DOCUMENT_STORE);
      }
      if (!documents.indexNames.contains("byIdentity")) {
        documents.createIndex("byIdentity", "identityKey", { unique: false });
      }
      if (!database.objectStoreNames.contains(CHUNK_STORE)) {
        const chunks = database.createObjectStore(CHUNK_STORE, { keyPath: "id" });
        chunks.createIndex("byBlobKey", "blobKey", { unique: false });
      }
      if (!database.objectStoreNames.contains(KEY_STORE)) {
        database.createObjectStore(KEY_STORE, { keyPath: "id" });
      }
    };
    request.onsuccess = () => {
      request.result.onversionchange = () => {
        request.result.close();
        databasePromise = null;
        deviceKeyPromise = null;
      };
      resolve(request.result);
    };
    request.onerror = () => {
      databasePromise = null;
      reject(request.error || new Error("Secure offline storage could not be opened."));
    };
    request.onblocked = () => {
      databasePromise = null;
      reject(new Error("Close other portal tabs before upgrading offline storage."));
    };
  });
  void removeLegacyPlaintextCache();
  return databasePromise;
}

async function deviceKey(database: IDBDatabase): Promise<CryptoKey> {
  if (deviceKeyPromise) return deviceKeyPromise;
  const loadOrCreate = async (): Promise<CryptoKey> => {
    const read = database.transaction(KEY_STORE, "readonly");
    const existing = await requestResult<{ id: string; key: CryptoKey } | undefined>(
      read.objectStore(KEY_STORE).get(DEVICE_KEY_ID),
    );
    await transactionDone(read);
    if (existing?.key) return existing.key;

    const generated = await crypto.subtle.generateKey(
      { name: "AES-GCM", length: 256 },
      false,
      ["encrypt", "decrypt"],
    );
    const recheck = database.transaction(KEY_STORE, "readonly");
    const createdByAnotherTab = await requestResult<{ id: string; key: CryptoKey } | undefined>(
      recheck.objectStore(KEY_STORE).get(DEVICE_KEY_ID),
    );
    await transactionDone(recheck);
    if (createdByAnotherTab?.key) return createdByAnotherTab.key;

    const write = database.transaction(KEY_STORE, "readwrite");
    write.objectStore(KEY_STORE).put({ id: DEVICE_KEY_ID, key: generated });
    await transactionDone(write);
    return generated;
  };
  const locks = (navigator as Navigator & {
    locks?: { request<T>(name: string, callback: () => T | PromiseLike<T>): Promise<T> };
  }).locks;
  const pending: Promise<CryptoKey> = locks
    ? locks.request<CryptoKey>("amo-controlled-pdf-device-key", loadOrCreate)
    : loadOrCreate();
  deviceKeyPromise = pending;
  return pending;
}

function additionalData(key: string, sourceSha256: string, index: number): ArrayBuffer {
  const encoded = new TextEncoder().encode(`${key}\n${sourceSha256.toLowerCase()}\n${index}`);
  const bytes = new Uint8Array(encoded.byteLength);
  bytes.set(encoded);
  return bytes.buffer;
}

function hex(bytes: ArrayBuffer): string {
  return [...new Uint8Array(bytes)].map((value) => value.toString(16).padStart(2, "0")).join("");
}

async function sha256(bytes: ArrayBuffer): Promise<string> {
  return hex(await crypto.subtle.digest("SHA-256", bytes));
}

async function documentRow(database: IDBDatabase, key: string): Promise<OfflinePdfDocument | null> {
  const transaction = database.transaction(DOCUMENT_STORE, "readonly");
  const row = await requestResult<OfflinePdfDocument | undefined>(
    transaction.objectStore(DOCUMENT_STORE).get(key),
  );
  await transactionDone(transaction);
  return row || null;
}

async function identityRows(database: IDBDatabase, identity: PdfWorkingCopyIdentity): Promise<OfflinePdfDocument[]> {
  const transaction = database.transaction(DOCUMENT_STORE, "readonly");
  const rows = await requestResult<OfflinePdfDocument[]>(
    transaction.objectStore(DOCUMENT_STORE).index("byIdentity").getAll(documentIdentityKey(identity)),
  );
  await transactionDone(transaction);
  return rows;
}

function validDocumentRow(
  row: OfflinePdfDocument,
  identity: PdfWorkingCopyIdentity,
  sourceSha256?: string,
): boolean {
  return row.owner === ownerId(identity)
    && (!sourceSha256 || row.sourceSha256 === sourceSha256.toLowerCase())
    && row.byteLength > 0
    && row.byteLength <= MAX_SINGLE_DOCUMENT_BYTES
    && row.chunkCount > 0
    && Date.now() - row.cachedAt <= CACHE_MAX_AGE_MS;
}

async function deleteBlobChunks(database: IDBDatabase, blobKey: string): Promise<void> {
  if (!blobKey) return;
  const transaction = database.transaction(CHUNK_STORE, "readwrite");
  const index = transaction.objectStore(CHUNK_STORE).index("byBlobKey");
  await new Promise<void>((resolve, reject) => {
    const cursor = index.openKeyCursor(IDBKeyRange.only(blobKey));
    cursor.onsuccess = () => {
      const result = cursor.result;
      if (!result) {
        resolve();
        return;
      }
      transaction.objectStore(CHUNK_STORE).delete(result.primaryKey);
      result.continue();
    };
    cursor.onerror = () => reject(cursor.error || new Error("Offline PDF chunks could not be removed."));
  });
  await transactionDone(transaction);
}

async function deleteDocumentRow(database: IDBDatabase, row: OfflinePdfDocument): Promise<void> {
  const transaction = database.transaction(DOCUMENT_STORE, "readwrite");
  transaction.objectStore(DOCUMENT_STORE).delete(row.key);
  await transactionDone(transaction);
  await deleteBlobChunks(database, row.blobKey);
}

async function pruneOwner(database: IDBDatabase, owner: string, protectedKey?: string): Promise<void> {
  const transaction = database.transaction(DOCUMENT_STORE, "readonly");
  const rows = await requestResult<OfflinePdfDocument[]>(
    transaction.objectStore(DOCUMENT_STORE).index("byOwner").getAll(owner),
  );
  await transactionDone(transaction);
  rows.sort((left, right) => right.lastOpenedAt - left.lastOpenedAt);

  let retainedBytes = 0;
  let retainedEntries = 0;
  for (const row of rows) {
    const keepProtected = row.key === protectedKey;
    const expired = Date.now() - row.cachedAt > CACHE_MAX_AGE_MS;
    const exceedsEntryLimit = retainedEntries >= MAX_USER_CACHE_ENTRIES;
    const exceedsByteLimit = retainedBytes + row.byteLength > MAX_USER_CACHE_BYTES;
    if (!keepProtected && (expired || exceedsEntryLimit || exceedsByteLimit)) {
      await deleteDocumentRow(database, row);
      continue;
    }
    retainedBytes += row.byteLength;
    retainedEntries += 1;
  }
}

async function updateLastOpened(database: IDBDatabase, row: OfflinePdfDocument): Promise<void> {
  const transaction = database.transaction(DOCUMENT_STORE, "readwrite");
  transaction.objectStore(DOCUMENT_STORE).put({ ...row, lastOpenedAt: Date.now() });
  await transactionDone(transaction);
}

export async function hasCachedPdfSource(
  identity: PdfWorkingCopyIdentity,
  sourceSha256: string,
  readerUrl: string,
): Promise<boolean> {
  if (!offlineStorageAvailable() || !sourceSha256.trim()) return false;
  try {
    const database = await openDatabase();
    const row = await documentRow(database, cacheKey(identity, sourceSha256, readerUrl));
    if (!row) return false;
    const valid = validDocumentRow(row, identity, sourceSha256);
    if (!valid) await deleteDocumentRow(database, row);
    return valid;
  } catch {
    return false;
  }
}

export async function readCachedPdfSource(
  identity: PdfWorkingCopyIdentity,
  sourceSha256: string,
  readerUrl: string,
): Promise<ArrayBuffer | null> {
  if (!offlineStorageAvailable() || !sourceSha256.trim()) return null;
  try {
    const database = await openDatabase();
    const key = cacheKey(identity, sourceSha256, readerUrl);
    const row = await documentRow(database, key);
    if (!row || !(await hasCachedPdfSource(identity, sourceSha256, readerUrl))) return null;
    const encryptionKey = await deviceKey(database);

    // Reopen cached manuals in bounded batches. One transaction per chunk was
    // slow for thousand-page PDFs; loading the entire encrypted file at once
    // can double/triple memory pressure. Eight 4 MiB chunks balances both.
    const output = new Uint8Array(row.byteLength);
    let offset = 0;
    for (let batchStart = 0; batchStart < row.chunkCount; batchStart += CACHE_REOPEN_BATCH_CHUNKS) {
      const batchEnd = Math.min(row.chunkCount, batchStart + CACHE_REOPEN_BATCH_CHUNKS);
      const transaction = database.transaction(CHUNK_STORE, "readonly");
      const store = transaction.objectStore(CHUNK_STORE);
      const requests: Array<Promise<OfflinePdfChunk | undefined>> = [];
      for (let index = batchStart; index < batchEnd; index += 1) {
        requests.push(requestResult<OfflinePdfChunk | undefined>(
          store.get(`${row.blobKey}:${index}`),
        ));
      }
      const chunks = await Promise.all(requests);
      await transactionDone(transaction);
      if (chunks.some((chunk, relativeIndex) => (
        !chunk
        || chunk.index !== batchStart + relativeIndex
        || chunk.plainLength <= 0
      ))) {
        await deleteDocumentRow(database, row);
        return null;
      }

      const plainChunks = await Promise.all(chunks.map(async (chunk) => {
        if (!chunk) throw new Error("Cached PDF chunk is unavailable.");
        const plain = await crypto.subtle.decrypt(
          {
            name: "AES-GCM",
            iv: chunk.iv,
            additionalData: additionalData(key, row.sourceSha256, chunk.index),
          },
          encryptionKey,
          chunk.ciphertext,
        );
        if (plain.byteLength !== chunk.plainLength) {
          throw new Error("Cached PDF chunk failed authenticated decryption.");
        }
        return plain;
      }));

      for (const plain of plainChunks) {
        if (offset + plain.byteLength > output.byteLength) {
          await deleteDocumentRow(database, row);
          return null;
        }
        output.set(new Uint8Array(plain), offset);
        offset += plain.byteLength;
      }
    }

    // Every stored chunk is authenticated with AES-GCM using the controlled
    // checksum and chunk index as additional data. The complete source was
    // checksum-verified when it entered this cache, so re-hashing hundreds of
    // megabytes on every open only adds latency without increasing local
    // corruption detection.
    if (offset !== row.byteLength) {
      await deleteDocumentRow(database, row);
      return null;
    }
    void updateLastOpened(database, row).catch(() => undefined);
    return output.buffer;
  } catch {
    return null;
  }
}

export type LatestCachedPdfSource = {
  bytes: ArrayBuffer;
  sourceSha256: string;
  readerUrl: string;
  byteLength: number;
};

export async function readLatestCachedPdfSource(
  identity: PdfWorkingCopyIdentity,
): Promise<LatestCachedPdfSource | null> {
  if (!offlineStorageAvailable()) return null;
  try {
    const database = await openDatabase();
    const rows = (await identityRows(database, identity))
      .sort((left, right) => right.lastOpenedAt - left.lastOpenedAt);
    for (const row of rows) {
      if (!validDocumentRow(row, identity) || !row.readerUrl) {
        await deleteDocumentRow(database, row);
        continue;
      }
      const bytes = await readCachedPdfSource(identity, row.sourceSha256, row.readerUrl);
      if (bytes) {
        return {
          bytes,
          sourceSha256: row.sourceSha256,
          readerUrl: row.readerUrl,
          byteLength: row.byteLength,
        };
      }
    }
    return null;
  } catch {
    return null;
  }
}

async function storePdfSource(
  identity: PdfWorkingCopyIdentity,
  sourceSha256: string,
  readerUrl: string,
  expectedBytes?: number | null,
): Promise<boolean> {
  if (!offlineStorageAvailable() || !sourceSha256.trim() || /^(?:blob:|data:)/i.test(readerUrl)) {
    throw new Error("This document source cannot be retained for offline use.");
  }
  const expectedFingerprint = sourceSha256.toLowerCase();
  const expected = Number(expectedBytes || 0);
  if (expected > MAX_SINGLE_DOCUMENT_BYTES) {
    throw new Error("This controlled PDF exceeds the offline document limit.");
  }

  const database = await openDatabase();
  const key = cacheKey(identity, expectedFingerprint, readerUrl);
  if (await hasCachedPdfSource(identity, expectedFingerprint, readerUrl)) return true;

  if (navigator.storage?.persist) await navigator.storage.persist().catch(() => false);
  if (navigator.storage?.estimate) {
    const estimate = await navigator.storage.estimate().catch(() => null);
    if (estimate?.quota && expected > 0) {
      const usage = Number(estimate.usage || 0);
      if (estimate.quota - usage < expected * 1.15) {
        throw new Error("This device does not have enough storage for the offline PDF.");
      }
    }
  }

  const headers = new Headers(authHeaders());
  headers.delete("Range");
  const response = await fetch(authenticatedReaderUrl(readerUrl, identity, expectedFingerprint), {
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok || response.status === 206) {
    throw new Error(`The complete controlled PDF could not be retrieved (${response.status}).`);
  }

  const declaredFingerprint = String(
    response.headers.get("X-Reader-SHA256")
      || response.headers.get("X-PDF-Reader-SHA256")
      || "",
  ).trim().toLowerCase();
  if (declaredFingerprint && declaredFingerprint !== expectedFingerprint) {
    throw new Error("The retrieved PDF does not match the verified controlled revision.");
  }

  const contentLength = Number(response.headers.get("Content-Length") || 0);
  if (contentLength > MAX_SINGLE_DOCUMENT_BYTES) {
    throw new Error("The controlled PDF exceeds the offline document limit.");
  }
  if (expected > 0 && contentLength > 0 && Math.abs(contentLength - expected) > Math.max(1024, expected * 0.02)) {
    throw new Error("The retrieved PDF size does not match the controlled revision.");
  }

  const encryptionKey = await deviceKey(database);
  const blobKey = `${key}:${Date.now()}:${crypto.randomUUID()}`;
  let chunkIndex = 0;
  let totalBytes = 0;

  const persistChunk = async (plain: ArrayBuffer): Promise<void> => {
    if (!plain.byteLength) return;
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const ciphertext = await crypto.subtle.encrypt(
      {
        name: "AES-GCM",
        iv,
        additionalData: additionalData(key, expectedFingerprint, chunkIndex),
      },
      encryptionKey,
      plain,
    );
    const transaction = database.transaction(CHUNK_STORE, "readwrite");
    transaction.objectStore(CHUNK_STORE).put({
      id: `${blobKey}:${chunkIndex}`,
      blobKey,
      index: chunkIndex,
      iv: iv.buffer,
      ciphertext,
      plainLength: plain.byteLength,
    } satisfies OfflinePdfChunk);
    await transactionDone(transaction);
    chunkIndex += 1;
    totalBytes += plain.byteLength;
    if (totalBytes > MAX_SINGLE_DOCUMENT_BYTES) {
      throw new Error("The controlled PDF exceeds the offline document limit.");
    }
  };

  try {
    if (response.body && declaredFingerprint === expectedFingerprint) {
      // Stream directly from the authenticated immutable reader endpoint into
      // encrypted IndexedDB chunks. This avoids holding a 1000-page manual in
      // one giant ArrayBuffer while it downloads in the background.
      const reader = response.body.getReader();
      let pending = new Uint8Array(0);
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        if (!value?.byteLength) continue;
        const combined = new Uint8Array(pending.byteLength + value.byteLength);
        combined.set(pending, 0);
        combined.set(value, pending.byteLength);
        let offset = 0;
        while (combined.byteLength - offset >= CHUNK_BYTES) {
          const slice = combined.slice(offset, offset + CHUNK_BYTES);
          await persistChunk(slice.buffer);
          offset += CHUNK_BYTES;
        }
        pending = combined.slice(offset);
      }
      if (pending.byteLength) await persistChunk(pending.buffer);
    } else {
      // Compatibility path for older/proxy endpoints that cannot expose the
      // verified checksum header. Verify the complete payload locally once.
      const bytes = await response.arrayBuffer();
      if (!bytes.byteLength || bytes.byteLength > MAX_SINGLE_DOCUMENT_BYTES) {
        throw new Error("The controlled PDF is empty or exceeds the offline document limit.");
      }
      const actualSha256 = await sha256(bytes);
      if (actualSha256 !== expectedFingerprint) {
        throw new Error("The retrieved PDF failed its controlled-revision checksum.");
      }
      for (let offset = 0; offset < bytes.byteLength; offset += CHUNK_BYTES) {
        await persistChunk(bytes.slice(offset, Math.min(bytes.byteLength, offset + CHUNK_BYTES)));
      }
    }

    if (!totalBytes || (expected > 0 && Math.abs(totalBytes - expected) > Math.max(1024, expected * 0.02))) {
      throw new Error("The retrieved PDF size does not match the controlled revision.");
    }

    const previous = await documentRow(database, key);
    const now = Date.now();
    const transaction = database.transaction(DOCUMENT_STORE, "readwrite");
    transaction.objectStore(DOCUMENT_STORE).put({
      key,
      owner: ownerId(identity),
      identityKey: documentIdentityKey(identity),
      readerUrl,
      sourceSha256: expectedFingerprint,
      blobKey,
      cachedAt: now,
      lastOpenedAt: now,
      byteLength: totalBytes,
      chunkCount: chunkIndex,
      contentType: response.headers.get("Content-Type") || "application/pdf",
    } satisfies OfflinePdfDocument);
    await transactionDone(transaction);
    if (previous?.blobKey && previous.blobKey !== blobKey) {
      await deleteBlobChunks(database, previous.blobKey);
    }
    await pruneOwner(database, ownerId(identity), key);
    return true;
  } catch (error) {
    await deleteBlobChunks(database, blobKey).catch(() => undefined);
    throw error;
  }
}

export function savePdfSourceOffline(
  identity: PdfWorkingCopyIdentity,
  sourceSha256: string,
  readerUrl: string,
  expectedBytes?: number | null,
): Promise<boolean> {
  const key = cacheKey(identity, sourceSha256, readerUrl);
  const existing = inFlight.get(key);
  if (existing) return existing;
  const task = storePdfSource(identity, sourceSha256, readerUrl, expectedBytes)
    .finally(() => {
      if (inFlight.get(key) === task) inFlight.delete(key);
    });
  inFlight.set(key, task);
  return task;
}

export async function deleteCachedPdfSource(
  identity: PdfWorkingCopyIdentity,
  sourceSha256: string,
  readerUrl: string,
): Promise<void> {
  if (!offlineStorageAvailable() || !sourceSha256.trim()) return;
  const database = await openDatabase();
  const row = await documentRow(database, cacheKey(identity, sourceSha256, readerUrl));
  if (row) await deleteDocumentRow(database, row);
}
