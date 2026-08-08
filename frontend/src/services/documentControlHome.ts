import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";

export type DocumentControlMyWorkItem = {
  id: string;
  kind: "CHANGE_REQUEST" | "PERIODIC_REVIEW" | "ACKNOWLEDGEMENT" | "WORKFLOW_DECISION";
  manual_id: string;
  entity_id: string;
  title: string;
  status: string;
  priority: string;
  due_at?: string | null;
  action_label: string;
  target_path: string;
  document: {
    id: string;
    code: string;
    title: string;
  };
};

export type DocumentControlMyWorkResponse = {
  items: DocumentControlMyWorkItem[];
  limit: number;
};

export async function getDocumentControlMyWork(tenant: string): Promise<DocumentControlMyWorkResponse> {
  const response = await fetch(
    `${getApiBaseUrl()}/doc-control/workspace/t/${encodeURIComponent(tenant)}/my-work`,
    {
      headers: authHeaders(),
      credentials: "same-origin",
    },
  );
  if (!response.ok) {
    let message = `The Document Control work queue could not be loaded (${response.status}).`;
    try {
      const payload = await response.json();
      message = typeof payload?.detail === "string"
        ? payload.detail
        : payload?.detail?.message || message;
    } catch {
      // Keep the operational fallback message.
    }
    throw new Error(message);
  }
  return response.json() as Promise<DocumentControlMyWorkResponse>;
}
