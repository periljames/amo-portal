import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";

const API = `${getApiBaseUrl()}/aircraft/induction`;

export type Catalogue = { families: any[]; types: any[]; variants: any[]; templates: any[]; revisions: any[] };
export type TenantProgram = { id: string; amo_id: string; variant_id: string; code: string; title: string; authority?: string | null; approval_reference?: string | null; status: string };
export type TenantProgramRevision = { id: string; program_id: string; base_template_revision_id: string; revision_code: string; status: string; effective_date?: string | null; approval_reference?: string | null; approval_date?: string | null; notes?: string | null };
export type MappingProfile = { id: string; scope: string; name: string; version: number; source_system: string; source_version?: string | null; dataset: string; fingerprint: string; status: string };
export type InductionJob = { id: string; amo_id: string; induction_ref: string; serial_number: string; registration: string; variant_id: string; template_revision_id: string; program_revision_id: string; status: string; source_system?: string | null; source_reference?: string | null; current_step: string; counts_json: Record<string, any>; validation_json: Record<string, any>; activation_manifest_json: Record<string, any>; created_at: string; updated_at: string };
export type InductionDataset = { id: string; induction_id: string; dataset: string; source_name: string; source_sheet?: string | null; fingerprint: string; mapping_profile_id?: string | null; headers_json: string[]; row_count: number; status: string; created_at: string };
export type InductionRow = { id: string; dataset_id: string; row_number: number; source_json: Record<string, any>; normalized_json: Record<string, any>; final_json: Record<string, any>; status: string; errors_json: string[]; warnings_json: string[]; decision?: string | null };
export type InductionWorkspace = { induction: InductionJob; datasets: InductionDataset[]; rows_by_dataset: Record<string, InductionRow[]>; applicability_snapshot?: { id: string; snapshot_hash: string; configuration_hash: string; applicable_requirements_json: any[]; excluded_requirements_json: any[]; context_json: Record<string, any> } | null; binding?: Record<string, any> | null };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: { ...authHeaders(), ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...(init?.headers || {}) },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    const message = typeof detail === "string" ? detail : detail?.message || detail?.code || `Request failed (${response.status})`;
    const error = new Error(message) as Error & { detail?: any; status?: number };
    error.detail = detail;
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

const post = <T>(path: string, payload?: any) => request<T>(path, { method: "POST", body: payload === undefined ? undefined : JSON.stringify(payload) });

export const inductionApi = {
  catalogue: () => request<Catalogue>("/catalogue"),
  templateRevision: (id: string) => request<any>(`/catalogue/revisions/${id}`),
  programs: () => request<TenantProgram[]>("/programs"),
  programRevisions: (id: string) => request<TenantProgramRevision[]>(`/programs/${id}/revisions`),
  mappingProfiles: () => request<MappingProfile[]>("/mapping-profiles"),
  jobs: () => request<InductionJob[]>("/jobs"),
  workspace: (id: string) => request<InductionWorkspace>(`/jobs/${id}`),
  createJob: (payload: Record<string, any>) => post<InductionJob>("/jobs", payload),
  upload: async (id: string, files: File[], sourceSystem: string, dataset?: string) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    form.append("source_system", sourceSystem || "GENERIC");
    if (dataset) form.append("dataset", dataset);
    return request<InductionDataset[]>(`/jobs/${id}/upload`, { method: "POST", body: form });
  },
  validate: (id: string) => post<InductionJob>(`/jobs/${id}/validate`),
  resolveEffectivity: (id: string) => post<any>(`/jobs/${id}/resolve-effectivity`),
  approve: (id: string) => post<InductionJob>(`/jobs/${id}/approve`),
  activate: (id: string, approvalNote: string, counters: any[]) => post<any>(`/jobs/${id}/activate`, { approval_note: approvalNote, counters }),
  decideRow: (jobId: string, rowId: string, decision: string, finalJson: Record<string, any>) => post<InductionRow>(`/jobs/${jobId}/rows/${rowId}/decision`, { decision, final_json: finalJson }),
  createFamily: (payload: Record<string, any>) => post<any>("/catalogue/families", payload),
  createType: (payload: Record<string, any>) => post<any>("/catalogue/types", payload),
  createVariant: (payload: Record<string, any>) => post<any>("/catalogue/variants", payload),
  createTemplate: (payload: Record<string, any>) => post<any>("/catalogue/templates", payload),
  createTemplateRevision: (templateId: string, payload: Record<string, any>) => post<any>(`/catalogue/templates/${templateId}/revisions`, payload),
  addSourceDocument: (revisionId: string, payload: Record<string, any>) => post<any>(`/catalogue/revisions/${revisionId}/source-documents`, payload),
  addConfigurationNode: (revisionId: string, payload: Record<string, any>) => post<any>(`/catalogue/revisions/${revisionId}/configuration`, payload),
  addRequirement: (revisionId: string, payload: Record<string, any>) => post<any>(`/catalogue/revisions/${revisionId}/requirements`, payload),
  publishTemplateRevision: (revisionId: string, approvalNote: string) => post<any>(`/catalogue/revisions/${revisionId}/publish`, { approval_note: approvalNote }),
  createMappingProfile: (payload: Record<string, any>) => post<any>("/mapping-profiles", payload),
  createProgram: (payload: Record<string, any>) => post<any>("/programs", payload),
  createProgramRevision: (programId: string, payload: Record<string, any>) => post<any>(`/programs/${programId}/revisions`, payload),
  addProgramOverride: (revisionId: string, payload: Record<string, any>) => post<any>(`/program-revisions/${revisionId}/overrides`, payload),
  approveProgramRevision: (revisionId: string, approvalNote: string) => post<any>(`/program-revisions/${revisionId}/approve`, { approval_note: approvalNote }),
};
