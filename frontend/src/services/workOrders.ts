// src/services/workOrders.ts
// Work order + task API helpers.

import { apiGet, apiPost, apiPut } from "./crs";

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
export type TaskCategory = "SCHEDULED" | "UNSCHEDULED" | "DEFECT" | string;

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

export interface WorkOrderCreatePayload {
  wo_number: string;
  aircraft_serial_number: string;
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
}

export interface WorkOrderUpdatePayload {
  description?: string | null;
  check_type?: string | null;
  status?: WorkOrderStatus;
  due_date?: string | null;
  closed_date?: string | null;
  closure_reason?: string | null;
  closure_notes?: string | null;
}

export interface TaskCardRead {
  id: number;
  work_order_id?: number;
  aircraft_serial_number?: string;
  title?: string;
  description?: string | null;
  status?: TaskStatus;
  category?: TaskCategory;
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

export interface TaskCreatePayload {
  title: string;
  description?: string | null;
  category?: TaskCategory;
  origin_type?: TaskOriginType;
  priority?: TaskPriority;
  ata_chapter?: string | null;
  task_code?: string | null;
  zone?: string | null;
  access_panel?: string | null;
  planned_start?: string | null;
  planned_end?: string | null;
  estimated_manhours?: number | null;
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
  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined || value === "") return;
    qs.set(key, String(value));
  });
  const encoded = qs.toString();
  return encoded ? `?${encoded}` : "";
}

export async function listWorkOrders(params?: {
  aircraft_serial_number?: string;
  status?: WorkOrderStatus;
  wo_type?: WorkOrderType;
  skip?: number;
  limit?: number;
}): Promise<WorkOrderRead[]> {
  return apiGet<WorkOrderRead[]>(`/work-orders/${toQuery(params ?? {})}`);
}

export async function createWorkOrder(payload: WorkOrderCreatePayload): Promise<WorkOrderRead> {
  // Creation stays server-controlled unless the API supplies a durable idempotency key.
  return apiPost<WorkOrderRead>("/work-orders/", payload);
}

export async function getWorkOrder(id: number): Promise<WorkOrderRead> {
  return apiGet<WorkOrderRead>(`/work-orders/${id}`);
}

export async function getWorkOrderByNumber(woNumber: string): Promise<WorkOrderRead> {
  return apiGet<WorkOrderRead>(`/work-orders/by-number/${encodeURIComponent(woNumber)}`);
}

export async function listTasksForWorkOrder(workOrderId: number): Promise<TaskCardRead[]> {
  return apiGet<TaskCardRead[]>(`/work-orders/${workOrderId}/tasks`);
}

export async function createTask(workOrderId: number, payload: TaskCreatePayload): Promise<TaskCardRead> {
  // Creation stays live-only to avoid duplicate maintenance instructions.
  return apiPost<TaskCardRead>(`/work-orders/${workOrderId}/tasks`, payload);
}

export async function getTask(taskId: number): Promise<TaskCardRead> {
  return apiGet<TaskCardRead>(`/work-orders/tasks/${taskId}`);
}

export async function updateTask(taskId: number, payload: TaskUpdatePayload): Promise<TaskCardRead> {
  return apiPut<TaskCardRead>(`/work-orders/tasks/${taskId}`, payload, {
    offline: {
      queueMutation: true,
      entityType: "work-order-task",
      entityId: String(taskId),
    },
  });
}

export async function updateWorkOrder(id: number, payload: WorkOrderUpdatePayload): Promise<WorkOrderRead> {
  return apiPut<WorkOrderRead>(`/work-orders/${id}`, payload, {
    offline: {
      queueMutation: true,
      entityType: "work-order",
      entityId: String(id),
    },
  });
}

export async function inspectTask(
  taskId: number,
  payload: { notes?: string | null; signed_flag: boolean; signature_hash?: string | null },
): Promise<unknown> {
  // Inspection/signature actions must be confirmed by the live server.
  return apiPost<unknown>(`/work-orders/tasks/${taskId}/inspect`, payload);
}

export async function inspectWorkOrder(
  workOrderId: number,
  payload: { notes?: string | null; signed_flag: boolean; signature_hash?: string | null },
): Promise<unknown> {
  return apiPost<unknown>(`/work-orders/${workOrderId}/inspect`, payload);
}
