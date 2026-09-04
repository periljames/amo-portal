import { apiRequest, qmsPath } from "./apiClient";

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
};

export function getAuditSession(amoCode: string, auditId: string, signal?: AbortSignal) {
  return apiRequest<AuditSession>(qmsPath(amoCode, `/audits/${encodeURIComponent(auditId)}/session`), {
    timeoutMs: 15_000,
    cacheTtlMs: 2_000,
    signal,
  });
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
