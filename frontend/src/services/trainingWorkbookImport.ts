import { apiDelete, apiGet, apiPost } from "./crs";
import { authHeaders, handleAuthFailure } from "./auth";
import { getApiBaseUrl } from "./config";
import type {
  PersonnelLicenceRead,
  TrainingCourseRoleRuleRead,
  TrainingPersonRoleRead,
  TrainingRoleGroupRead,
  TrainingWorkbookImportDecision,
  TrainingWorkbookImportJob,
  TrainingWorkbookImportJobPage,
  TrainingWorkbookImportRowPage,
} from "../types/trainingWorkbookImport";

export interface WorkbookUploadProgress {
  loadedBytes: number;
  totalBytes?: number;
  percent?: number;
}

export function createTrainingWorkbookImport(
  file: File,
  options?: { idempotencyKey?: string; onUploadProgress?: (progress: WorkbookUploadProgress) => void },
): Promise<TrainingWorkbookImportJob> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const params = new URLSearchParams();
    if (options?.idempotencyKey) params.set("idempotency_key", options.idempotencyKey);
    const query = params.toString();
    xhr.open("POST", `${getApiBaseUrl()}/training/workbook-imports${query ? `?${query}` : ""}`);
    const headers = new Headers(authHeaders());
    headers.forEach((value, key) => xhr.setRequestHeader(key, value));
    xhr.upload.addEventListener("progress", (event) => {
      const totalBytes = event.lengthComputable ? event.total : undefined;
      options?.onUploadProgress?.({
        loadedBytes: event.loaded,
        totalBytes,
        percent: totalBytes ? Math.min(100, (event.loaded / totalBytes) * 100) : undefined,
      });
    });
    xhr.addEventListener("load", () => {
      if (xhr.status === 401) {
        handleAuthFailure("expired");
        reject(new Error("Session expired. Sign in and retry the import."));
        return;
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        let message = xhr.responseText || `Workbook upload failed (${xhr.status}).`;
        try {
          const body = JSON.parse(xhr.responseText) as { detail?: string };
          message = body.detail || message;
        } catch {
          // Keep response text.
        }
        reject(new Error(message));
        return;
      }
      try {
        resolve(JSON.parse(xhr.responseText) as TrainingWorkbookImportJob);
      } catch {
        reject(new Error("The workbook upload returned an invalid response."));
      }
    });
    xhr.addEventListener("error", () => reject(new Error("Network error while uploading the training workbook.")));
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}

export function getTrainingWorkbookImport(jobId: string): Promise<TrainingWorkbookImportJob> {
  return apiGet<TrainingWorkbookImportJob>(`/training/workbook-imports/${encodeURIComponent(jobId)}`, { headers: authHeaders() });
}

export function listTrainingWorkbookImportRows(
  jobId: string,
  options: { sheet?: string; status?: string; reviewOnly?: boolean; q?: string; limit?: number; offset?: number } = {},
): Promise<TrainingWorkbookImportRowPage> {
  const params = new URLSearchParams();
  if (options.sheet) params.set("sheet", options.sheet);
  if (options.status) params.set("status", options.status);
  if (options.reviewOnly) params.set("review_only", "true");
  if (options.q) params.set("q", options.q);
  if (typeof options.limit === "number") params.set("limit", String(options.limit));
  if (typeof options.offset === "number") params.set("offset", String(options.offset));
  const query = params.toString();
  return apiGet<TrainingWorkbookImportRowPage>(
    `/training/workbook-imports/${encodeURIComponent(jobId)}/rows${query ? `?${query}` : ""}`,
    { headers: authHeaders() },
  );
}

export function commitTrainingWorkbookImport(
  jobId: string,
  decisions: TrainingWorkbookImportDecision[],
  forceReimport = false,
): Promise<TrainingWorkbookImportJob> {
  return apiPost<TrainingWorkbookImportJob>(
    `/training/workbook-imports/${encodeURIComponent(jobId)}/commit`,
    { decisions, force_reimport: forceReimport },
    { headers: authHeaders() },
  );
}

export function cancelTrainingWorkbookImport(jobId: string): Promise<TrainingWorkbookImportJob> {
  return apiPost<TrainingWorkbookImportJob>(
    `/training/workbook-imports/${encodeURIComponent(jobId)}/cancel`,
    {},
    { headers: authHeaders() },
  );
}

export function listTrainingPersonnelLicences(userId: string): Promise<PersonnelLicenceRead[]> {
  return apiGet<PersonnelLicenceRead[]>(
    `/training/workbook-imports/users/${encodeURIComponent(userId)}/licences`,
    { headers: authHeaders() },
  );
}

export function listTrainingWorkbookImports(limit = 25, offset = 0): Promise<TrainingWorkbookImportJobPage> {
  return apiGet<TrainingWorkbookImportJobPage>(`/training/workbook-imports?limit=${limit}&offset=${offset}`, { headers: authHeaders() });
}

export async function downloadTrainingWorkbookTemplate(): Promise<void> {
  const response = await fetch(`${getApiBaseUrl()}/training/workbook-imports/template`, { headers: authHeaders() });
  if (response.status === 401) handleAuthFailure("expired");
  if (!response.ok) throw new Error(`Workbook template download failed (${response.status}).`);
  const href = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = "amo-training-import-template-2026.08.xlsx";
  anchor.click();
  URL.revokeObjectURL(href);
}

const CATALOG = "/training/workbook-imports/catalog";

export const listTrainingRoleGroups = () => apiGet<TrainingRoleGroupRead[]>(`${CATALOG}/role-groups`);
export const saveTrainingRoleGroup = (payload: { code: string; description?: string | null; is_active?: boolean }) =>
  apiPost<TrainingRoleGroupRead>(`${CATALOG}/role-groups`, payload);
export const deactivateTrainingRoleGroup = (id: string) =>
  apiDelete<TrainingRoleGroupRead>(`${CATALOG}/role-groups/${encodeURIComponent(id)}`);

export const listTrainingPersonRoles = () => apiGet<TrainingPersonRoleRead[]>(`${CATALOG}/person-roles`);
export const saveTrainingPersonRole = (payload: { user_id: string; role_group_id: string; department?: string | null; position?: string | null; notes?: string | null; is_active?: boolean }) =>
  apiPost<TrainingPersonRoleRead>(`${CATALOG}/person-roles`, payload);
export const deactivateTrainingPersonRole = (id: string) =>
  apiDelete<TrainingPersonRoleRead>(`${CATALOG}/person-roles/${encodeURIComponent(id)}`);

export const listTrainingRoleRules = () => apiGet<TrainingCourseRoleRuleRead[]>(`${CATALOG}/role-rules`);
export const saveTrainingRoleRule = (payload: { course_id: string; role_group_id: string; is_required?: boolean; requirement_type?: string; notes?: string | null; is_active?: boolean }) =>
  apiPost<TrainingCourseRoleRuleRead>(`${CATALOG}/role-rules`, payload);
export const deactivateTrainingRoleRule = (id: string) =>
  apiDelete<TrainingCourseRoleRuleRead>(`${CATALOG}/role-rules/${encodeURIComponent(id)}`);
