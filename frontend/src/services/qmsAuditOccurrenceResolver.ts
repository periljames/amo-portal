import { apiRequest, qmsPath } from "./apiClient";
import type { QMSAuditOut } from "./qms";
import { readAuditOfflinePackByKey } from "./qmsAuditOfflinePack";

export type AuditOccurrenceSetupUpdate = {
  title?: string | null;
  scope?: string | null;
  objectives?: string | null;
  criteria?: string | null;
  auditee?: string | null;
  auditee_email?: string | null;
  planned_start?: string | null;
  planned_end?: string | null;
  planned_start_time?: string | null;
  planned_end_time?: string | null;
  notify_auditors?: boolean | null;
  notify_auditees?: boolean | null;
  reminder_interval_days?: number | null;
  reschedule_reason?: string | null;
  base_version?: number | null;
};

export function auditOccurrenceResolverKey(auditKey: string): string {
  const key = auditKey.trim();
  if (!key) return "";

  // FastAPI decodes percent-encoded slashes before matching a normal path
  // parameter, so a reference such as QAR/MO/26/015 cannot safely be sent as
  // one encoded {audit_key} segment. The backend resolver already supports this
  // deterministic separator-normalised slug when matching audit_ref.
  return key
    .toLowerCase()
    .replaceAll("/", "-")
    .replaceAll("_", "-")
    .replaceAll(" ", "-")
    .replaceAll(".", "-")
    .replace(/^-+|-+$/g, "");
}

/** One cache identity for every panel that resolves the same audit occurrence. */
export function auditOccurrenceQueryKey(amoCode: string, auditKey: string) {
  return ["qms", "audit-occurrence", amoCode.trim().toLowerCase(), auditOccurrenceResolverKey(auditKey)] as const;
}

export async function resolveAuditOccurrence(amoCode: string, auditKey: string, signal?: AbortSignal): Promise<QMSAuditOut> {
  const key = auditOccurrenceResolverKey(auditKey);
  if (!key) throw new Error("Audit occurrence key is required.");
  const readOffline = async () => {
    const pack = await readAuditOfflinePackByKey(amoCode, key);
    if (!pack?.fieldwork_state.authorized) return null;
    const audit = pack.work_package.package_snapshot.audit;
    if (!audit.id || !audit.audit_ref || !audit.title) return null;
    return audit as unknown as QMSAuditOut;
  };
  if (typeof navigator !== "undefined" && !navigator.onLine) {
    const offline = await readOffline();
    if (offline) return offline;
    throw new Error("This audit is unavailable offline on this device. Reconnect and use Make available offline from Prepare before fieldwork.");
  }
  try {
    return await apiRequest<QMSAuditOut>(
      qmsPath(amoCode, `/audits/resolve/${encodeURIComponent(key)}`),
      { timeoutMs: 15_000, cacheTtlMs: 5_000, signal },
    );
  } catch (error) {
    const message = error instanceof Error ? error.message.toLowerCase() : "";
    if (!message.includes("offline") && !message.includes("could not be reached") && !message.includes("cached copy")) throw error;
    const offline = await readOffline();
    if (offline) return offline;
    throw error;
  }
}

export function updateAuditOccurrenceSetup(
  amoCode: string,
  auditId: string,
  payload: AuditOccurrenceSetupUpdate,
): Promise<QMSAuditOut> {
  const id = auditId.trim();
  if (!id) return Promise.reject(new Error("Audit occurrence ID is required."));
  return apiRequest<QMSAuditOut>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(id)}/setup`),
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      timeoutMs: 15_000,
    },
  );
}
