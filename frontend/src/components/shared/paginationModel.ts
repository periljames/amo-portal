export function pageNumbers(page: number, total?: number, hasNext = false): Array<number | string> {
  const last = total == null ? page + (hasNext ? 1 : 0) : Math.max(1, total);
  const values = [...new Set([1, page - 1, page, page + 1, ...(total != null ? [last] : [])])].filter(n => n >= 1 && n <= last).sort((a,b) => a-b);
  const result: Array<number | string> = [];
  values.forEach((n,i) => { if(i && n-values[i-1]>1) result.push(`gap-${n}`); result.push(n); });
  return result;
}
