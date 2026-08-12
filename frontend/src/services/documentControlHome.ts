import { authHeaders } from "./auth";
import { getApiBaseUrl } from "./config";
import { listDocumentRetentionWork } from "./documentControlRetention";

export type DocumentControlMyWorkKind =
  | "CHANGE_REQUEST"
  | "PERIODIC_REVIEW"
  | "ACKNOWLEDGEMENT"
  | "WORKFLOW_DECISION"
  | "AUTHORITY_ACTION"
  | "TEMPORARY_REVISION"
  | "CONTROLLED_COPY"
  | "EXTERNAL_SOURCE_ACTION"
  | "RETENTION_APPROVAL"
  | "RETENTION_EXECUTION";

export type DocumentControlMyWorkItem = {
  id: string;
  kind: DocumentControlMyWorkKind;
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

async function fetchWorkFeed(tenant: string, suffix: string): Promise<DocumentControlMyWorkResponse> {
  const response = await fetch(
    `${getApiBaseUrl()}/doc-control/workspace/t/${encodeURIComponent(tenant)}/${suffix}`,
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

function dueTime(item: DocumentControlMyWorkItem): number {
  if (!item.due_at) return Number.POSITIVE_INFINITY;
  const parsed = new Date(item.due_at).getTime();
  return Number.isNaN(parsed) ? Number.POSITIVE_INFINITY : parsed;
}

const PRIORITY_ORDER: Record<string, number> = {
  OVERDUE: 0,
  ACTION: 1,
  CRITICAL: 1,
  HIGH: 2,
  DUE: 3,
  NORMAL: 4,
  LOW: 5,
};

export async function getDocumentControlMyWork(tenant: string): Promise<DocumentControlMyWorkResponse> {
  const [core, external, retention] = await Promise.all([
    fetchWorkFeed(tenant, "my-work"),
    fetchWorkFeed(tenant, "external-source-work"),
    listDocumentRetentionWork(tenant),
  ]);
  const retentionItems: DocumentControlMyWorkItem[] = retention.map((item) => {
    const parts = item.title.split(" · ");
    const code = parts.length > 1 ? parts[parts.length - 1] : "Document";
    return {
      id: `retention:${item.id}:${item.kind}`,
      kind: item.kind,
      manual_id: item.manual_id,
      entity_id: item.id,
      title: item.title,
      status: item.status,
      priority: item.priority,
      due_at: item.due_at,
      action_label: item.kind === "RETENTION_APPROVAL" ? "Review disposition" : "Record disposition",
      target_path: item.target_path,
      document: {
        id: item.manual_id,
        code,
        title: item.detail,
      },
    };
  });
  const items = [...core.items, ...external.items, ...retentionItems]
    .sort((left, right) => {
      const priority = (PRIORITY_ORDER[left.priority] ?? 9) - (PRIORITY_ORDER[right.priority] ?? 9);
      if (priority !== 0) return priority;
      const due = dueTime(left) - dueTime(right);
      if (Number.isFinite(due) && due !== 0) return due;
      return left.id.localeCompare(right.id);
    })
    .slice(0, 30);
  return { items, limit: 30 };
}
