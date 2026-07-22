import type { PersistedClient, Persister } from "@tanstack/react-query-persist-client";

import { currentOfflineScope } from "./offlinePersistence";

const DATABASE_NAME = "amo-portal-query-cache";
const DATABASE_VERSION = 1;
const STORE_NAME = "persisted_clients";
const CACHE_KEY = "tanstack-query-cache-v3";

type ScopedPersistedClient = {
  scope: string;
  client: PersistedClient;
};

type ScopeChangeHandler = (previousScope: string, nextScope: string) => void;

let databasePromise: Promise<IDBDatabase | null> | null = null;
const memoryClients = new Map<string, PersistedClient>();

function storageKey(scope: string): string {
  return `${scope}:${CACHE_KEY}`;
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
  if (typeof window === "undefined" || !window.indexedDB) return null;
  if (databasePromise) return databasePromise;

  databasePromise = new Promise<IDBDatabase | null>((resolve) => {
    const request = window.indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(STORE_NAME)) {
        database.createObjectStore(STORE_NAME);
      }
    };
    request.onsuccess = () => {
      const database = request.result;
      database.onversionchange = () => database.close();
      resolve(database);
    };
    request.onerror = () => {
      console.warn("[query-cache] IndexedDB unavailable; using memory fallback", request.error);
      resolve(null);
    };
    request.onblocked = () => console.warn("[query-cache] IndexedDB upgrade blocked by another portal tab");
  });
  return databasePromise;
}

export function createPortalQueryPersister(onScopeChange?: ScopeChangeHandler): Persister {
  // The QueryClient belongs to the scope active when the provider is hydrated.
  // A context switch must clear the QueryClient before a snapshot can be rebound.
  let boundScope = currentOfflineScope();

  return {
    async persistClient(client: PersistedClient): Promise<void> {
      const scope = currentOfflineScope();
      if (scope !== boundScope) {
        // Reject the first snapshot after a context switch. It can still contain
        // the previous AMO's queries. Set the new binding before notifying the
        // runtime so QueryClient.clear() cannot recursively report the same switch.
        const previousScope = boundScope;
        boundScope = scope;
        onScopeChange?.(previousScope, scope);
        return;
      }

      memoryClients.set(scope, client);
      const database = await openDatabase();
      if (!database || currentOfflineScope() !== scope) return;
      const transaction = database.transaction(STORE_NAME, "readwrite");
      const done = transactionDone(transaction);
      const record: ScopedPersistedClient = { scope, client };
      transaction.objectStore(STORE_NAME).put(record, storageKey(scope));
      await done;
    },

    async restoreClient(): Promise<PersistedClient | undefined> {
      const scope = currentOfflineScope();
      boundScope = scope;
      const database = await openDatabase();
      if (!database) return memoryClients.get(scope);
      if (currentOfflineScope() !== scope) return undefined;

      const transaction = database.transaction(STORE_NAME, "readonly");
      const done = transactionDone(transaction);
      const record = await requestResult<ScopedPersistedClient | undefined>(
        transaction.objectStore(STORE_NAME).get(storageKey(scope)),
      );
      await done;
      if (!record || record.scope !== scope) return memoryClients.get(scope);
      memoryClients.set(scope, record.client);
      return record.client;
    },

    async removeClient(): Promise<void> {
      const scope = currentOfflineScope();
      boundScope = scope;
      memoryClients.delete(scope);
      const database = await openDatabase();
      if (!database) return;
      const transaction = database.transaction(STORE_NAME, "readwrite");
      const done = transactionDone(transaction);
      transaction.objectStore(STORE_NAME).delete(storageKey(scope));
      await done;
    },
  } satisfies Persister;
}

export async function clearAllPortalQueryCaches(): Promise<void> {
  memoryClients.clear();
  const database = await openDatabase();
  if (!database) return;
  const transaction = database.transaction(STORE_NAME, "readwrite");
  const done = transactionDone(transaction);
  transaction.objectStore(STORE_NAME).clear();
  await done.catch(() => undefined);
}
