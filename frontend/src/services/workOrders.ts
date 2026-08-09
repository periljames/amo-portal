// src/services/workOrders.ts
// Work order + task API helpers.

import { authHeaders } from "./auth";
import { apiGet, apiPost, apiPut } from "./crs";
import { emitProductEvent, trackProductWorkflow } from "./productAnalytics";

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
  return apiGet<WorkOrderRead[]>(`/work-orders/${toQuery(params ?? {})}`, {
    headers: authHeaders(),
  });
}

export async function createWorkOrder(payload: WorkOrderCreatePayload): Promise<WorkOrderRead> {
  // Creation stays server-controlled unless the API supplies a durable idempotency key.
  return trackProductWorkflow({
    module: "work-orders",
    workflow: "work-order-create",
    source: "maintenance",
    operation: () => apiPost<WorkOrderRead>("/work-orders/", payload, {
      headers: authHeaders(),
    }),
  });
}

export async function getWorkOrder(id: number): Promise<WorkOrderRead> {
  return apiGet<WorkOrderRead>(`/work-orders/${id}`, {
    headers: authHeaders(),
  });
}

export async function getWorkOrderByNumber(woNumber: string): Promise<WorkOrderRead> {
  return apiGet<WorkOrderRead>(`/work-orders/by-number/${encodeURIComponent(woNumber)}`, {
    headers: authHeaders(),
  });
}

export async function listTasksForWorkOrder(workOrderId: number): Promise<TaskCardRead[]> {
  return apiGet<TaskCardRead[]>(`/work-orders/${workOrderId}/tasks`, {
    headers: authHeaders(),
  });
}

export async function createTask(workOrderId: number, payload: TaskCreatePayload): Promise<TaskCardRead> {
  // Creation stays live-only to avoid duplicate maintenance instructions.
  return trackProductWorkflow({
    module: "work-orders",
    workflow: "task-card-create",
    source: "maintenance",
    operation: () => apiPost<TaskCardRead>(`/work-orders/${workOrderId}/tasks`, payload, {
      headers: authHeaders(),
    }),
  });
}

export async function getTask(taskId: number): Promise<TaskCardRead> {
  return apiGet<TaskCardRead>(`/work-orders/tasks/${taskId}`, {
    headers: authHeaders(),
  });
}

export async function updateTask(taskId: number, payload: TaskUpdatePayload): Promise<TaskCardRead> {
  // Task updates carry last_known_updated_at, so the backend can reject stale replay.
  return trackProductWorkflow({
    module: "work-orders",
    workflow: payload.status ? "task-status-update" : "task-card-update",
    source: "maintenance",
    operation: () => apiPut<TaskCardRead>(`/work-orders/tasks/${taskId}`, payload, {
      headers: authHeaders(),
      offline: {
        queueMutation: true,
        entityType: "work-order-task",
        entityId: String(taskId),
      },
    }),
  });
}

export async function updateWorkOrder(id: number, payload: WorkOrderUpdatePayload): Promise<WorkOrderRead> {
  // Work-order updates have no backend revision/idempotency contract yet.
  // Keep them live-only so delayed replay cannot overwrite a newer planner edit.
  return trackProductWorkflow({
    module: "work-orders",
    workflow: payload.status ? "work-order-status-update" : "work-order-update",
    source: "maintenance",
    operation: () => apiPut<WorkOrderRead>(`/work-orders/${id}`, payload, {
      headers: authHeaders(),
    }),
  });
}

export async function inspectTask(
  taskId: number,
  payload: { notes?: string | null; signed_flag: boolean; signature_hash?: string | null },
): Promise<unknown> {
  // Inspection/signature actions must be confirmed by the live server.
  const result = await trackProductWorkflow({
    module: "work-orders",
    workflow: "task-inspection",
    source: "maintenance",
    operation: () => apiPost<unknown>(`/work-orders/tasks/${taskId}/inspect`, payload, {
      headers: authHeaders(),
    }),
  });
  void emitProductEvent({
    event_type: "approval_completed",
    module: "work-orders",
    outcome: "SUCCESS",
    metadata: {
      workflow: "task-inspection",
      source: "maintenance",
    },
  });
  return result;
}

export async function inspectWorkOrder(
  workOrderId: number,
  payload: { notes?: string | null; signed_flag: boolean; signature_hash?: string | null },
): Promise<unknown> {
  const result = await trackProductWorkflow({
    module: "work-orders",
    workflow: "work-order-inspection",
    source: "maintenance",
    operation: () => apiPost<unknown>(`/work-orders/${workOrderId}/inspect`, payload, {
      headers: authHeaders(),
    }),
  });
  void emitProductEvent({
    event_type: "approval_completed",
    module: "work-orders",
    outcome: "SUCCESS",
    metadata: {
      workflow: "work-order-inspection",
      source: "maintenance",
    },
  });
  return result;
}
