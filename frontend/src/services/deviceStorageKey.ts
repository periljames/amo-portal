/** Select one non-extractable device key atomically, including across tabs. */
export async function getOrCreateDeviceStorageKey(database: IDBDatabase, storeName: string, id: string): Promise<CryptoKey> {
  const existing = await new Promise<CryptoKey | undefined>((resolve, reject) => {
    const transaction = database.transaction(storeName, "readonly");
    const request = transaction.objectStore(storeName).get(id);
    transaction.oncomplete = () => resolve(request.result?.key);
    transaction.onabort = transaction.onerror = () => reject(transaction.error || new Error("Device key could not be read."));
  });
  if (existing) return existing;
  // Crypto work must finish before opening the write transaction. Keeping the
  // final read and conditional insert in that transaction prevents overwrites.
  const candidate = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
  return new Promise<CryptoKey>((resolve, reject) => {
    const transaction = database.transaction(storeName, "readwrite");
    const store = transaction.objectStore(storeName);
    const request = store.get(id);
    let selected: CryptoKey;
    request.onsuccess = () => {
      selected = request.result?.key || candidate;
      if (!request.result?.key) store.add({ id, key: selected, createdAt: Date.now() });
    };
    transaction.oncomplete = () => resolve(selected);
    transaction.onabort = transaction.onerror = () => reject(transaction.error || new Error("Device key could not be saved."));
  });
}
