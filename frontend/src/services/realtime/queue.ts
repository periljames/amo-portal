import type { RealtimeEnvelope } from "./types";

const DB_NAME = "amo-realtime";
const STORE = "outbound";
export const MAX_OUTBOUND_MESSAGES = 500;
export type OutboundScope = Pick<RealtimeEnvelope, "amoId" | "userId">;
function sameScope(row: OutboundScope, scope: OutboundScope): boolean {
  return row.amoId === scope.amoId && row.userId === scope.userId;
}

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
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      const store = tx.objectStore(STORE);
      const request = store.getAll();
      request.onsuccess = () => {
        const rows = request.result as RealtimeEnvelope[];
        const duplicate = rows.find((row) => row.id === clean.id);
        if ((duplicate && !sameScope(duplicate, clean))
          || (!duplicate && rows.filter((row) => sameScope(row, clean)).length >= MAX_OUTBOUND_MESSAGES)) {
          reject(new Error("The message queue is full or this message ID belongs to another account. Existing unsent messages were retained."));
          tx.abort();
          return;
        }
        store.put(clean);
      };
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error || new Error("Realtime outbox transaction aborted"));
    });
  } finally {
    db.close();
  }
}

export async function loadOutbound(scope: OutboundScope): Promise<RealtimeEnvelope[]> {
  const db = await openDb();
  try {
    return (await readAll(db)).filter((row) => sameScope(row, scope));
  } finally {
    db.close();
  }
}

export async function removeOutbound(id: string, scope: OutboundScope): Promise<void> {
  const db = await openDb();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, "readwrite");
      const store = tx.objectStore(STORE);
      const request = store.get(id);
      request.onsuccess = () => {
        if (request.result && sameScope(request.result, scope)) store.delete(id);
      };
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error || new Error("Realtime outbox transaction aborted"));
    });
  } finally {
    db.close();
  }
}
