/** Optional device reads cannot gate login or online navigation. Durable writes are never raced. */
export async function optionalStorageRead<T>(read: () => Promise<T>, fallback: T, timeoutMs = 800): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      Promise.resolve().then(read).catch(() => fallback),
      new Promise<T>(resolve => { timer = setTimeout(() => resolve(fallback), timeoutMs); }),
    ]);
  } finally { if (timer !== undefined) clearTimeout(timer); }
}
