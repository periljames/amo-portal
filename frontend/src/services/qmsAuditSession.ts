import { apiRequest, qmsPath } from "./apiClient";
import { projectOfflineAuditSession, readAuditOfflinePack } from "./qmsAuditOfflinePack";
import { requireAuditContract } from "./qmsAuditWorkflowContract";

export type AuditSessionStageId = "setup" | "prepare" | "live" | "closing" | "follow-up" | "archive";

export type AuditSessionStage = {
  id: AuditSessionStageId;
  label: string;
  complete: boolean;
  active: boolean;
  legacy_tab: string;
  helper: string;
};

export type AuditSession = {
  audit_id: string;
  current_stage_id: AuditSessionStageId;
  current_stage_label: string;
  percent_complete: number;
  stages: AuditSessionStage[];
  source_workflow_stage_id: string;
  source_workflow_percent_complete: number;
  preparation_issued: boolean;
  execution_status: string;
  follow_up_status: string;
  archive_count: number;
  fieldwork_access?: { ready: boolean; blocker: string | null };
};

export async function getAuditSession(amoCode: string, auditId: string, signal?: AbortSignal) {
  const readOffline = async () => {
    const pack = await readAuditOfflinePack(amoCode, auditId);
    if (!pack?.fieldwork_state.authorized) return null;
    return requireAuditContract(projectOfflineAuditSession(pack) as AuditSession, "session");
  };
  if (typeof navigator !== "undefined" && !navigator.onLine) {
    const offline = await readOffline();
    if (offline) return offline;
  }
  try {
    const session = await apiRequest<AuditSession>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/session`), {
      timeoutMs: 15_000,
      cacheTtlMs: 2_000,
      signal,
    });
    return requireAuditContract(session, "session");
  } catch (error) {
    const message = error instanceof Error ? error.message.toLowerCase() : "";
    if (!message.includes("offline") && !message.includes("could not be reached") && !message.includes("cached copy")) throw error;
    const offline = await readOffline();
    if (offline) return offline;
    throw error;
  }
}

export function completeAuditFieldwork(amoCode: string, auditId: string) {
  return apiRequest<Record<string, unknown>>(
    qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/fieldwork/complete`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
      timeoutMs: 30_000,
    },
  );
}
