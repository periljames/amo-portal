import { getToken, handleAuthFailure } from "./auth";
import { getApiBaseUrl } from "./config";

export type TaskStatus = "OPEN" | "IN_PROGRESS" | "DONE" | "CANCELLED";

export interface TaskItem {
  id: string;
  amo_id: string;
  title: string;
  description?: string | null;
  status: TaskStatus;
  owner_user_id?: string | null;
  supervisor_user_id?: string | null;
  due_at?: string | null;
  escalated_at?: string | null;
  closed_at?: string | null;
  entity_type?: string | null;
  entity_id?: string | null;
  priority: number;
  metadata_json?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

const API_BASE = getApiBaseUrl();

export async function listMyTasks(): Promise<TaskItem[]> {
  const token = getToken();
  const resp = await fetch(`${API_BASE}/tasks/my`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!resp.ok) {
    if (resp.status === 401) {
      handleAuthFailure();
    }
    if (resp.status === 403) {
      throw new Error("Access denied.");
    }
    throw new Error("Failed to load tasks.");
  }
  return (await resp.json()) as TaskItem[];
}

export async function updateTask(taskId: string, payload: { status?: TaskStatus }): Promise<TaskItem> {
  const token = getToken();
  const resp = await fetch(`${API_BASE}/tasks/${taskId}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : undefined),
    },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    if (resp.status === 401) {
      handleAuthFailure();
    }
    if (resp.status === 403) {
      throw new Error("Access denied.");
    }
    throw new Error("Failed to update task.");
  }
  return (await resp.json()) as TaskItem;
}
