export type PdfVirtualMeasurement = {
  index: number;
  start: number;
  end: number;
  size: number;
};

export function selectPdfVirtualPage(
  measurements: Iterable<PdfVirtualMeasurement>,
  scrollOffset: number,
  viewportSize: number,
  anchorOffset = 24,
): number | null {
  if (!(viewportSize > 0)) return null;
  const anchor = Math.max(0, scrollOffset) + Math.min(
    Math.max(0, anchorOffset),
    Math.max(0, viewportSize - 1),
  );
  const rows = [...measurements].filter((row) => (
    Number.isInteger(row.index)
    && row.index >= 0
    && Number.isFinite(row.start)
    && Number.isFinite(row.end)
    && row.end > row.start
  ));
  if (!rows.length) return null;

  const containing = rows.find((row) => row.start <= anchor && row.end > anchor);
  if (containing) return containing.index + 1;

  rows.sort((left, right) => {
    const leftDistance = Math.min(Math.abs(left.start - anchor), Math.abs(left.end - anchor));
    const rightDistance = Math.min(Math.abs(right.start - anchor), Math.abs(right.end - anchor));
    return leftDistance - rightDistance || left.index - right.index;
  });
  return rows[0].index + 1;
}

export function updatePdfRetainedPages(
  current: readonly number[],
  page: number,
  limit: number,
): number[] {
  const normalized = Math.max(1, Math.trunc(page));
  const next = current.filter((value) => value !== normalized && Number.isInteger(value) && value > 0);
  next.push(normalized);
  return next.slice(-Math.max(1, Math.trunc(limit)));
}

export function prioritizePdfRenderIndexes(
  visibleIndexes: readonly number[],
  retainedPages: readonly number[],
  targetPage: number | null,
  currentPage: number,
  pageCount: number,
  limit: number,
): number[] {
  const count = Math.max(0, Math.trunc(pageCount));
  if (!count) return [];
  const targetIndex = targetPage && targetPage > 0 ? targetPage - 1 : null;
  const currentIndex = Math.max(0, Math.min(count - 1, Math.trunc(currentPage) - 1));
  const priority: number[] = [];
  const push = (index: number) => {
    if (!Number.isInteger(index) || index < 0 || index >= count || priority.includes(index)) return;
    priority.push(index);
  };

  if (targetIndex !== null) push(targetIndex);
  [...visibleIndexes]
    .sort((left, right) => {
      const anchor = targetIndex ?? currentIndex;
      return Math.abs(left - anchor) - Math.abs(right - anchor) || left - right;
    })
    .forEach(push);
  [...retainedPages].reverse().map((page) => page - 1).forEach(push);
  push(currentIndex);

  return priority.slice(0, Math.max(1, visibleIndexes.length, Math.trunc(limit)));
}
