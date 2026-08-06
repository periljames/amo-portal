export type VirtualPageEntry = {
  index: number;
  start: number;
  end: number;
};

export function selectPhysicalVirtualPage(
  items: VirtualPageEntry[],
  scrollTop: number,
  inset = 0,
): number | null {
  if (!items.length) return null;
  const anchor = Math.max(0, scrollTop + Math.max(0, inset));
  const containing = items.find((item) => item.start <= anchor && item.end > anchor);
  const closest = containing || items.reduce((best, item) => (
    Math.abs(item.start - anchor) < Math.abs(best.start - anchor) ? item : best
  ), items[0]);
  return closest.index + 1;
}

export function nextHotPageIndexes(
  currentIndexes: number[],
  physicalPage: number,
  pageCount: number,
  limit: number,
): number[] {
  if (!Number.isInteger(physicalPage) || physicalPage < 1 || pageCount < 1) return [];
  const candidates = [
    physicalPage - 1,
    physicalPage,
    physicalPage + 1,
    ...currentIndexes.map((index) => index + 1),
  ]
    .filter((page) => page >= 1 && page <= pageCount)
    .map((page) => page - 1);
  return [...new Set(candidates)].slice(0, Math.max(1, limit));
}
