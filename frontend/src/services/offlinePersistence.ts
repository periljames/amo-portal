import { authHeaders, getCachedUser, getContext, getToken } from "./auth";
import { getApiBaseUrl } from "./config";

const DATABASE_NAME = "amo-portal-offline";
const DATABASE_VERSION = 1;
const API_STORE = "api_cache";
const OUTBOX_STORE = "outbox";
const OFFLINE_EVENT = "amo:offline-state-changed";
const OFFLINE_SYNC_EVENT = "amo:offline-sync-complete";
const REPLAY_LEASE_KEY = "amo:offline-replay-lease";
const REPLAY_LEASE_MS = 45_000;
const REPLAY_REQUEST_TIMEOUT_MS = 30_000;
const ACTIVE_AMO_KEYS = ["amodb_active_amo_id", "amodb_admin_active_amo_id"];

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

export type OfflineSyncDetail = {
  scope: string;
  synced: number;
  paths: string[];
  entityTypes: string[];
  reason?: "synced" | "discarded";
};

export type ApiCacheRecord<T = unknown> = {
  key: string;
  scope: string;
  path: string;
  value: T;
  storedAt: number;
  expiresAt: number;
};

type ReplayLease = {
  owner: string;
  expiresAt: number;
};

type EnqueueOfflineMutationInput = {
  path: string;
  method: string;
  headers?: HeadersInit;
  body?: string;
  entityType?: string;
  entityId?: string;
  idempotencyKey?: string;
  scope?: string;
};

let databasePromise: Promise<IDBDatabase | null> | null = null;
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
    request.onblocked = () => console.warn("[offline] IndexedDB upgrade blocked by another portal tab");
  });

  return databasePromise;
}

function randomId(prefix: string): string {
  const uuid = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}-${uuid}`;
}

function activeAmoId(): string | null {
  if (typeof window === "undefined") return null;
  for (const key of ACTIVE_AMO_KEYS) {
    const value = window.localStorage.getItem(key)?.trim();
    if (value) return value;
  }
  return null;
}

export function currentOfflineScope(): string {
  const user = getCachedUser();
  const tenant = activeAmoId() || user?.amo_id || getContext().amoCode || "platform";
  return `${user?.id || "anonymous"}:${tenant || "platform"}`;
}

function scopedKey(kind: string, key: string, scope = currentOfflineScope()): string {
  return `${kind}:${scope}:${key}`;
}

function notifyOfflineStateChanged(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(OFFLINE_EVENT));
}

function notifyOfflineSyncComplete(detail: OfflineSyncDetail): void {
  if (typeof window === "undefined") return;
  if (detail.synced <= 0 && detail.paths.length === 0) return;
  window.dispatchEvent(new CustomEvent<OfflineSyncDetail>(OFFLINE_SYNC_EVENT, { detail }));
}

export function onOfflineStateChanged(listener: () => void): () => void {
  if (typeof window === "undefined") return () => undefined;
  window.addEventListener(OFFLINE_EVENT, listener);
  return () => window.removeEventListener(OFFLINE_EVENT, listener);
}

export function onOfflineSyncComplete(listener: (detail: OfflineSyncDetail) => void): () => void {
  if (typeof window === "undefined") return () => undefined;
  const handler = (event: Event) => listener((event as CustomEvent<OfflineSyncDetail>).detail);
  window.addEventListener(OFFLINE_SYNC_EVENT, handler);
  return () => window.removeEventListener(OFFLINE_SYNC_EVENT, handler);
}

async function putRecord(storeName: string, value: unknown): Promise<void> {
  const database = await openDatabase();
  if (!database) return;
  const transaction = database.transaction(storeName, "readwrite");
  const done = transactionDone(transaction);
  transaction.objectStore(storeName).put(value);
  await done;
}

async function deleteRecord(storeName: string, key: IDBValidKey): Promise<void> {
  const database = await openDatabase();
  if (!database) return;
  const transaction = database.transaction(storeName, "readwrite");
  const done = transactionDone(transaction);
  transaction.objectStore(storeName).delete(key);
  await done;
}

async function readRecord<T>(storeName: string, key: IDBValidKey): Promise<T | undefined> {
  const database = await openDatabase();
  if (!database) return undefined;
  const transaction = database.transaction(storeName, "readonly");
  const done = transactionDone(transaction);
  const value = await requestResult(transaction.objectStore(storeName).get(key));
  await done;
  return value as T | undefined;
}

async function recordsForScope<T>(storeName: string, scope: string): Promise<T[]> {
  const database = await openDatabase();
  if (!database) return [];
  const transaction = database.transaction(storeName, "readonly");
  const done = transactionDone(transaction);
  const index = transaction.objectStore(storeName).index("scope");
  const values = await requestResult(index.getAll(IDBKeyRange.only(scope)));
  await done;
  return values as T[];
}

async function deleteScopeRecords(storeName: string, scope: string): Promise<void> {
  const database = await openDatabase();
  if (!database) return;
  const transaction = database.transaction(storeName, "readwrite");
  const done = transactionDone(transaction);
  const index = transaction.objectStore(storeName).index("scope");
  const keys = await requestResult(index.getAllKeys(IDBKeyRange.only(scope)));
  keys.forEach((key) => transaction.objectStore(storeName).delete(key));
  await done;
}

export async function writeApiCache<T>(
  path: string,
  value: T,
  ttlMs: number,
  scope = currentOfflineScope(),
): Promise<void> {
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

export async function readApiCache<T>(
  path: string,
  allowExpired = false,
  scope = currentOfflineScope(),
): Promise<ApiCacheRecord<T> | null> {
  if (currentOfflineScope() !== scope) return null;
  const key = scopedKey("api", path, scope);
  const memory = memoryApiCache.get(key) as ApiCacheRecord<T> | undefined;
  if (memory && (allowExpired || memory.expiresAt > Date.now())) return memory;

  const stored = await readRecord<ApiCacheRecord<T>>(API_STORE, key).catch(() => undefined);
  if (currentOfflineScope() !== scope) return null;
  if (!stored || stored.scope !== scope) return null;
  memoryApiCache.set(key, stored);
  if (!allowExpired && stored.expiresAt <= Date.now()) return null;
  return stored;
}

export async function removeApiCache(path: string, scope = currentOfflineScope()): Promise<void> {
  const key = scopedKey("api", path, scope);
  memoryApiCache.delete(key);
  await deleteRecord(API_STORE, key).catch(() => undefined);
}

export async function enqueueOfflineMutation(input: EnqueueOfflineMutationInput): Promise<OfflineOutboxEntry> {
  const scope = input.scope || currentOfflineScope();
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
  if (currentOfflineScope() !== scope) return [];
  const stored = await recordsForScope<OfflineOutboxEntry>(OUTBOX_STORE, scope).catch(() => []);
  if (currentOfflineScope() !== scope) return [];

  if (!stored.length && memoryOutbox.size) {
    return [...memoryOutbox.values()]
      .filter((entry) => entry.scope === scope)
      .sort((a, b) => a.createdAt - b.createdAt);
  }
  stored.forEach((entry) => memoryOutbox.set(entry.id, entry));
  return stored.sort((a, b) => a.createdAt - b.createdAt);
}

export async function getOfflineOutboxSummary(scope = currentOfflineScope()): Promise<OfflineOutboxSummary> {
  const entries = await listOfflineMutations(scope);
  const summary: OfflineOutboxSummary = { queued: 0, syncing: 0, conflict: 0, failed: 0, total: entries.length };
  entries.forEach((entry) => {
    if (entry.status === "queued") summary.queued += 1;
    if (entry.status === "syncing") summary.syncing += 1;
    if (entry.status === "conflict") summary.conflict += 1;
    if (entry.status === "failed") summary.failed += 1;
  });
  return summary;
}

async function saveOutboxEntry(entry: OfflineOutboxEntry): Promise<void> {
  memoryOutbox.set(entry.id, entry);
  await putRecord(OUTBOX_STORE, entry);
  notifyOfflineStateChanged();
}

async function findOutboxEntry(id: string): Promise<OfflineOutboxEntry | undefined> {
  const memory = memoryOutbox.get(id);
  if (memory) return memory;
  return readRecord<OfflineOutboxEntry>(OUTBOX_STORE, id).catch(() => undefined);
}

async function removeOutboxEntry(entry: OfflineOutboxEntry, reason?: "discarded"): Promise<void> {
  memoryOutbox.delete(entry.id);
  await deleteRecord(OUTBOX_STORE, entry.id).catch(() => undefined);
  notifyOfflineStateChanged();
  if (reason === "discarded") {
    notifyOfflineSyncComplete({
      scope: entry.scope,
      synced: 0,
      paths: [entry.path],
      entityTypes: entry.entityType ? [entry.entityType] : [],
      reason,
    });
  }
}

export async function retryOfflineMutation(id: string): Promise<OfflineOutboxEntry> {
  const entry = await findOutboxEntry(id);
  if (!entry) throw new Error("The local change no longer exists.");
  if (entry.scope !== currentOfflineScope()) {
    throw new Error("Switch back to the AMO where this change was created before retrying it.");
  }
  const queued: OfflineOutboxEntry = {
    ...entry,
    status: "queued",
    updatedAt: Date.now(),
    error: undefined,
    conflict: undefined,
  };
  await saveOutboxEntry(queued);
  return queued;
}

export async function discardOfflineMutation(id: string): Promise<void> {
  const entry = await findOutboxEntry(id);
  if (!entry) return;
  if (entry.scope !== currentOfflineScope()) {
    throw new Error("Switch back to the AMO where this change was created before discarding it.");
  }
  await removeOutboxEntry(entry, "discarded");
}

function readReplayLease(): ReplayLease | null {
  if (typeof window === "undefined") return null;
  try {
    return JSON.parse(window.localStorage.getItem(REPLAY_LEASE_KEY) || "null") as ReplayLease | null;
  } catch {
    return null;
  }
}

function acquireReplayLease(): string | null {
  if (typeof window === "undefined") return "server";
  const owner = randomId("tab");
  const now = Date.now();
  try {
    const current = readReplayLease();
    if (current?.expiresAt && current.expiresAt > now) return null;
    const lease: ReplayLease = { owner, expiresAt: now + REPLAY_LEASE_MS };
    window.localStorage.setItem(REPLAY_LEASE_KEY, JSON.stringify(lease));
    return readReplayLease()?.owner === owner ? owner : null;
  } catch {
    return owner;
  }
}

function renewReplayLease(owner: string): boolean {
  if (typeof window === "undefined" || owner === "server") return true;
  try {
    const current = readReplayLease();
    if (!current || current.owner !== owner) return false;
    window.localStorage.setItem(
      REPLAY_LEASE_KEY,
      JSON.stringify({ owner, expiresAt: Date.now() + REPLAY_LEASE_MS } satisfies ReplayLease),
    );
    return true;
  } catch {
    return true;
  }
}

function releaseReplayLease(owner: string): void {
  if (typeof window === "undefined" || owner === "server") return;
  try {
    const current = readReplayLease();
    if (!current || current.owner === owner) window.localStorage.removeItem(REPLAY_LEASE_KEY);
  } catch {
    // Best effort only.
  }
}

async function fetchForReplay(entry: OfflineOutboxEntry): Promise<Response> {
  if (currentOfflineScope() !== entry.scope) {
    throw new Error("AMO context changed. This change will retry when you return to its AMO.");
  }
  const controller = new AbortController();
  const timeout = window.setTimeout(
    () => controller.abort(new DOMException("Offline replay request timed out", "AbortError")),
    REPLAY_REQUEST_TIMEOUT_MS,
  );
  try {
    const headers = new Headers(authHeaders(entry.headers));
    headers.set("Idempotency-Key", entry.idempotencyKey);
    const response = await fetch(
      `${getApiBaseUrl().replace(/\/$/, "")}${entry.path.startsWith("/") ? entry.path : `/${entry.path}`}`,
      {
        method: entry.method,
        headers,
        body: entry.body,
        credentials: "include",
        signal: controller.signal,
      },
    );
    if (currentOfflineScope() !== entry.scope) {
      throw new Error("AMO context changed during synchronisation. The operation remains queued in its original AMO.");
    }
    return response;
  } finally {
    window.clearTimeout(timeout);
  }
}

async function parseReplayError(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) return response.json().catch(() => ({ status: response.status }));
  return response.text().catch(() => response.statusText);
}

function retryableReplayStatus(status: number): boolean {
  return status === 401 || status === 408 || status === 425 || status === 429 || status >= 500;
}

export async function replayOfflineMutations(): Promise<OfflineOutboxSummary> {
  if (typeof navigator !== "undefined" && !navigator.onLine) return getOfflineOutboxSummary();
  if (!getToken()) return getOfflineOutboxSummary();
  const leaseOwner = acquireReplayLease();
  if (!leaseOwner) return getOfflineOutboxSummary();

  const scope = currentOfflineScope();
  const syncedPaths = new Set<string>();
  const syncedEntityTypes = new Set<string>();
  let synced = 0;

  try {
    const entries = (await listOfflineMutations(scope))
      .filter((entry) => entry.status === "queued" || entry.status === "syncing");
    if (currentOfflineScope() !== scope) return getOfflineOutboxSummary(scope);

    for (const entry of entries) {
      if (currentOfflineScope() !== scope || entry.scope !== scope) break;
      if (!renewReplayLease(leaseOwner)) break;
      const syncing: OfflineOutboxEntry = {
        ...entry,
        status: "syncing",
        updatedAt: Date.now(),
        error: undefined,
      };
      await saveOutboxEntry(syncing);
      try {
        const response = await fetchForReplay(syncing);
        if (response.ok) {
          synced += 1;
          syncedPaths.add(syncing.path);
          if (syncing.entityType) syncedEntityTypes.add(syncing.entityType);
          await removeOutboxEntry(syncing);
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

        if (retryableReplayStatus(response.status)) {
          await saveOutboxEntry({
            ...syncing,
            status: "queued",
            attempts: syncing.attempts + 1,
            updatedAt: Date.now(),
            error: response.status === 401
              ? "Session expired. This change will retry after sign-in."
              : `Server unavailable (${response.status})`,
          });
          break;
        }

        await saveOutboxEntry({
          ...syncing,
          status: "failed",
          attempts: syncing.attempts + 1,
          updatedAt: Date.now(),
          error: typeof detail === "string" ? detail : JSON.stringify(detail),
        });
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
    releaseReplayLease(leaseOwner);
  }

  notifyOfflineSyncComplete({
    scope,
    synced,
    paths: [...syncedPaths],
    entityTypes: [...syncedEntityTypes],
    reason: "synced",
  });
  return getOfflineOutboxSummary(scope);
}

export async function clearCurrentOfflineScope(): Promise<void> {
  const scope = currentOfflineScope();
  [...memoryApiCache.entries()].forEach(([key, value]) => {
    if (value.scope === scope) memoryApiCache.delete(key);
  });
  [...memoryOutbox.entries()].forEach(([key, value]) => {
    if (value.scope === scope) memoryOutbox.delete(key);
  });
  await Promise.all([
    deleteScopeRecords(API_STORE, scope),
    deleteScopeRecords(OUTBOX_STORE, scope),
  ]).catch(() => undefined);
  notifyOfflineStateChanged();
}

export async function clearAllPortalApiCaches(): Promise<void> {
  memoryApiCache.clear();
  const database = await openDatabase();
  if (!database) return;
  const transaction = database.transaction(API_STORE, "readwrite");
  const done = transactionDone(transaction);
  transaction.objectStore(API_STORE).clear();
  await done.catch(() => undefined);
}

export async function clearAllPortalOfflineData(): Promise<void> {
  memoryApiCache.clear();
  memoryOutbox.clear();
  const database = await openDatabase();
  if (database) {
    const transaction = database.transaction([API_STORE, OUTBOX_STORE], "readwrite");
    const done = transactionDone(transaction);
    transaction.objectStore(API_STORE).clear();
    transaction.objectStore(OUTBOX_STORE).clear();
    await done.catch(() => undefined);
  }
  notifyOfflineStateChanged();
}

export function newOfflineIdempotencyKey(prefix = "portal"): string {
  return randomId(prefix);
}
