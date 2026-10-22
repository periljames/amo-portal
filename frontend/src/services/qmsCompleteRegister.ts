/** Read bounded pages, but never present a partial population as complete analysis. */
export async function readCompleteRegister<T extends { id: string }>(
  read: (offset: number) => Promise<{ items: T[]; total: number; limit: number; offset: number; has_more: boolean }>,
  signal: AbortSignal,
): Promise<T[]> {
  const items: T[] = [];
  const seen = new Set<string>();
  let offset = 0;
  let expectedTotal: number | undefined;
  for (;;) {
    signal.throwIfAborted();
    const page = await read(offset);
    signal.throwIfAborted();
    if (!Number.isSafeInteger(page.total) || page.total < 0 || page.offset !== offset || !Array.isArray(page.items)) {
      throw new Error("The analysis source returned invalid paging information. Refresh to retry.");
    }
    expectedTotal ??= page.total;
    if (page.total !== expectedTotal) throw new Error("Records changed while loading analysis. Refresh to load a consistent population.");
    for (const item of page.items) {
      if (!item.id || seen.has(item.id)) throw new Error("The analysis source repeated a record. Refresh to retry.");
      seen.add(item.id);
      items.push(item);
    }
    if (!page.has_more) {
      if (items.length !== expectedTotal) throw new Error("The analysis source is incomplete. Refresh to retry.");
      return items;
    }
    if (!page.items.length || !Number.isSafeInteger(page.limit) || page.limit <= 0 || items.length >= expectedTotal) {
      throw new Error("The analysis source could not advance to the next page. Refresh to retry.");
    }
    offset += page.limit;
  }
}
