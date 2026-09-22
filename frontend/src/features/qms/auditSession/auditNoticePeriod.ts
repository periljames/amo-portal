/** True when notice_date does not leave the configured lead time before planned start. */
export function auditNoticePeriodInsufficient(input: {
  plannedStart?: string | null;
  noticeDate?: string | null;
  requiredNoticeDays?: number | null;
}): boolean {
  const planned = (input.plannedStart || "").slice(0, 10);
  const notice = (input.noticeDate || "").slice(0, 10);
  const days = Math.max(0, Number(input.requiredNoticeDays ?? 0));
  if (!/^\d{4}-\d{2}-\d{2}$/.test(planned) || !/^\d{4}-\d{2}-\d{2}$/.test(notice)) {
    return false;
  }
  const plannedMs = Date.parse(`${planned}T12:00:00`);
  const noticeMs = Date.parse(`${notice}T12:00:00`);
  if (!Number.isFinite(plannedMs) || !Number.isFinite(noticeMs)) return false;
  const latestPermitted = plannedMs - days * 86_400_000;
  return noticeMs > latestPermitted;
}
