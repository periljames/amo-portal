import type { PersistedClient, Persister } from "@tanstack/react-query-persist-client";

import { currentOfflineScope } from "./offlinePersistence";

const DATABASE_NAME = "amo-portal-query-cache";
const DATABASE_VERSION = 1;
const STORE_NAME = "persisted_clients";
const CACHE_KEY = "tanstack-query-cache-v2";

let databasePromise: Promise<IDBDatabase | null> | null = null;
let memoryClient: PersistedClient | undefined;

function storageKey(): string {
  return `${currentOfflineScope()}:${CACHE_KEY}`;
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
  });
  return databasePromise;
}

export function createPortalQueryPersister(): Persister {
  return {
    async persistClient(client: PersistedClient): Promise<void> {
      memoryClient = client;
      const database = await openDatabase();
      if (!database) return;
      const transaction = database.transaction(STORE_NAME, "readwrite");
      transaction.objectStore(STORE_NAME).put(client, storageKey());
      await transactionDone(transaction);
    },

    async restoreClient(): Promise<PersistedClient | undefined> {
      const database = await openDatabase();
      if (!database) return memoryClient;
      const transaction = database.transaction(STORE_NAME, "readonly");
      const client = await requestResult<PersistedClient | undefined>(
        transaction.objectStore(STORE_NAME).get(storageKey()),
      );
      await transactionDone(transaction);
      memoryClient = client;
      return client;
    },

    async removeClient(): Promise<void> {
      memoryClient = undefined;
      const database = await openDatabase();
      if (!database) return;
      const transaction = database.transaction(STORE_NAME, "readwrite");
      transaction.objectStore(STORE_NAME).delete(storageKey());
      await transactionDone(transaction);
    },
  } satisfies Persister;
}

export async function clearAllPortalQueryCaches(): Promise<void> {
  memoryClient = undefined;
  const database = await openDatabase();
  if (!database) return;
  const transaction = database.transaction(STORE_NAME, "readwrite");
  transaction.objectStore(STORE_NAME).clear();
  await transactionDone(transaction).catch(() => undefined);
}
