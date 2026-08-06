import { authHeaders } from "./auth";
import { apiGet, apiPost, apiPut } from "./crs";

export type MigrationDataset =
  | "AIRCRAFT_MASTER"
  | "UTILISATION"
  | "COMPONENT"
  | "AMP_BASELINE"
  | "DEFERRAL"
  | "MAINTENANCE_RECORD";

export type MigrationRow = {
  id: string;
  batch_id: string;
  dataset: MigrationDataset;
  source_row_number: number;
  source_key: string;
  raw_json: Record<string, unknown>;
  normalized_json: Record<string, unknown>;
  status: string;
  action: string;
  errors_json: unknown[];
  warnings_json: unknown[];
  local_object_type?: string | null;
  local_object_id?: string | null;
  applied_at?: string | null;
};

export type MigrationReconciliation = {
  id: string;
  batch_id: string;
  row_id: string;
  category: string;
  severity: string;
  status: string;
  summary: string;
  source_json: Record<string, unknown>;
  local_json: Record<string, unknown>;
  differences_json: Record<string, unknown>;
  resolution?: string | null;
  resolution_notes?: string | null;
};

export type MigrationCheckpoint = {
  id: string;
  batch_id: string;
  checkpoint_key: string;
  label: string;
  status: "PENDING" | "COMPLETE" | "BLOCKED" | "NOT_APPLICABLE";
  evidence_json: string[];
  notes?: string | null;
  completed_at?: string | null;
};

export type MigrationBatch = {
  id: string;
  name: string;
  preset?: string | null;
  target_aircraft_serial_number?: string | null;
  target_registration?: string | null;
  source_type: string;
  source_reference?: string | null;
  status: string;
  mode: string;
  scope_json: Record<string, unknown>;
  summary_json: Record<string, unknown>;
  cutover_checklist_json: Record<string, unknown>;
  rollback_manifest_json: Array<Record<string, unknown>>;
  approved_at?: string | null;
  committed_at?: string | null;
  created_at: string;
  updated_at: string;
  rows: MigrationRow[];
  reconciliation_items: MigrationReconciliation[];
  checkpoints: MigrationCheckpoint[];
};

export type MigrationSummary = {
  batches: number;
  active_batches: number;
  open_reconciliation: number;
  staged_rows: number;
  applied_rows: number;
  failed_rows: number;
  latest_batch?: MigrationBatch | null;
};

export function getMigrationSummary() {
  return apiGet<MigrationSummary>("/integrations/migration/summary", { headers: authHeaders() });
}

export function listMigrationBatches() {
  return apiGet<MigrationBatch[]>("/integrations/migration/batches", { headers: authHeaders() });
}

export function createFiveYSlsPilot(sourceReference?: string) {
  return apiPost<MigrationBatch>(
    "/integrations/migration/presets/5y-sls",
    { source_reference: sourceReference || null },
    { headers: authHeaders() },
  );
}

export function stageMigrationRows(
  batchId: string,
  rows: Array<{ dataset: MigrationDataset; source_key: string; payload: Record<string, unknown> }>,
  replaceExistingStage = false,
) {
  return apiPost<MigrationBatch>(
    `/integrations/migration/batches/${encodeURIComponent(batchId)}/stage`,
    { rows, replace_existing_stage: replaceExistingStage },
    { headers: authHeaders() },
  );
}

export function validateMigrationBatch(batchId: string) {
  return apiPost<MigrationBatch>(
    `/integrations/migration/batches/${encodeURIComponent(batchId)}/validate`,
    {},
    { headers: authHeaders() },
  );
}

export function reconcileMigrationBatch(batchId: string) {
  return apiPost<MigrationBatch>(
    `/integrations/migration/batches/${encodeURIComponent(batchId)}/reconcile`,
    {},
    { headers: authHeaders() },
  );
}

export function decideMigrationReconciliation(
  batchId: string,
  itemId: string,
  resolution: "ACCEPT_SOURCE" | "KEEP_LOCAL" | "MERGE" | "WAIVE",
  resolutionNotes: string,
  mergedPayload?: Record<string, unknown>,
) {
  return apiPost<MigrationReconciliation>(
    `/integrations/migration/batches/${encodeURIComponent(batchId)}/reconciliation/${encodeURIComponent(itemId)}/decision`,
    { resolution, resolution_notes: resolutionNotes, merged_payload: mergedPayload },
    { headers: authHeaders() },
  );
}

export function updateMigrationCheckpoint(
  batchId: string,
  checkpointKey: string,
  status: MigrationCheckpoint["status"],
  notes?: string,
  evidence: string[] = [],
) {
  return apiPut<MigrationCheckpoint>(
    `/integrations/migration/batches/${encodeURIComponent(batchId)}/checkpoints/${encodeURIComponent(checkpointKey)}`,
    { status, notes: notes || null, evidence_json: evidence },
    { headers: authHeaders() },
  );
}

export function approveMigrationBatch(batchId: string, approvalNotes: string) {
  return apiPost<MigrationBatch>(
    `/integrations/migration/batches/${encodeURIComponent(batchId)}/approve`,
    { approval_notes: approvalNotes },
    { headers: authHeaders() },
  );
}

export function commitMigrationBatch(batchId: string, commitNotes: string, allowPartial = false) {
  return apiPost<MigrationBatch>(
    `/integrations/migration/batches/${encodeURIComponent(batchId)}/commit`,
    { commit_notes: commitNotes, allow_partial: allowPartial },
    { headers: authHeaders() },
  );
}

export function rollbackMigrationBatch(batchId: string, reason: string) {
  return apiPost<MigrationBatch>(
    `/integrations/migration/batches/${encodeURIComponent(batchId)}/rollback`,
    { reason },
    { headers: authHeaders() },
  );
}
