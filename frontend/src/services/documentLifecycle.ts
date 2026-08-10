import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";
import { trackProductWorkflow } from "./productAnalytics";

export const DOCUMENT_TYPES = [
  "MANUAL",
  "POLICY",
  "PROCEDURE",
  "WORK_INSTRUCTION",
  "FORM",
  "CHECKLIST",
  "REGISTER",
  "EXTERNAL_DOCUMENT",
] as const;

export type DocumentType = typeof DOCUMENT_TYPES[number];

export type DocumentTypeResponse = {
  manual_id: string;
  document_type: DocumentType;
  source: "OVERRIDE" | "HIERARCHY" | "DETECTED" | "DEFAULT";
  publication_family?: string | null;
  allowed_types?: DocumentType[];
  manual_type?: string;
  document_class?: string;
};

export type DeleteDocumentResponse = {
  status: "deleted";
  manual_id: string;
  code: string;
  deleted_revisions: number;
  storage_cleanup: {
    deleted: number;
    skipped: number;
    failed: number;
  };
};

function workspacePath(tenant: string, suffix: string): string {
  return `/doc-control/workspace/t/${encodeURIComponent(tenant)}${suffix}`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(authHeaders());
  if (init.body !== undefined) headers.set("Content-Type", "application/json");
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers,
    credentials: "same-origin",
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      const detail = payload?.detail;
      message = typeof detail === "string" ? detail : String(detail?.message || JSON.stringify(detail || message));
    } catch {
      // Keep status fallback.
    }
    const error = new Error(message) as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  return response.json() as Promise<T>;
}

export function getDocumentType(tenant: string, manualId: string): Promise<DocumentTypeResponse> {
  return request(workspacePath(tenant, `/documents/${encodeURIComponent(manualId)}/document-type`));
}

export function updateDocumentType(
  tenant: string,
  manualId: string,
  documentType: DocumentType,
): Promise<DocumentTypeResponse> {
  return trackProductWorkflow({
    module: "document-control",
    workflow: "document-type-update",
    source: "document-control",
    operation: () => request(workspacePath(tenant, `/documents/${encodeURIComponent(manualId)}/document-type`), {
      method: "PATCH",
      body: JSON.stringify({ document_type: documentType }),
    }),
  });
}

export function deleteDocument(tenant: string, manualId: string): Promise<DeleteDocumentResponse> {
  return trackProductWorkflow({
    module: "document-control",
    workflow: "draft-document-delete",
    source: "document-control",
    operation: () => request(workspacePath(tenant, `/documents/${encodeURIComponent(manualId)}`), {
      method: "DELETE",
    }),
  });
}
