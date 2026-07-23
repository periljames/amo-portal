import { authHeaders, getCachedUser, getContext, getToken } from "./auth";
import { getApiBaseUrl } from "./config";

const DATABASE_NAME = "amo-portal-offline";
const DATABASE_VERSION = 2;
const API_STORE = "api_cache";
const OUTBOX_STORE = "outbox";
const LEASE_STORE = "leases";
const OFFLINE_EVENT = "amo:offline-state-changed";
const OFFLINE_SYNC_EVENT = "amo:offline-sync-complete";
const OFFLINE_CHANNEL = "amo:offline-state";
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
  key: string;
  scope: string;
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

type DatabaseRead<T> = {
  available: boolean;
  value: T;
};

let databasePromise: Promise<IDBDatabase | null> | null = null;
let offlineChannel: BroadcastChannel | null = null;
const memoryApiCache = new Map<string, ApiCacheRecord>();
const memoryOutbox = new Map<string, OfflineOutboxEntry>();
const memoryReplayLeases = new Map<string, ReplayLease>();

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
      if (!database.objectStoreNames.contains(LEASE_STORE)) {
        const store = database.createObjectStore(LEASE_STORE, { keyPath: "key" });
        store.createIndex("scope", "scope", { unique: false });
        store.createIndex("expiresAt", "expiresAt", { unique: false });
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

function channel(): BroadcastChannel | null {
  if (typeof window === "undefined" || typeof BroadcastChannel === "undefined") return null;
  if (offlineChannel) return offlineChannel;
  offlineChannel = new BroadcastChannel(OFFLINE_CHANNEL);
  offlineChannel.onmessage = (event: MessageEvent<{ type?: string; detail?: OfflineSyncDetail }>) => {
    if (event.data?.type === "sync" && event.data.detail) {
      window.dispatchEvent(new CustomEvent<OfflineSyncDetail>(OFFLINE_SYNC_EVENT, { detail: event.data.detail }));
    }
    window.dispatchEvent(new CustomEvent(OFFLINE_EVENT));
  };
  return offlineChannel;
}

function notifyOfflineStateChanged(broadcast = true): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(OFFLINE_EVENT));
  if (broadcast) channel()?.postMessage({ type: "state" });
}

function notifyOfflineSyncComplete(detail: OfflineSyncDetail, broadcast = true): void {
  if (typeof window === "undefined") return;
  if (detail.synced <= 0 && detail.paths.length === 0) return;
  window.dispatchEvent(new CustomEvent<OfflineSyncDetail>(OFFLINE_SYNC_EVENT, { detail }));
  if (broadcast) channel()?.postMessage({ type: "sync", detail });
}

export function onOfflineStateChanged(listener: () => void): () => void {
  if (typeof window === "undefined") return () => undefined;
  channel();
  window.addEventListener(OFFLINE_EVENT, listener);
  return () => window.removeEventListener(OFFLINE_EVENT, listener);
}

export function onOfflineSyncComplete(listener: (detail: OfflineSyncDetail) => void): () => void {
  if (typeof window === "undefined") return () => undefined;
  channel();
  const handler = (event: Event) => listener((event as CustomEvent<OfflineSyncDetail>).detail);
  window.addEventListener(OFFLINE_SYNC_EVENT, handler);
  return () => window.removeEventListener(OFFLINE_SYNC_EVENT, handler);
}

async function putRecord(storeName: string, value: unknown): Promise<boolean> {
  const database = await openDatabase();
  if (!database) return false;
  const transaction = database.transaction(storeName, "readwrite");
  const done = transactionDone(transaction);
  transaction.objectStore(storeName).put(value);
  await done;
  return true;
}

async function deleteRecord(storeName: string, key: IDBValidKey): Promise<boolean> {
  const database = await openDatabase();
  if (!database) return false;
  const transaction = database.transaction(storeName, "readwrite");
  const done = transactionDone(transaction);
  transaction.objectStore(storeName).delete(key);
  await done;
  return true;
}

async function readRecord<T>(storeName: string, key: IDBValidKey): Promise<DatabaseRead<T | undefined>> {
  const database = await openDatabase();
  if (!database) return { available: false, value: undefined };
  const transaction = database.transaction(storeName, "readonly");
  const done = transactionDone(transaction);
  const value = await requestResult(transaction.objectStore(storeName).get(key));
  await done;
  return { available: true, value: value as T | undefined };
}

async function recordsForScope<T>(storeName: string, scope: string): Promise<DatabaseRead<T[]>> {
  const database = await openDatabase();
  if (!database) return { available: false, value: [] };
  const transaction = database.transaction(storeName, "readonly");
  const done = transactionDone(transaction);
  const index = transaction.objectStore(storeName).index("scope");
  const values = await requestResult(index.getAll(IDBKeyRange.only(scope)));
  await done;
  return { available: true, value: values as T[] };
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
  await putRecord(API_STORE, record).catch((error) => {
    console.warn("[offline] Could not cache API response", error);
    return false;
  });
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

  const stored = await readRecord<ApiCacheRecord<T>>(API_STORE, key).catch(() => ({
    available: false,
    value: undefined,
  }));
  if (currentOfflineScope() !== scope) return null;
  if (!stored.available || !stored.value || stored.value.scope !== scope) return null;
  memoryApiCache.set(key, stored.value);
  if (!allowExpired && stored.value.expiresAt <= Date.now()) return null;
  return stored.value;
}

export async function removeApiCache(path: string, scope = currentOfflineScope()): Promise<void> {
  const key = scopedKey("api", path, scope);
  memoryApiCache.delete(key);
  await deleteRecord(API_STORE, key).catch(() => false);
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
  const result = await recordsForScope<OfflineOutboxEntry>(OUTBOX_STORE, scope).catch(() => ({
    available: false,
    value: [],
  }));
  if (currentOfflineScope() !== scope) return [];

  if (!result.available) {
    return [...memoryOutbox.values()]
      .filter((entry) => entry.scope === scope)
      .sort((left, right) => left.createdAt - right.createdAt);
  }

  const storedIds = new Set(result.value.map((entry) => entry.id));
  [...memoryOutbox.entries()].forEach(([id, entry]) => {
    if (entry.scope === scope && !storedIds.has(id)) memoryOutbox.delete(id);
  });
  result.value.forEach((entry) => memoryOutbox.set(entry.id, entry));
  return result.value.sort((left, right) => left.createdAt - right.createdAt);
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

async function findOutboxEntry(id: string): Promise<OfflineOutboxEntry | undefined> {
  const stored = await readRecord<OfflineOutboxEntry>(OUTBOX_STORE, id).catch(() => ({
    available: false,
    value: undefined,
  }));
  if (stored.available) {
    if (stored.value) memoryOutbox.set(id, stored.value);
    else memoryOutbox.delete(id);
    return stored.value;
  }
  return memoryOutbox.get(id);
}

async function replaceOutboxEntry(
  expected: OfflineOutboxEntry,
  next: OfflineOutboxEntry,
): Promise<OfflineOutboxEntry | null> {
  const database = await openDatabase();
  if (!database) {
    const current = memoryOutbox.get(expected.id);
    if (!current || current.updatedAt !== expected.updatedAt || current.status !== expected.status) return null;
    memoryOutbox.set(next.id, next);
    notifyOfflineStateChanged();
    return next;
  }

  const transaction = database.transaction(OUTBOX_STORE, "readwrite");
  const done = transactionDone(transaction);
  const store = transaction.objectStore(OUTBOX_STORE);
  const current = await requestResult(store.get(expected.id)) as OfflineOutboxEntry | undefined;
  if (!current || current.updatedAt !== expected.updatedAt || current.status !== expected.status) {
    await done;
    if (!current) memoryOutbox.delete(expected.id);
    else memoryOutbox.set(current.id, current);
    return null;
  }
  store.put(next);
  await done;
  memoryOutbox.set(next.id, next);
  notifyOfflineStateChanged();
  return next;
}

async function removeOutboxEntry(
  expected: OfflineOutboxEntry,
  reason?: "discarded",
): Promise<boolean> {
  const database = await openDatabase();
  if (!database) {
    const current = memoryOutbox.get(expected.id);
    if (!current || current.updatedAt !== expected.updatedAt || current.status !== expected.status) return false;
    memoryOutbox.delete(expected.id);
  } else {
    const transaction = database.transaction(OUTBOX_STORE, "readwrite");
    const done = transactionDone(transaction);
    const store = transaction.objectStore(OUTBOX_STORE);
    const current = await requestResult(store.get(expected.id)) as OfflineOutboxEntry | undefined;
    if (!current || current.updatedAt !== expected.updatedAt || current.status !== expected.status) {
      await done;
      if (!current) memoryOutbox.delete(expected.id);
      else memoryOutbox.set(current.id, current);
      return false;
    }
    store.delete(expected.id);
    await done;
    memoryOutbox.delete(expected.id);
  }

  notifyOfflineStateChanged();
  if (reason === "discarded") {
    notifyOfflineSyncComplete({
      scope: expected.scope,
      synced: 0,
      paths: [expected.path],
      entityTypes: expected.entityType ? [expected.entityType] : [],
      reason,
    });
  }
  return true;
}

function parseBody(entry: OfflineOutboxEntry): Record<string, unknown> {
  if (!entry.body) return {};
  try {
    const parsed = JSON.parse(entry.body) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return { ...(parsed as Record<string, unknown>) };
    }
  } catch {
    // The original payload is retained for non-JSON operations.
  }
  return {};
}

export function currentConflictRevision(value: unknown): number | null {
  if (!value || typeof value !== "object") return null;
  const row = value as Record<string, unknown>;
  const direct = row.current_state_revision;
  if (typeof direct === "number" && Number.isFinite(direct)) return direct;
  if (Array.isArray(row.conflicts)) {
    for (const conflict of row.conflicts) {
      const found = currentConflictRevision(conflict);
      if (found !== null) return found;
    }
  }
  if (row.detail && typeof row.detail === "object") {
    return currentConflictRevision(row.detail);
  }
  return null;
}

async function currentTaskUpdatedAt(entry: OfflineOutboxEntry): Promise<string> {
  if (!entry.entityId) throw new Error("The conflicted task no longer has an identifier.");
  if (currentOfflineScope() !== entry.scope) {
    throw new Error("AMO context changed while preparing this retry.");
  }
  const response = await fetch(
    `${getApiBaseUrl().replace(/\/$/, "")}/work-orders/tasks/${encodeURIComponent(entry.entityId)}`,
    {
      method: "GET",
      headers: authHeaders(),
      credentials: "include",
    },
  );
  if (!response.ok) {
    throw new Error(`Could not refresh the current task before retrying (${response.status}).`);
  }
  const payload = await response.json() as { updated_at?: unknown };
  if (currentOfflineScope() !== entry.scope) {
    throw new Error("AMO context changed while preparing this retry.");
  }
  if (typeof payload.updated_at !== "string" || !payload.updated_at.trim()) {
    throw new Error("The current task revision is unavailable. Refresh the task and recreate the edit.");
  }
  return payload.updated_at;
}

export async function rebaseConflictBody(entry: OfflineOutboxEntry): Promise<string | undefined> {
  if (entry.status !== "conflict") return entry.body;
  const body = parseBody(entry);

  if (entry.entityType === "roster-assignment" || Object.prototype.hasOwnProperty.call(body, "expected_state_revision")) {
    const revision = currentConflictRevision(entry.conflict);
    if (revision === null) {
      throw new Error("The current roster revision is unavailable. Refresh the roster and recreate or discard this edit.");
    }
    body.expected_state_revision = revision;
    return JSON.stringify(body);
  }

  if (entry.entityType === "work-order-task" || Object.prototype.hasOwnProperty.call(body, "last_known_updated_at")) {
    body.last_known_updated_at = await currentTaskUpdatedAt(entry);
    return JSON.stringify(body);
  }

  return entry.body;
}

export async function retryOfflineMutation(id: string): Promise<OfflineOutboxEntry> {
  const entry = await findOutboxEntry(id);
  if (!entry) throw new Error("The local change no longer exists.");
  if (entry.scope !== currentOfflineScope()) {
    throw new Error("Switch back to the AMO where this change was created before retrying it.");
  }
  const body = await rebaseConflictBody(entry);
  const queued: OfflineOutboxEntry = {
    ...entry,
    body,
    status: "queued",
    updatedAt: Date.now(),
    error: undefined,
    conflict: undefined,
  };
  const saved = await replaceOutboxEntry(entry, queued);
  if (!saved) throw new Error("The local change was updated or removed in another tab. Refresh before retrying.");
  return saved;
}

export async function discardOfflineMutation(id: string): Promise<void> {
  const entry = await findOutboxEntry(id);
  if (!entry) return;
  if (entry.scope !== currentOfflineScope()) {
    throw new Error("Switch back to the AMO where this change was created before discarding it.");
  }
  await removeOutboxEntry(entry, "discarded");
}

function leaseKey(scope: string): string {
  return `replay:${scope}`;
}

async function acquireReplayLease(scope: string): Promise<string | null> {
  const owner = randomId("tab");
  const now = Date.now();
  const key = leaseKey(scope);
  const database = await openDatabase();
  if (!database) {
    const current = memoryReplayLeases.get(key);
    if (current && current.expiresAt > now) return null;
    memoryReplayLeases.set(key, { key, scope, owner, expiresAt: now + REPLAY_LEASE_MS });
    return owner;
  }

  const transaction = database.transaction(LEASE_STORE, "readwrite");
  const done = transactionDone(transaction);
  const store = transaction.objectStore(LEASE_STORE);
  const current = await requestResult(store.get(key)) as ReplayLease | undefined;
  if (current && current.expiresAt > now) {
    await done;
    return null;
  }
  store.put({ key, scope, owner, expiresAt: now + REPLAY_LEASE_MS } satisfies ReplayLease);
  await done;
  return owner;
}

async function renewReplayLease(owner: string, scope: string): Promise<boolean> {
  const key = leaseKey(scope);
  const database = await openDatabase();
  if (!database) {
    const current = memoryReplayLeases.get(key);
    if (!current || current.owner !== owner) return false;
    memoryReplayLeases.set(key, { ...current, expiresAt: Date.now() + REPLAY_LEASE_MS });
    return true;
  }

  const transaction = database.transaction(LEASE_STORE, "readwrite");
  const done = transactionDone(transaction);
  const store = transaction.objectStore(LEASE_STORE);
  const current = await requestResult(store.get(key)) as ReplayLease | undefined;
  if (!current || current.owner !== owner) {
    await done;
    return false;
  }
  store.put({ ...current, expiresAt: Date.now() + REPLAY_LEASE_MS });
  await done;
  return true;
}

async function releaseReplayLease(owner: string, scope: string): Promise<void> {
  const key = leaseKey(scope);
  const database = await openDatabase();
  if (!database) {
    const current = memoryReplayLeases.get(key);
    if (current?.owner === owner) memoryReplayLeases.delete(key);
    return;
  }

  const transaction = database.transaction(LEASE_STORE, "readwrite");
  const done = transactionDone(transaction);
  const store = transaction.objectStore(LEASE_STORE);
  const current = await requestResult(store.get(key)) as ReplayLease | undefined;
  if (current?.owner === owner) store.delete(key);
  await done;
}

async function fetchForReplay(entry: OfflineOutboxEntry): Promise<Response> {
  if (currentOfflineScope() !== entry.scope) {
    throw new Error("AMO context changed. This change will retry when you return to its AMO.");
  }
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(
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
    globalThis.clearTimeout(timeout);
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
  const scope = currentOfflineScope();
  if (typeof navigator !== "undefined" && !navigator.onLine) return getOfflineOutboxSummary(scope);
  if (!getToken()) return getOfflineOutboxSummary(scope);
  const leaseOwner = await acquireReplayLease(scope);
  if (!leaseOwner) return getOfflineOutboxSummary(scope);

  const syncedPaths = new Set<string>();
  const syncedEntityTypes = new Set<string>();
  let synced = 0;

  try {
    const entries = (await listOfflineMutations(scope))
      .filter((entry) => entry.status === "queued" || entry.status === "syncing");
    if (currentOfflineScope() !== scope) return getOfflineOutboxSummary(scope);

    for (const entry of entries) {
      if (currentOfflineScope() !== scope || entry.scope !== scope) break;
      if (!(await renewReplayLease(leaseOwner, scope))) break;
      const syncing: OfflineOutboxEntry = {
        ...entry,
        status: "syncing",
        updatedAt: Date.now(),
        error: undefined,
      };
      const claimed = await replaceOutboxEntry(entry, syncing);
      if (!claimed) continue;

      try {
        const response = await fetchForReplay(claimed);
        if (!(await renewReplayLease(leaseOwner, scope))) break;
        if (response.ok) {
          if (await removeOutboxEntry(claimed)) {
            synced += 1;
            syncedPaths.add(claimed.path);
            if (claimed.entityType) syncedEntityTypes.add(claimed.entityType);
          }
          continue;
        }

        const detail = await parseReplayError(response);
        if (response.status === 409 || response.status === 412 || response.status === 422) {
          await replaceOutboxEntry(claimed, {
            ...claimed,
            status: "conflict",
            attempts: claimed.attempts + 1,
            updatedAt: Date.now(),
            error: `Server conflict (${response.status})`,
            conflict: detail,
          });
          continue;
        }

        if (retryableReplayStatus(response.status)) {
          await replaceOutboxEntry(claimed, {
            ...claimed,
            status: "queued",
            attempts: claimed.attempts + 1,
            updatedAt: Date.now(),
            error: response.status === 401
              ? "Session expired. This change will retry after sign-in."
              : `Server unavailable (${response.status})`,
          });
          break;
        }

        await replaceOutboxEntry(claimed, {
          ...claimed,
          status: "failed",
          attempts: claimed.attempts + 1,
          updatedAt: Date.now(),
          error: typeof detail === "string" ? detail : JSON.stringify(detail),
        });
      } catch (error) {
        await replaceOutboxEntry(claimed, {
          ...claimed,
          status: "queued",
          attempts: claimed.attempts + 1,
          updatedAt: Date.now(),
          error: error instanceof Error ? error.message : String(error),
        });
        break;
      }
    }
  } finally {
    await releaseReplayLease(leaseOwner, scope);
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
  memoryReplayLeases.delete(leaseKey(scope));
  await Promise.all([
    deleteScopeRecords(API_STORE, scope),
    deleteScopeRecords(OUTBOX_STORE, scope),
    deleteScopeRecords(LEASE_STORE, scope),
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
  memoryReplayLeases.clear();
  const database = await openDatabase();
  if (database) {
    const transaction = database.transaction([API_STORE, OUTBOX_STORE, LEASE_STORE], "readwrite");
    const done = transactionDone(transaction);
    transaction.objectStore(API_STORE).clear();
    transaction.objectStore(OUTBOX_STORE).clear();
    transaction.objectStore(LEASE_STORE).clear();
    await done.catch(() => undefined);
  }
  notifyOfflineStateChanged();
}

export function newOfflineIdempotencyKey(prefix = "portal"): string {
  return randomId(prefix);
}
