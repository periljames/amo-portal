import type { RealtimeEnvelope } from "./types";

const DB_NAME = "amo-realtime";
const STORE = "outbound";
export const MAX_OUTBOUND_MESSAGES = 500;

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: "id" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export function sanitizeOutbound(envelope: RealtimeEnvelope): RealtimeEnvelope {
  const clean = { ...envelope };
  delete clean.authToken;
  return clean;
}

async function readAll(db: IDBDatabase): Promise<RealtimeEnvelope[]> {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const req = tx.objectStore(STORE).getAll();
    req.onsuccess = () => {
      const rows = (req.result || []) as RealtimeEnvelope[];
      resolve(rows.map(sanitizeOutbound).sort((a, b) => a.ts - b.ts || a.id.localeCompare(b.id)));
    };
    req.onerror = () => reject(req.error);
  });
}

export async function queueOutbound(envelope: RealtimeEnvelope): Promise<void> {
  const db = await openDb();
  try {
    const clean = sanitizeOutbound(envelope);
    const existing = await readAll(db);
    const excess = Math.max(0, existing.length + (existing.some((row) => row.id === clean.id) ? 0 : 1) - MAX_OUTBOUND_MESSAGES);
    const idsToRemove = existing.slice(0, excess).map((row) => row.id);
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      const store = tx.objectStore(STORE);
      for (const id of idsToRemove) store.delete(id);
      store.put(clean);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error || new Error("Realtime outbox transaction aborted"));
    });
  } finally {
    db.close();
  }
}

export async function loadOutbound(): Promise<RealtimeEnvelope[]> {
  const db = await openDb();
  try {
    return await readAll(db);
  } finally {
    db.close();
  }
}

export async function removeOutbound(id: string): Promise<void> {
  const db = await openDb();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      tx.objectStore(STORE).delete(id);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error || new Error("Realtime outbox transaction aborted"));
    });
  } finally {
    db.close();
  }
}
