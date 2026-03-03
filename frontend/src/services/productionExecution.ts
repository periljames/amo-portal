import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";
import { apiGet, apiPost } from "./crs";

export type ExecutionEvidence = {
  id: number;
  work_order_id: number;
  task_card_id?: number | null;
  file_name: string;
  storage_path: string;
  content_type?: string | null;
  notes?: string | null;
  created_at: string;
};

export type ReleaseGate = {
  id: number;
  work_order_id: number;
  status: string;
  readiness_notes?: string | null;
  blockers_json: string[];
  evidence_count: number;
  signed_off_by_user_id?: string | null;
  signed_off_at?: string | null;
  handed_to_records: boolean;
  handed_to_records_at?: string | null;
  updated_at: string;
};

function evidencePath(workOrderId?: number): string {
  if (!workOrderId) return "/records/production/evidence";
  const params = new URLSearchParams({ work_order_id: String(workOrderId) });
  return `/records/production/evidence?${params.toString()}`;
}

export const listExecutionEvidence = (workOrderId?: number) =>
  apiGet<ExecutionEvidence[]>(evidencePath(workOrderId), { headers: authHeaders() });

export async function uploadExecutionEvidence(
  workOrderId: number,
  file: File,
  taskCardId?: number,
  notes?: string,
): Promise<ExecutionEvidence> {
  const form = new FormData();
  form.append("work_order_id", String(workOrderId));
  if (typeof taskCardId === "number") form.append("task_card_id", String(taskCardId));
  if (notes) form.append("notes", notes);
  form.append("file", file);

  const res = await fetch(`${getApiBaseUrl()}/records/production/evidence/upload`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
    credentials: "include",
  });
  if (!res.ok) throw new Error(await res.text());
  return (await res.json()) as ExecutionEvidence;
}

export const listReleaseGates = () =>
  apiGet<ReleaseGate[]>("/records/production/release-gates", { headers: authHeaders() });

export const upsertReleaseGate = (payload: {
  work_order_id: number;
  status: string;
  readiness_notes?: string;
  blockers_json?: string[];
  handed_to_records?: boolean;
  sign_off?: boolean;
}) => apiPost<ReleaseGate>("/records/production/release-gates", payload, { headers: authHeaders() });
