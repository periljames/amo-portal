import { qmsListAuditPersonnelOptions as qmsListCoreAuditPersonnelOptions, type QMSPersonOption } from "./qmsCore";

export type QMSAuditPersonnelOptionsParams = {
  search?: string;
  limit?: number;
};

/**
 * Load audit personnel through the registered Quality personnel endpoint.
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

  return qmsListCoreAuditPersonnelOptions({
    limit,
    ...(search ? { search } : {}),
  });
}
