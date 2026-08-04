import { authHeaders } from "./auth";
import { apiGet, apiPatch, apiPost } from "./crs";

export type WorkPackageStatus =
  | "DRAFT"
  | "REVIEW"
  | "READY"
  | "RELEASED"
  | "IN_PROGRESS"
  | "CLOSED"
  | "CANCELLED";

export type WorkPackageOrder = {
  link_id: number;
  work_order_id: number;
  wo_number: string;
  status: string;
  description?: string | null;
  due_date?: string | null;
  sequence_no: number;
  source_type: string;
  source_ref?: string | null;
  task_count: number;
  completed_task_count: number;
  estimated_manhours: number;
};

export type WorkPackage = {
  id: number;
  package_ref: string;
  aircraft_serial_number: string;
  title: string;
  description?: string | null;
  check_type?: string | null;
  status: WorkPackageStatus;
  due_date?: string | null;
  planned_start?: string | null;
  planned_end?: string | null;
  source_horizon_days: number;
  baseline_generated_at?: string | null;
  readiness_status: "NOT_CHECKED" | "BLOCKED" | "ATTENTION" | "READY" | string;
  readiness_json: {
    blockers?: string[];
    warnings?: string[];
    metrics?: Record<string, number>;
    generated_at?: string;
  };
  created_at: string;
  updated_at: string;
  orders: WorkPackageOrder[];
};

export type WorkPackageCreate = {
  package_ref?: string;
  aircraft_serial_number: string;
  title: string;
  description?: string;
  check_type?: string;
  due_date?: string;
  planned_start?: string;
  planned_end?: string;
  source_horizon_days?: number;
  program_item_ids?: number[];
};

export type WorkPackageReadiness = {
  work_package_id: number;
  readiness_status: string;
  blockers: string[];
  warnings: string[];
  metrics: Record<string, number>;
  generated_at: string;
};

export function listWorkPackages(params: { aircraftSerialNumber?: string; status?: string } = {}) {
  const query = new URLSearchParams();
  if (params.aircraftSerialNumber) query.set("aircraft_serial_number", params.aircraftSerialNumber);
  if (params.status) query.set("status_filter", params.status);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiGet<WorkPackage[]>(`/work-packages${suffix}`, { headers: authHeaders() });
}

export function getWorkPackage(id: number) {
  return apiGet<WorkPackage>(`/work-packages/${id}`, { headers: authHeaders() });
}

export function createWorkPackage(payload: WorkPackageCreate) {
  return apiPost<WorkPackage>("/work-packages", payload, { headers: authHeaders() });
}

export function updateWorkPackage(id: number, payload: Partial<WorkPackageCreate>) {
  return apiPatch<WorkPackage>(`/work-packages/${id}`, payload, { headers: authHeaders() });
}

export function attachWorkOrder(id: number, workOrderId: number) {
  return apiPost<WorkPackage>(`/work-packages/${id}/orders`, {
    work_order_id: workOrderId,
    source_type: "MANUAL",
  }, { headers: authHeaders() });
}

export function getWorkPackageReadiness(id: number) {
  return apiGet<WorkPackageReadiness>(`/work-packages/${id}/readiness`, { headers: authHeaders() });
}

export function updateWorkPackageStatus(id: number, status: WorkPackageStatus, notes?: string) {
  return apiPost<WorkPackage>(`/work-packages/${id}/status`, { status, notes }, { headers: authHeaders() });
}
