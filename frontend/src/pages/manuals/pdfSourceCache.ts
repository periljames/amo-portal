import { authHeaders, getCachedUser } from "../../services/auth";
import { getApiBaseUrl } from "../../services/config";
import type { PdfWorkingCopyIdentity } from "./pdfWorkingCopyStore";

const CACHE_NAME = "amo-controlled-pdf-source-cache-v1";
const MAX_SINGLE_DOCUMENT_BYTES = 300 * 1024 * 1024;
const MAX_USER_CACHE_BYTES = 600 * 1024 * 1024;
const MAX_USER_CACHE_ENTRIES = 4;
const CACHE_MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000;

const inFlight = new Map<string, Promise<boolean>>();

type CachedPdfMetadata = {
  key: string;
  owner: string;
  sourceSha256: string;
  cachedAt: number;
  byteLength: number;
};

function ownerId(identity: PdfWorkingCopyIdentity): string {
  return String(identity.userId || getCachedUser()?.id || "anonymous");
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
  const origin = typeof window === "undefined" ? "https://amo.invalid" : window.location.origin;
  const owner = ownerId(identity);
  const parts = [
    owner,
    identity.tenant.toLowerCase(),
    identity.manualId,
    identity.revisionId,
    sourceSha256.toLowerCase(),
    variantKey(readerUrl),
  ].map((value) => encodeURIComponent(value));
  return `${origin}/__amo_pdf_source_cache__/v1/${parts.join("/")}`;
}

function authenticatedReaderUrl(path: string, identity: PdfWorkingCopyIdentity): string {
  if (/^(?:blob:|data:)/i.test(path)) return path;
  const absolute = /^https?:\/\//i.test(path) ? path : `${getApiBaseUrl()}${path}`;
  const url = new URL(absolute, typeof window === "undefined" ? "https://amo.invalid" : window.location.origin);
  if (!url.searchParams.has("reader_user")) url.searchParams.set("reader_user", ownerId(identity));
  return url.toString();
}

function cacheAvailable(): boolean {
  return typeof window !== "undefined" && typeof caches !== "undefined";
}

function metadataFromResponse(key: string, response: Response): CachedPdfMetadata | null {
  const owner = response.headers.get("X-AMO-PDF-Owner") || "";
  const sourceSha256 = response.headers.get("X-AMO-PDF-Source-SHA256") || "";
  const cachedAt = Number(response.headers.get("X-AMO-PDF-Cached-At") || 0);
  const byteLength = Number(response.headers.get("X-AMO-PDF-Bytes") || 0);
  if (!owner || !sourceSha256 || !cachedAt || !byteLength) return null;
  return { key, owner, sourceSha256, cachedAt, byteLength };
}

async function deleteEntry(cache: Cache, key: string): Promise<void> {
  try { await cache.delete(key); } catch { /* cache eviction is best effort */ }
}

async function pruneCache(cache: Cache, owner: string): Promise<void> {
  const requests = await cache.keys();
  const rows: CachedPdfMetadata[] = [];
  for (const request of requests) {
    const response = await cache.match(request);
    if (!response) continue;
    const metadata = metadataFromResponse(request.url, response);
    if (!metadata) {
      await deleteEntry(cache, request.url);
      continue;
    }
    if (metadata.owner === owner) rows.push(metadata);
  }

  rows.sort((left, right) => right.cachedAt - left.cachedAt);
  let retainedBytes = 0;
  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index];
    const expired = Date.now() - row.cachedAt > CACHE_MAX_AGE_MS;
    const exceedsEntryLimit = index >= MAX_USER_CACHE_ENTRIES;
    const exceedsByteLimit = retainedBytes + row.byteLength > MAX_USER_CACHE_BYTES;
    if (expired || exceedsEntryLimit || exceedsByteLimit) {
      await deleteEntry(cache, row.key);
      continue;
    }
    retainedBytes += row.byteLength;
  }
}

export async function readCachedPdfSource(
  identity: PdfWorkingCopyIdentity,
  sourceSha256: string,
  readerUrl: string,
): Promise<ArrayBuffer | null> {
  if (!cacheAvailable() || !sourceSha256.trim()) return null;
  const key = cacheKey(identity, sourceSha256, readerUrl);
  try {
    const cache = await caches.open(CACHE_NAME);
    const response = await cache.match(key);
    if (!response) return null;
    const metadata = metadataFromResponse(key, response);
    if (
      !metadata
      || metadata.owner !== ownerId(identity)
      || metadata.sourceSha256.toLowerCase() !== sourceSha256.toLowerCase()
      || Date.now() - metadata.cachedAt > CACHE_MAX_AGE_MS
      || metadata.byteLength > MAX_SINGLE_DOCUMENT_BYTES
    ) {
      await deleteEntry(cache, key);
      return null;
    }
    const bytes = await response.arrayBuffer();
    if (!bytes.byteLength || bytes.byteLength !== metadata.byteLength) {
      await deleteEntry(cache, key);
      return null;
    }
    return bytes;
  } catch {
    return null;
  }
}

async function warmSource(
  identity: PdfWorkingCopyIdentity,
  sourceSha256: string,
  readerUrl: string,
  expectedBytes?: number | null,
): Promise<boolean> {
  if (!cacheAvailable() || !sourceSha256.trim() || /^(?:blob:|data:)/i.test(readerUrl)) return false;
  const expected = Number(expectedBytes || 0);
  if (expected > MAX_SINGLE_DOCUMENT_BYTES) return false;

  const key = cacheKey(identity, sourceSha256, readerUrl);
  const cache = await caches.open(CACHE_NAME);
  if (await cache.match(key)) return true;

  const headers = new Headers(authHeaders());
  headers.delete("Range");
  const response = await fetch(authenticatedReaderUrl(readerUrl, identity), {
    headers,
    credentials: "same-origin",
    cache: "reload",
  });
  if (!response.ok || response.status === 206) return false;

  const blob = await response.blob();
  if (!blob.size || blob.size > MAX_SINGLE_DOCUMENT_BYTES) return false;
  if (expected > 0 && Math.abs(blob.size - expected) > Math.max(1024, expected * 0.02)) return false;

  const cachedAt = Date.now();
  const cachedResponse = new Response(blob, {
    status: 200,
    headers: {
      "Content-Type": response.headers.get("Content-Type") || "application/pdf",
      "Content-Length": String(blob.size),
      "X-AMO-PDF-Owner": ownerId(identity),
      "X-AMO-PDF-Source-SHA256": sourceSha256.toLowerCase(),
      "X-AMO-PDF-Cached-At": String(cachedAt),
      "X-AMO-PDF-Bytes": String(blob.size),
    },
  });
  await cache.put(key, cachedResponse);
  await pruneCache(cache, ownerId(identity));
  return true;
}

export function warmPdfSourceCache(
  identity: PdfWorkingCopyIdentity,
  sourceSha256: string,
  readerUrl: string,
  expectedBytes?: number | null,
): Promise<boolean> {
  const key = cacheKey(identity, sourceSha256, readerUrl);
  const existing = inFlight.get(key);
  if (existing) return existing;
  const task = warmSource(identity, sourceSha256, readerUrl, expectedBytes)
    .catch(() => false)
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
  if (!cacheAvailable() || !sourceSha256.trim()) return;
  try {
    const cache = await caches.open(CACHE_NAME);
    await cache.delete(cacheKey(identity, sourceSha256, readerUrl));
  } catch {
    // Source cache removal is best effort.
  }
}
