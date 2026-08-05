import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";

const API = `${getApiBaseUrl()}/aircraft/induction`;

export type Catalogue = {
  families: any[];
  types: any[];
  variants: any[];
  templates: any[];
  revisions: any[];
};

export type TenantProgram = {
  id: string;
  amo_id: string;
  variant_id: string;
  code: string;
  title: string;
  authority?: string | null;
  approval_reference?: string | null;
  status: string;
};

export type InductionJob = {
  id: string;
  amo_id: string;
  induction_ref: string;
  serial_number: string;
  registration: string;
  variant_id: string;
  template_revision_id: string;
  program_revision_id: string;
  status: string;
  source_system?: string | null;
  source_reference?: string | null;
  current_step: string;
  counts_json: Record<string, any>;
  validation_json: Record<string, any>;
  activation_manifest_json: Record<string, any>;
  created_at: string;
  updated_at: string;
};

export type InductionDataset = {
  id: string;
  induction_id: string;
  dataset: string;
  source_name: string;
  source_sheet?: string | null;
  fingerprint: string;
  mapping_profile_id?: string | null;
  headers_json: string[];
  row_count: number;
  status: string;
  created_at: string;
};

export type InductionRow = {
  id: string;
  dataset_id: string;
  row_number: number;
  source_json: Record<string, any>;
  normalized_json: Record<string, any>;
  final_json: Record<string, any>;
  status: string;
  errors_json: string[];
  warnings_json: string[];
  decision?: string | null;
};

export type InductionWorkspace = {
  induction: InductionJob;
  datasets: InductionDataset[];
  rows_by_dataset: Record<string, InductionRow[]>;
  applicability_snapshot?: {
    id: string;
    snapshot_hash: string;
    configuration_hash: string;
    applicable_requirements_json: any[];
    excluded_requirements_json: any[];
    context_json: Record<string, any>;
  } | null;
  binding?: Record<string, any> | null;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: {
      ...authHeaders(),
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(init?.headers || {}),
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    const message = typeof detail === "string"
      ? detail
      : detail?.message || detail?.code || `Request failed (${response.status})`;
    const error = new Error(message) as Error & { detail?: any; status?: number };
    error.detail = detail;
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const inductionApi = {
  catalogue: () => request<Catalogue>("/catalogue"),
  programs: () => request<TenantProgram[]>("/programs"),
  jobs: () => request<InductionJob[]>("/jobs"),
  workspace: (id: string) => request<InductionWorkspace>(`/jobs/${id}`),
  createJob: (payload: Record<string, any>) => request<InductionJob>("/jobs", { method: "POST", body: JSON.stringify(payload) }),
  upload: async (id: string, files: File[], sourceSystem: string, dataset?: string) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    form.append("source_system", sourceSystem || "GENERIC");
    if (dataset) form.append("dataset", dataset);
    return request<InductionDataset[]>(`/jobs/${id}/upload`, { method: "POST", body: form });
  },
  validate: (id: string) => request<InductionJob>(`/jobs/${id}/validate`, { method: "POST" }),
  resolveEffectivity: (id: string) => request<any>(`/jobs/${id}/resolve-effectivity`, { method: "POST" }),
  approve: (id: string) => request<InductionJob>(`/jobs/${id}/approve`, { method: "POST" }),
  activate: (id: string, approvalNote: string, counters: any[]) => request<any>(`/jobs/${id}/activate`, {
    method: "POST",
    body: JSON.stringify({ approval_note: approvalNote, counters }),
  }),
  decideRow: (jobId: string, rowId: string, decision: string, finalJson: Record<string, any>) => request<InductionRow>(`/jobs/${jobId}/rows/${rowId}/decision`, {
    method: "POST",
    body: JSON.stringify({ decision, final_json: finalJson }),
  }),
  createFamily: (payload: Record<string, any>) => request<any>("/catalogue/families", { method: "POST", body: JSON.stringify(payload) }),
  createType: (payload: Record<string, any>) => request<any>("/catalogue/types", { method: "POST", body: JSON.stringify(payload) }),
  createVariant: (payload: Record<string, any>) => request<any>("/catalogue/variants", { method: "POST", body: JSON.stringify(payload) }),
  createTemplate: (payload: Record<string, any>) => request<any>("/catalogue/templates", { method: "POST", body: JSON.stringify(payload) }),
  createTemplateRevision: (templateId: string, payload: Record<string, any>) => request<any>(`/catalogue/templates/${templateId}/revisions`, { method: "POST", body: JSON.stringify(payload) }),
  createProgram: (payload: Record<string, any>) => request<any>("/programs", { method: "POST", body: JSON.stringify(payload) }),
  createProgramRevision: (programId: string, payload: Record<string, any>) => request<any>(`/programs/${programId}/revisions`, { method: "POST", body: JSON.stringify(payload) }),
};
