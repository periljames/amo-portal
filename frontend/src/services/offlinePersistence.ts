import { authHeaders, getCachedUser, getContext, getToken, handleAuthFailure } from "./auth";
import { getApiBaseUrl } from "./config";
import {
  isPortalReady,
  notePortalResponse,
  recommendedRequestTimeoutMs,
} from "./portalConnectivity";

const DATABASE_NAME = "amo-portal-offline";
const DATABASE_VERSION = 3;
const API_STORE = "api_cache";
const OUTBOX_STORE = "outbox";
const LEASE_STORE = "leases";
const KEY_STORE = "device_keys";
const OFFLINE_EVENT = "amo:offline-state-changed";
const OFFLINE_SYNC_EVENT = "amo:offline-sync-complete";
const OFFLINE_PROGRESS_EVENT = "amo:offline-sync-progress";
const OFFLINE_CHANNEL = "amo:offline-state";
const REPLAY_LEASE_MS = 45_000;
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
  nextAttemptAt?: number;
  lastAttemptAt?: number;
  error?: string;
  responseStatus?: number;
  errorCode?: string;
  retryable?: boolean;
  serverDetail?: string;
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

export type OfflineReplayProgress = {
  scope: string;
  phase: "idle" | "sending" | "paused" | "complete";
  current: number;
  total: number;
  synced: number;
  currentPath?: string;
  message?: string;
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

export type EncryptedDeviceValue = { v: 1; iv: string; data: string };
type StoredApiCacheRecord = Omit<ApiCacheRecord, "value"> & {
  value?: unknown;
  encryptedValue?: EncryptedDeviceValue;
};
type StoredOfflineOutboxEntry = OfflineOutboxEntry & {
  encryptedBody?: EncryptedDeviceValue;
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
let deviceKeyPromise: Promise<CryptoKey | null> | null = null;
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
      if (!database.objectStoreNames.contains(KEY_STORE)) {
        database.createObjectStore(KEY_STORE, { keyPath: "id" });
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

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  bytes.forEach((value) => { binary += String.fromCharCode(value); });
  return btoa(binary);
}

function base64ToBytes(value: string): Uint8Array<ArrayBuffer> {
  const binary = atob(value);
  const buffer = new ArrayBuffer(binary.length);
  const bytes = new Uint8Array(buffer);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

async function deviceEncryptionKey(): Promise<CryptoKey | null> {
  if (deviceKeyPromise) return deviceKeyPromise;
  const loadOrCreate = async (): Promise<CryptoKey | null> => {
    if (!globalThis.crypto?.subtle) return null;
    const database = await openDatabase();
    if (!database) return null;
    const readTransaction = database.transaction(KEY_STORE, "readonly");
    const existing = await requestResult(readTransaction.objectStore(KEY_STORE).get("portal-device")) as {
      id: string;
      key: CryptoKey;
    } | undefined;
    await transactionDone(readTransaction);
    if (existing?.key) return existing.key;
    const key = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
    // Another tab may have created the device key while WebCrypto was running.
    const recheckTransaction = database.transaction(KEY_STORE, "readonly");
    const recheck = await requestResult(recheckTransaction.objectStore(KEY_STORE).get("portal-device")) as {
      id: string;
      key: CryptoKey;
    } | undefined;
    await transactionDone(recheckTransaction);
    if (recheck?.key) return recheck.key;
    const writeTransaction = database.transaction(KEY_STORE, "readwrite");
    const done = transactionDone(writeTransaction);
    writeTransaction.objectStore(KEY_STORE).put({ id: "portal-device", key, createdAt: Date.now() });
    await done;
    return key;
  };
  deviceKeyPromise = (async () => {
    const lockManager = typeof navigator === "undefined"
      ? null
      : (navigator as Navigator & {
        locks?: { request<T>(name: string, callback: () => Promise<T>): Promise<T> };
      }).locks;
    return lockManager
      ? lockManager.request("amo-portal-device-key", loadOrCreate)
      : loadOrCreate();
  })().catch(() => null);
  return deviceKeyPromise;
}

export async function encryptDeviceValue(value: unknown): Promise<EncryptedDeviceValue | null> {
  const key = await deviceEncryptionKey();
  if (!key) return null;
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const plaintext = new TextEncoder().encode(JSON.stringify(value));
  const encrypted = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, plaintext);
  return { v: 1, iv: bytesToBase64(iv), data: bytesToBase64(new Uint8Array(encrypted)) };
}

export async function decryptDeviceValue<T>(value: EncryptedDeviceValue): Promise<T> {
  const key = await deviceEncryptionKey();
  if (!key) throw new Error("This device can no longer unlock the locally saved record.");
  const decrypted = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: base64ToBytes(value.iv) },
    key,
    base64ToBytes(value.data),
  );
  return JSON.parse(new TextDecoder().decode(decrypted)) as T;
}

async function protectApiRecord(record: ApiCacheRecord): Promise<StoredApiCacheRecord> {
  const encryptedValue = await encryptDeviceValue(record.value).catch(() => null);
  if (!encryptedValue) throw new Error("Secure device storage is unavailable");
  return { ...record, value: undefined, encryptedValue };
}

async function restoreApiRecord<T>(record: StoredApiCacheRecord): Promise<ApiCacheRecord<T>> {
  if (!record.encryptedValue) return record as ApiCacheRecord<T>;
  const value = await decryptDeviceValue<T>(record.encryptedValue);
  const { encryptedValue: _encryptedValue, ...rest } = record;
  return { ...rest, value } as ApiCacheRecord<T>;
}

async function protectOutboxEntry(entry: OfflineOutboxEntry): Promise<StoredOfflineOutboxEntry> {
  if (entry.body === undefined) return entry;
  const encryptedBody = await encryptDeviceValue(entry.body).catch(() => null);
  if (!encryptedBody) throw new Error("Secure device storage is unavailable; reconnect before saving this change");
  return { ...entry, body: undefined, encryptedBody };
}

async function restoreOutboxEntry(entry: StoredOfflineOutboxEntry): Promise<OfflineOutboxEntry> {
  if (!entry.encryptedBody) return entry;
  const body = await decryptDeviceValue<string>(entry.encryptedBody);
  const { encryptedBody: _encryptedBody, ...rest } = entry;
  return { ...rest, body };
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
  offlineChannel.onmessage = (event: MessageEvent<{
    type?: string;
    detail?: OfflineSyncDetail | OfflineReplayProgress;
  }>) => {
    if (event.data?.type === "sync" && event.data.detail) {
      window.dispatchEvent(new CustomEvent<OfflineSyncDetail>(OFFLINE_SYNC_EVENT, {
        detail: event.data.detail as OfflineSyncDetail,
      }));
    }
    if (event.data?.type === "progress" && event.data.detail) {
      window.dispatchEvent(new CustomEvent<OfflineReplayProgress>(OFFLINE_PROGRESS_EVENT, {
        detail: event.data.detail as OfflineReplayProgress,
      }));
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

function notifyOfflineReplayProgress(detail: OfflineReplayProgress, broadcast = true): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<OfflineReplayProgress>(OFFLINE_PROGRESS_EVENT, { detail }));
  if (broadcast) channel()?.postMessage({ type: "progress", detail });
}

async function requestBackgroundReplay(): Promise<void> {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
  try {
    const registration = await navigator.serviceWorker.ready;
    const sync = (registration as ServiceWorkerRegistration & {
      sync?: { register(tag: string): Promise<void> };
    }).sync;
    await sync?.register("amo-portal-outbox");
  } catch {
    // Background Sync is optional; the foreground readiness monitor is authoritative.
  }
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

export function onOfflineReplayProgress(listener: (detail: OfflineReplayProgress) => void): () => void {
  if (typeof window === "undefined") return () => undefined;
  channel();
  const handler = (event: Event) => listener((event as CustomEvent<OfflineReplayProgress>).detail);
  window.addEventListener(OFFLINE_PROGRESS_EVENT, handler);
  return () => window.removeEventListener(OFFLINE_PROGRESS_EVENT, handler);
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
  await protectApiRecord(record).then((storedRecord) => putRecord(API_STORE, storedRecord)).catch((error) => {
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

  const stored = await readRecord<StoredApiCacheRecord>(API_STORE, key).catch(() => ({
    available: false,
    value: undefined,
  }));
  if (currentOfflineScope() !== scope) return null;
  if (!stored.available || !stored.value || stored.value.scope !== scope) return null;
  const restored = await restoreApiRecord<T>(stored.value).catch(() => null);
  if (!restored) return null;
  memoryApiCache.set(key, restored);
  if (!allowExpired && restored.expiresAt <= Date.now()) return null;
  return restored;
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
    nextAttemptAt: now,
  };
  if (!(await openDatabase())) {
    // Memory-only fallback is not persisted at rest, so no plaintext is left
    // on the device when secure IndexedDB/WebCrypto storage is unavailable.
    memoryOutbox.set(entry.id, entry);
    notifyOfflineStateChanged();
    return entry;
  }
  const storedEntry = await protectOutboxEntry(entry);
  await putRecord(OUTBOX_STORE, storedEntry);
  memoryOutbox.set(entry.id, entry);
  notifyOfflineStateChanged();
  void requestBackgroundReplay();
  return entry;
}

export async function listOfflineMutations(scope = currentOfflineScope()): Promise<OfflineOutboxEntry[]> {
  if (currentOfflineScope() !== scope) return [];
  const result = await recordsForScope<StoredOfflineOutboxEntry>(OUTBOX_STORE, scope).catch(() => ({
    available: false,
    value: [],
  }));
  if (currentOfflineScope() !== scope) return [];

  if (!result.available) {
    return [...memoryOutbox.values()]
      .filter((entry) => entry.scope === scope)
      .sort((left, right) => left.createdAt - right.createdAt);
  }

  const restoredEntries = (await Promise.all(
    result.value.map((entry) => restoreOutboxEntry(entry).catch(() => null)),
  )).filter((entry): entry is OfflineOutboxEntry => entry !== null);
  const storedIds = new Set(restoredEntries.map((entry) => entry.id));
  [...memoryOutbox.entries()].forEach(([id, entry]) => {
    if (entry.scope === scope && !storedIds.has(id)) memoryOutbox.delete(id);
  });
  restoredEntries.forEach((entry) => memoryOutbox.set(entry.id, entry));
  return restoredEntries.sort((left, right) => left.createdAt - right.createdAt);
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
  const stored = await readRecord<StoredOfflineOutboxEntry>(OUTBOX_STORE, id).catch(() => ({
    available: false,
    value: undefined,
  }));
  if (stored.available) {
    const restored = stored.value ? await restoreOutboxEntry(stored.value).catch(() => undefined) : undefined;
    if (restored) memoryOutbox.set(id, restored);
    else memoryOutbox.delete(id);
    return restored;
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

  const protectedNext = await protectOutboxEntry(next);
  const transaction = database.transaction(OUTBOX_STORE, "readwrite");
  const done = transactionDone(transaction);
  const store = transaction.objectStore(OUTBOX_STORE);
  const current = await requestResult(store.get(expected.id)) as StoredOfflineOutboxEntry | undefined;
  if (!current || current.updatedAt !== expected.updatedAt || current.status !== expected.status) {
    await done;
    if (!current) memoryOutbox.delete(expected.id);
    else {
      const restored = await restoreOutboxEntry(current).catch(() => undefined);
      if (restored) memoryOutbox.set(current.id, restored);
    }
    return null;
  }
  store.put(protectedNext);
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
    const current = await requestResult(store.get(expected.id)) as StoredOfflineOutboxEntry | undefined;
    if (!current || current.updatedAt !== expected.updatedAt || current.status !== expected.status) {
      await done;
      if (!current) memoryOutbox.delete(expected.id);
      else {
        const restored = await restoreOutboxEntry(current).catch(() => undefined);
        if (restored) memoryOutbox.set(current.id, restored);
      }
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
  if (entry.retryable === false) {
    throw new Error(entry.serverDetail || "This change cannot be retried unchanged. Correct the source data, then recreate it.");
  }
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
    responseStatus: undefined,
    errorCode: undefined,
    retryable: undefined,
    serverDetail: undefined,
    conflict: undefined,
    nextAttemptAt: Date.now(),
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
  const requestTimeoutMs = recommendedRequestTimeoutMs(entry.method);
  const timeout = globalThis.setTimeout(
    () => controller.abort(new DOMException("Offline replay request timed out", "AbortError")),
    requestTimeoutMs,
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
    notePortalResponse(response);
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

function normaliseReplayError(detail: unknown, status: number): {
  message: string;
  errorCode?: string;
  retryable?: boolean;
} {
  const outer = detail && typeof detail === "object" ? detail as Record<string, unknown> : null;
  const nested = outer?.detail && typeof outer.detail === "object"
    ? outer.detail as Record<string, unknown>
    : outer;
  const messageValue = nested?.detail ?? outer?.detail;
  const message = typeof messageValue === "string" && messageValue.trim()
    ? messageValue.trim()
    : typeof detail === "string" && detail.trim()
      ? detail.trim()
      : `The server rejected this change (${status}).`;
  return {
    message,
    errorCode: typeof nested?.error_code === "string" ? nested.error_code : undefined,
    retryable: typeof nested?.retryable === "boolean" ? nested.retryable : undefined,
  };
}

function retryableReplayStatus(status: number): boolean {
  return status === 401 || status === 408 || status === 425 || status === 429 || status >= 500;
}

function replayDelayMs(attempts: number, response?: Response): number {
  const headerSeconds = Number(response?.headers.get("Retry-After"));
  if (Number.isFinite(headerSeconds) && headerSeconds > 0) {
    return Math.min(5 * 60_000, Math.ceil(headerSeconds) * 1000);
  }
  const base = Math.min(60_000, 2_000 * (2 ** Math.min(Math.max(attempts - 1, 0), 5)));
  return Math.round(base * (0.8 + Math.random() * 0.4));
}

export async function replayOfflineMutations(): Promise<OfflineOutboxSummary> {
  const scope = currentOfflineScope();
  if (!isPortalReady()) return getOfflineOutboxSummary(scope);
  if (!getToken()) return getOfflineOutboxSummary(scope);
  const leaseOwner = await acquireReplayLease(scope);
  if (!leaseOwner) return getOfflineOutboxSummary(scope);

  const syncedPaths = new Set<string>();
  const syncedEntityTypes = new Set<string>();
  let synced = 0;

  try {
    const replayStartedAt = Date.now();
    const entries = (await listOfflineMutations(scope))
      .filter((entry) => (
        (entry.status === "queued" || entry.status === "syncing")
        && (!entry.nextAttemptAt || entry.nextAttemptAt <= replayStartedAt)
      ));
    if (currentOfflineScope() !== scope) return getOfflineOutboxSummary(scope);

    notifyOfflineReplayProgress({
      scope,
      phase: entries.length > 0 ? "sending" : "idle",
      current: 0,
      total: entries.length,
      synced: 0,
      message: entries.length > 0 ? `Sending 0 of ${entries.length}` : "No local changes are waiting",
    });

    for (const [index, entry] of entries.entries()) {
      if (currentOfflineScope() !== scope || entry.scope !== scope) break;
      if (!(await renewReplayLease(leaseOwner, scope))) break;
      notifyOfflineReplayProgress({
        scope,
        phase: "sending",
        current: index + 1,
        total: entries.length,
        synced,
        currentPath: entry.path,
        message: `Sending ${index + 1} of ${entries.length}`,
      });
      const syncing: OfflineOutboxEntry = {
        ...entry,
        status: "syncing",
        updatedAt: Date.now(),
        error: undefined,
        responseStatus: undefined,
        errorCode: undefined,
        retryable: undefined,
        serverDetail: undefined,
        lastAttemptAt: Date.now(),
        nextAttemptAt: undefined,
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
        const failure = normaliseReplayError(detail, response.status);
        const revisionConflict = failure.retryable === true
          || Boolean(failure.errorCode?.includes("REVISION_CONFLICT"));
        if ((response.status === 409 || response.status === 412) && revisionConflict) {
          await replaceOutboxEntry(claimed, {
            ...claimed,
            status: "conflict",
            attempts: claimed.attempts + 1,
            updatedAt: Date.now(),
            error: failure.message,
            responseStatus: response.status,
            errorCode: failure.errorCode,
            retryable: true,
            serverDetail: failure.message,
            conflict: detail,
            nextAttemptAt: undefined,
          });
          continue;
        }

        if (retryableReplayStatus(response.status)) {
          const attempts = claimed.attempts + 1;
          const nextAttemptAt = Date.now() + replayDelayMs(attempts, response);
          await replaceOutboxEntry(claimed, {
            ...claimed,
            status: "queued",
            attempts,
            updatedAt: Date.now(),
            error: response.status === 401
              ? "Session expired. This change will retry after sign-in."
              : failure.message,
            responseStatus: response.status,
            errorCode: failure.errorCode,
            retryable: true,
            serverDetail: failure.message,
            nextAttemptAt,
          });
          notifyOfflineReplayProgress({
            scope,
            phase: "paused",
            current: index + 1,
            total: entries.length,
            synced,
            currentPath: claimed.path,
            message: response.status === 401
              ? "Sign in to continue synchronising"
              : "Server recovery in progress; retry scheduled",
          });
          if (response.status === 401) handleAuthFailure("outbox-replay-unauthorized");
          break;
        }

        await replaceOutboxEntry(claimed, {
          ...claimed,
          status: "failed",
          attempts: claimed.attempts + 1,
          updatedAt: Date.now(),
          error: failure.message,
          responseStatus: response.status,
          errorCode: failure.errorCode,
          retryable: false,
          serverDetail: failure.message,
          nextAttemptAt: undefined,
        });
      } catch (error) {
        const attempts = claimed.attempts + 1;
        await replaceOutboxEntry(claimed, {
          ...claimed,
          status: "queued",
          attempts,
          updatedAt: Date.now(),
          error: error instanceof Error ? error.message : String(error),
          retryable: true,
          nextAttemptAt: Date.now() + replayDelayMs(attempts),
        });
        notifyOfflineReplayProgress({
          scope,
          phase: "paused",
          current: index + 1,
          total: entries.length,
          synced,
          currentPath: claimed.path,
          message: "Connection interrupted; retry scheduled",
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
  const finalSummary = await getOfflineOutboxSummary(scope);
  notifyOfflineReplayProgress({
    scope,
    phase: finalSummary.queued > 0 ? "paused" : "complete",
    current: synced,
    total: synced + finalSummary.total,
    synced,
    message: finalSummary.queued > 0
      ? `${finalSummary.queued} local change${finalSummary.queued === 1 ? "" : "s"} waiting for retry`
      : synced > 0 ? `${synced} change${synced === 1 ? "" : "s"} confirmed` : "Up to date",
  });
  return finalSummary;
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
