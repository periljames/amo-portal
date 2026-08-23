import { qmsListAuditPersonnelOptions as qmsListLegacyAuditPersonnelOptions, type QMSPersonOption } from "./qmsLegacy";

export type QMSAuditPersonnelOptionsParams = {
  search?: string;
  limit?: number;
};

/**
 * Load audit personnel through the registered Quality personnel endpoint.
 *
 * The canonical AMO-scoped router does not currently expose
 * `/audits/personnel/options`; sending this request through `qmsPath(...)`
 * therefore falls into the generic canonical catch-all, whose response shape
 * and limit contract do not match `QMSPersonOption[]`. Keep this compatibility
 * call on the explicit `/quality/audits/personnel/options` handler until a
 * dedicated canonical route is registered and covered by backend tests.
 *
 * The explicit personnel handler caps `limit` at 100 and `search` at 100
 * characters. Enforce those bounds centrally so stale callers cannot produce
 * FastAPI 422 responses.
 */
export async function qmsListAuditPersonnelOptions(
  params?: QMSAuditPersonnelOptionsParams,
): Promise<QMSPersonOption[]> {
  const requestedLimit = Number.isFinite(params?.limit) ? Math.trunc(params!.limit!) : 50;
  const limit = Math.min(100, Math.max(1, requestedLimit));
  const search = params?.search?.trim().slice(0, 100) || "";

  return qmsListLegacyAuditPersonnelOptions({
    limit,
    ...(search ? { search } : {}),
  });
}
