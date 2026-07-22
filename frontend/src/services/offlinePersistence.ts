import { authHeaders, getActiveAmoId, getCachedUser, getContext, getToken } from "./auth";
import { getApiBaseUrl } from "./config";

const DATABASE_NAME = "amo-portal-offline";
const DATABASE_VERSION = 1;
const KV_STORE = "key_value";
const API_STORE = "api_cache";
const OUTBOX_STORE = "outbox";
const QUERY_CACHE_KEY = "tanstack-query-cache-v2";
const OFFLINE_EVENT = "amo:offline-state-changed";
const REPLAY_LEASE_KEY = "amo:offline-replay-lease";
const REPLAY_LEASE_MS = 20_000;

export type OfflineOutboxStatus = "queued" | "syncing" | "conflict" | "failed";

export type OfflineOutboxEntry = {
  id: string;
  scope: string;
  path: string;
  method: string;
  headers: Record<string, string>;
  body?: string;
  createdAt: number;
  updatedAt: number;
  attempts: number;
  status: OfflineOutboxStatus;
  entityType?: string;
  entityId?: string;
  idempotencyKey: string;
  error?: string;
  conflict?: unknown;
};

export type OfflineOutboxSummary = {
  queued: number;
  syncing: number;
  conflict: number;
  failed: number;
  total: number;
};

export type ApiCacheRecord<T = unknown> = {
  key: string;
  scope: string;
  path: string;
  value: T;
  storedAt: number;
  expiresAt: number;
};

type KeyValueRecord = {
  key: string;
  scope: string;
  value: unknown;
  updatedAt: number;
};

type QueryPersister = {
  persistClient(client: unknown): Promise<void>;
  restoreClient(): Promise<unknown | undefined>;
  removeClient(): Promise<void>;
};

let databasePromise: Promise<IDBDatabase | null> | null = null;
let memoryQueryCache: unknown;
const memoryApiCache = new Map<string, ApiCacheRecord>();
const memoryOutbox = new Map<string, OfflineOutboxEntry>();

function canUseIndexedDb(): boolean {
  return typeof window !== "undefined" && typeof window.indexedDB !== "undefined";
}

function requestResult<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("IndexedDB request failed"));
  });
}

function transactionDone(transaction: IDBTransaction): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error || new Error("IndexedDB transaction failed"));
    transaction.onabort = () => reject(transaction.error || new Error("IndexedDB transaction aborted"));
  });
}

async function openDatabase(): Promise<IDBDatabase | null> {
  if (!canUseIndexedDb()) return null;
  if (databasePromise) return databasePromise;

  databasePromise = new Promise<IDBDatabase | null>((resolve) => {
    const request = window.indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(KV_STORE)) {
        const store = database.createObjectStore(KV_STORE, { keyPath: "key" });
        store.createIndex("scope", "scope", { unique: false });
      }
      if (!database.objectStoreNames.contains(API_STORE)) {
        const store = database.createObjectStore(API_STORE, { keyPath: "key" });
        store.createIndex("scope", "scope", { unique: false });
        store.createIndex("expiresAt", "expiresAt", { unique: false });
      }
      if (!database.objectStoreNames.contains(OUTBOX_STORE)) {
        const store = database.createObjectStore(OUTBOX_STORE, { keyPath: "id" });
        store.createIndex("scope", "scope", { unique: false });
        store.createIndex("scope_created", ["scope", "createdAt"], { unique: false });
        store.createIndex("status", "status", { unique: false });
      }
    };
    request.onsuccess = () => {
      const database = request.result;
      database.onversionchange = () => database.close();
      resolve(database);
    };
    request.onerror = () => {
      console.warn("[offline] IndexedDB unavailable; using memory fallback", request.error);
      resolve(null);
    };
    request.onblocked = () => console.warn("[offline] IndexedDB upgrade blocked by another tab");
  });

  return databasePromise;
}

function randomId(prefix: string): string {
  const uuid = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}-${uuid}`;
}

export function currentOfflineScope(): string {
  const user = getCachedUser();
  const tenant = getActiveAmoId() || user?.amo_id || getContext().amoCode || "platform";
  return `${user?.id || "anonymous"}:${tenant || "platform"}`;
}

function scopedKey(kind: string, key: string, scope = currentOfflineScope()): string {
  return `${kind}:${scope}:${key}`;
}

function notifyOfflineStateChanged(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(OFFLINE_EVENT));
}

export function onOfflineStateChanged(listener: () => void): () => void {
  if (typeof window === "undefined") return () => undefined;
  window.addEventListener(OFFLINE_EVENT, listener);
  return () => window.removeEventListener(OFFLINE_EVENT, listener);
}

async function putRecord(storeName: string, value: unknown): Promise<void> {
  const database = await openDatabase();
  if (!database) return;
  const transaction = database.transaction(storeName, "readwrite");
  transaction.objectStore(storeName).put(value);
  await transactionDone(transaction);
}

async function deleteRecord(storeName: string, key: IDBValidKey): Promise<void> {
  const database = await openDatabase();
  if (!database) return;
  const transaction = database.transaction(storeName, "readwrite");
  transaction.objectStore(storeName).delete(key);
  await transactionDone(transaction);
}

async function readRecord<T>(storeName: string, key: IDBValidKey): Promise<T | undefined> {
  const database = await openDatabase();
  if (!database) return undefined;
  const transaction = database.transaction(storeName, "readonly");
  const value = await requestResult(transaction.objectStore(storeName).get(key));
  await transactionDone(transaction);
  return value as T | undefined;
}

async function recordsForScope<T>(storeName: string, scope: string): Promise<T[]> {
  const database = await openDatabase();
  if (!database) return [];
  const transaction = database.transaction(storeName, "readonly");
  const index = transaction.objectStore(storeName).index("scope");
  const values = await requestResult(index.getAll(IDBKeyRange.only(scope)));
  await transactionDone(transaction);
  return values as T[];
}

async function deleteScopeRecords(storeName: string, scope: string): Promise<void> {
  const database = await openDatabase();
  if (!database) return;
  const transaction = database.transaction(storeName, "readwrite");
  const index = transaction.objectStore(storeName).index("scope");
  const keys = await requestResult(index.getAllKeys(IDBKeyRange.only(scope)));
  keys.forEach((key) => transaction.objectStore(storeName).delete(key));
  await transactionDone(transaction);
}

export function createPortalQueryPersister(): QueryPersister {
  return {
    async persistClient(client: unknown) {
      memoryQueryCache = client;
      const scope = currentOfflineScope();
      const record: KeyValueRecord = {
        key: scopedKey("query", QUERY_CACHE_KEY, scope),
        scope,
        value: client,
        updatedAt: Date.now(),
      };
      await putRecord(KV_STORE, record).catch((error) => console.warn("[offline] Could not persist query cache", error));
    },
    async restoreClient() {
      const scope = currentOfflineScope();
      const record = await readRecord<KeyValueRecord>(KV_STORE, scopedKey("query", QUERY_CACHE_KEY, scope)).catch(() => undefined);
      return record?.value ?? memoryQueryCache;
    },
    async removeClient() {
      const scope = currentOfflineScope();
      memoryQueryCache = undefined;
      await deleteRecord(KV_STORE, scopedKey("query", QUERY_CACHE_KEY, scope)).catch(() => undefined);
    },
  };
}

export async function writeApiCache<T>(path: string, value: T, ttlMs: number): Promise<void> {
  const scope = currentOfflineScope();
  const key = scopedKey("api", path, scope);
  const now = Date.now();
  const record: ApiCacheRecord<T> = {
    key,
    scope,
    path,
    value,
    storedAt: now,
    expiresAt: now + Math.max(ttlMs, 1),
  };
  memoryApiCache.set(key, record);
  await putRecord(API_STORE, record).catch((error) => console.warn("[offline] Could not cache API response", error));
}

export async function readApiCache<T>(path: string, allowExpired = false): Promise<ApiCacheRecord<T> | null> {
  const scope = currentOfflineScope();
  const key = scopedKey("api", path, scope);
  const memory = memoryApiCache.get(key) as ApiCacheRecord<T> | undefined;
  if (memory && (allowExpired || memory.expiresAt > Date.now())) return memory;
  const stored = await readRecord<ApiCacheRecord<T>>(API_STORE, key).catch(() => undefined);
  if (!stored) return null;
  memoryApiCache.set(key, stored);
  if (!allowExpired && stored.expiresAt <= Date.now()) return null;
  return stored;
}

export async function removeApiCache(path: string): Promise<void> {
  const key = scopedKey("api", path);
  memoryApiCache.delete(key);
  await deleteRecord(API_STORE, key).catch(() => undefined);
}

export async function enqueueOfflineMutation(input: {
  path: string;
  method: string;
  headers?: HeadersInit;
  body?: string;
  entityType?: string;
  entityId?: string;
  idempotencyKey?: string;
}): Promise<OfflineOutboxEntry> {
  const scope = currentOfflineScope();
  const idempotencyKey = input.idempotencyKey || randomId("offline-operation");
  const headers = new Headers(input.headers);
  headers.delete("Authorization");
  headers.delete("Cookie");
  headers.set("Idempotency-Key", idempotencyKey);
  const now = Date.now();
  const entry: OfflineOutboxEntry = {
    id: randomId("outbox"),
    scope,
    path: input.path,
    method: input.method.toUpperCase(),
    headers: Object.fromEntries(headers.entries()),
    body: input.body,
    createdAt: now,
    updatedAt: now,
    attempts: 0,
    status: "queued",
    entityType: input.entityType,
    entityId: input.entityId,
    idempotencyKey,
  };
  memoryOutbox.set(entry.id, entry);
  await putRecord(OUTBOX_STORE, entry);
  notifyOfflineStateChanged();
  return entry;
}

export async function listOfflineMutations(scope = currentOfflineScope()): Promise<OfflineOutboxEntry[]> {
  const stored = await recordsForScope<OfflineOutboxEntry>(OUTBOX_STORE, scope).catch(() => []);
  if (!stored.length && memoryOutbox.size) {
    return [...memoryOutbox.values()].filter((entry) => entry.scope === scope).sort((a, b) => a.createdAt - b.createdAt);
  }
  stored.forEach((entry) => memoryOutbox.set(entry.id, entry));
  return stored.sort((a, b) => a.createdAt - b.createdAt);
}

export async function getOfflineOutboxSummary(scope = currentOfflineScope()): Promise<OfflineOutboxSummary> {
  const entries = await listOfflineMutations(scope);
  const summary: OfflineOutboxSummary = { queued: 0, syncing: 0, conflict: 0, failed: 0, total: entries.length };
  entries.forEach((entry) => { summary[entry.status] += 1; });
  return summary;
}

async function saveOutboxEntry(entry: OfflineOutboxEntry): Promise<void> {
  memoryOutbox.set(entry.id, entry);
  await putRecord(OUTBOX_STORE, entry);
  notifyOfflineStateChanged();
}

export async function discardOfflineMutation(id: string): Promise<void> {
  memoryOutbox.delete(id);
  await deleteRecord(OUTBOX_STORE, id).catch(() => undefined);
  notifyOfflineStateChanged();
}

function hasReplayLease(): boolean {
  if (typeof window === "undefined") return true;
  const now = Date.now();
  const owner = randomId("tab");
  try {
    const current = JSON.parse(window.localStorage.getItem(REPLAY_LEASE_KEY) || "null") as { owner?: string; expiresAt?: number } | null;
    if (current?.expiresAt && current.expiresAt > now) return false;
    window.localStorage.setItem(REPLAY_LEASE_KEY, JSON.stringify({ owner, expiresAt: now + REPLAY_LEASE_MS }));
    const confirmed = JSON.parse(window.localStorage.getItem(REPLAY_LEASE_KEY) || "null") as { owner?: string } | null;
    return confirmed?.owner === owner;
  } catch {
    return true;
  }
}

function releaseReplayLease(): void {
  if (typeof window === "undefined") return;
  try { window.localStorage.removeItem(REPLAY_LEASE_KEY); } catch { /* best effort */ }
}

async function parseReplayError(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) return response.json().catch(() => ({ status: response.status }));
  return response.text().catch(() => response.statusText);
}

export async function replayOfflineMutations(): Promise<OfflineOutboxSummary> {
  if (typeof navigator !== "undefined" && !navigator.onLine) return getOfflineOutboxSummary();
  if (!getToken() || !hasReplayLease()) return getOfflineOutboxSummary();

  const scope = currentOfflineScope();
  try {
    const entries = (await listOfflineMutations(scope)).filter((entry) => entry.status === "queued" || entry.status === "syncing");
    for (const entry of entries) {
      const syncing: OfflineOutboxEntry = { ...entry, status: "syncing", updatedAt: Date.now(), error: undefined };
      await saveOutboxEntry(syncing);
      try {
        const headers = new Headers(authHeaders(syncing.headers));
        headers.set("Idempotency-Key", syncing.idempotencyKey);
        const response = await fetch(`${getApiBaseUrl().replace(/\/$/, "")}${syncing.path.startsWith("/") ? syncing.path : `/${syncing.path}`}`, {
          method: syncing.method,
          headers,
          body: syncing.body,
          credentials: "include",
        });
        if (response.ok) {
          await discardOfflineMutation(syncing.id);
          continue;
        }
        const detail = await parseReplayError(response);
        if (response.status === 409 || response.status === 412 || response.status === 422) {
          await saveOutboxEntry({
            ...syncing,
            status: "conflict",
            attempts: syncing.attempts + 1,
            updatedAt: Date.now(),
            error: `Server conflict (${response.status})`,
            conflict: detail,
          });
          continue;
        }
        if (response.status >= 400 && response.status < 500) {
          await saveOutboxEntry({
            ...syncing,
            status: "failed",
            attempts: syncing.attempts + 1,
            updatedAt: Date.now(),
            error: typeof detail === "string" ? detail : JSON.stringify(detail),
          });
          continue;
        }
        await saveOutboxEntry({ ...syncing, status: "queued", attempts: syncing.attempts + 1, updatedAt: Date.now(), error: `Server unavailable (${response.status})` });
        break;
      } catch (error) {
        await saveOutboxEntry({
          ...syncing,
          status: "queued",
          attempts: syncing.attempts + 1,
          updatedAt: Date.now(),
          error: error instanceof Error ? error.message : String(error),
        });
        break;
      }
    }
  } finally {
    releaseReplayLease();
  }
  return getOfflineOutboxSummary(scope);
}

export async function clearCurrentOfflineScope(): Promise<void> {
  const scope = currentOfflineScope();
  memoryQueryCache = undefined;
  [...memoryApiCache.entries()].forEach(([key, value]) => { if (value.scope === scope) memoryApiCache.delete(key); });
  [...memoryOutbox.entries()].forEach(([key, value]) => { if (value.scope === scope) memoryOutbox.delete(key); });
  await Promise.all([
    deleteScopeRecords(KV_STORE, scope),
    deleteScopeRecords(API_STORE, scope),
    deleteScopeRecords(OUTBOX_STORE, scope),
  ]).catch(() => undefined);
  notifyOfflineStateChanged();
}

export async function clearAllPortalOfflineData(): Promise<void> {
  memoryQueryCache = undefined;
  memoryApiCache.clear();
  memoryOutbox.clear();
  const database = await openDatabase();
  if (database) {
    const transaction = database.transaction([KV_STORE, API_STORE, OUTBOX_STORE], "readwrite");
    transaction.objectStore(KV_STORE).clear();
    transaction.objectStore(API_STORE).clear();
    transaction.objectStore(OUTBOX_STORE).clear();
    await transactionDone(transaction).catch(() => undefined);
  }
  notifyOfflineStateChanged();
}

export function newOfflineIdempotencyKey(prefix = "portal"): string {
  return randomId(prefix);
}
