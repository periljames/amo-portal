import { currentOfflineScope, encryptDeviceValue, decryptDeviceValue, type EncryptedDeviceValue } from "./offlinePersistence";

type Row = { key: string; scope: string; encrypted: EncryptedDeviceValue };
const DATABASE = "amo-qms-fieldwork-journal";
function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 1);
    request.onupgradeneeded = () => request.result.createObjectStore("entries", { keyPath: "key" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}
/** No expiry: pending work is never discarded because a day has passed. */
export async function saveFieldworkJournal(amoCode: string, auditId: string, value: unknown): Promise<void> {
  const scope = currentOfflineScope();
  if (scope.startsWith("anonymous:")) throw new Error("Sign in before saving audit work on this device.");
  const encrypted = await encryptDeviceValue(value);
  if (!encrypted) throw new Error("Secure device storage is unavailable. Keep this page open and retry.");
  const db = await open();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction("entries", "readwrite");
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error || new Error("Device storage was interrupted."));
      tx.objectStore("entries").put({ key: `${scope}:${amoCode}:${auditId}`, scope, encrypted } satisfies Row);
    });
  } finally { db.close(); }
}
export async function readFieldworkJournal<T>(amoCode: string, auditId: string): Promise<T | null> {
  const scope = currentOfflineScope();
  const db = await open();
  try {
    const row = await new Promise<Row | undefined>((resolve, reject) => {
      const request = db.transaction("entries", "readonly").objectStore("entries").get(`${scope}:${amoCode}:${auditId}`);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    return row?.scope === scope ? decryptDeviceValue<T>(row.encrypted) : null;
  } finally { db.close(); }
}
