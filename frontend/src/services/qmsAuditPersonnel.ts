import { apiRequest, qmsPath } from "./apiClient";
import { getContext } from "./auth";
import type { QMSPersonOption } from "./qmsLegacy";

export type QMSAuditPersonnelOptionsParams = {
  search?: string;
  limit?: number;
};

/**
 * Load audit personnel through the canonical tenant-scoped Quality API.
 *
 * The backend contract caps `limit` at 100 and `search` at 100 characters.
 * Enforce those bounds here so individual screens cannot accidentally create
 * FastAPI 422 responses or fall back to the legacy global `/quality` surface.
 */
export async function qmsListAuditPersonnelOptions(
  params?: QMSAuditPersonnelOptionsParams,
): Promise<QMSPersonOption[]> {
  const context = getContext();
  const amoCode = (context.amoSlug || context.amoCode || "").trim();
  if (!amoCode) throw new Error("AMO context is required to load audit personnel.");

  const requestedLimit = Number.isFinite(params?.limit) ? Math.trunc(params!.limit!) : 50;
  const limit = Math.min(100, Math.max(1, requestedLimit));
  const search = params?.search?.trim().slice(0, 100) || "";
  const query = new URLSearchParams({ limit: String(limit) });
  if (search) query.set("search", search);

  return apiRequest<QMSPersonOption[]>(
    qmsPath(amoCode, `/audits/personnel/options?${query.toString()}`),
    { timeoutMs: 15_000, cacheTtlMs: 30_000 },
  );
}
