// src/services/workOrders.ts
// Work order + task API helpers.

import { getApiBaseUrl } from "./config";
import { getToken, handleAuthFailure } from "./auth";

type QueryVal = string | number | boolean | null | undefined;

export type WorkOrderStatus =
  | "DRAFT"
  | "RELEASED"
  | "IN_PROGRESS"
  | "COMPLETED"
  | "CANCELLED"
  | string;

export type WorkOrderType =
  | "PERIODIC"
  | "NON_ROUTINE"
  | "DEFECT"
  | string;

export type TaskStatus =
  | "PLANNED"
  | "IN_PROGRESS"
  | "COMPLETE"
  | "INSPECTED"
  | "CANCELLED"
  | string;

export type TaskOriginType = "SCHEDULED" | "NON_ROUTINE" | string;

export type TaskPriority = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | string;

export interface WorkOrderRead {
  id: number;
  wo_number?: string;
  aircraft_serial_number?: string;
  description?: string | null;
  check_type?: string | null;
  wo_type?: WorkOrderType;
  status?: WorkOrderStatus;
  is_scheduled?: boolean;
  due_date?: string | null;
  open_date?: string | null;
  closed_date?: string | null;
  closure_reason?: string | null;
  closure_notes?: string | null;
  originating_org?: string | null;
  work_package_ref?: string | null;
  operator_event_id?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface TaskCardRead {
  id: number;
  work_order_id?: number;
  aircraft_serial_number?: string;
  title?: string;
  description?: string | null;
  status?: TaskStatus;
  category?: string;
  origin_type?: TaskOriginType;
  priority?: TaskPriority;
  ata_chapter?: string | null;
  task_code?: string | null;
  zone?: string | null;
  access_panel?: string | null;
  planned_start?: string | null;
  planned_end?: string | null;
  actual_start?: string | null;
  actual_end?: string | null;
  estimated_manhours?: number | null;
  hf_notes?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface TaskUpdatePayload {
  title?: string | null;
  description?: string | null;
  status?: TaskStatus;
  actual_start?: string | null;
  actual_end?: string | null;
  hf_notes?: string | null;
  last_known_updated_at: string;
}

function toQuery(params: Record<string, QueryVal>): string {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === null || v === undefined || v === "") return;
    qs.set(k, String(v));
  });
  const s = qs.toString();
  return s ? `?${s}` : "";
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "GET",
    headers: {
      Accept: "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers || {}),
    },
    credentials: "include",
    ...init,
  });

  if (res.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Work Orders API ${res.status}: ${text || res.statusText}`);
  }

  return (await res.json()) as T;
}

async function sendJson<T>(
  path: string,
  method: "PUT" | "POST",
  body: unknown
): Promise<T> {
  const token = getToken();
  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    method,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body ?? {}),
    credentials: "include",
  });

  if (res.status === 401) {
    handleAuthFailure("expired");
    throw new Error("Session expired. Please sign in again.");
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Work Orders API ${res.status}: ${text || res.statusText}`);
  }

  return (await res.json()) as T;
}

export async function listWorkOrders(params?: {
  aircraft_serial_number?: string;
  status?: WorkOrderStatus;
  wo_type?: WorkOrderType;
  skip?: number;
  limit?: number;
}): Promise<WorkOrderRead[]> {
  return fetchJson<WorkOrderRead[]>(`/work-orders${toQuery(params ?? {})}`);
}

export async function getWorkOrder(id: number): Promise<WorkOrderRead> {
  return fetchJson<WorkOrderRead>(`/work-orders/${id}`);
}

export async function getWorkOrderByNumber(woNumber: string): Promise<WorkOrderRead> {
  return fetchJson<WorkOrderRead>(`/work-orders/by-number/${encodeURIComponent(woNumber)}`);
}

export async function listTasksForWorkOrder(workOrderId: number): Promise<TaskCardRead[]> {
  return fetchJson<TaskCardRead[]>(`/work-orders/${workOrderId}/tasks`);
}

export async function getTask(taskId: number): Promise<TaskCardRead> {
  return fetchJson<TaskCardRead>(`/work-orders/tasks/${taskId}`);
}

export async function updateTask(
  taskId: number,
  payload: TaskUpdatePayload
): Promise<TaskCardRead> {
  return sendJson<TaskCardRead>(`/work-orders/tasks/${taskId}`, "PUT", payload);
}
