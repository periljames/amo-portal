import { authHeaders } from "./auth";
import { apiDelete, apiGet, apiPost, apiPut } from "./crs";

export interface SetupDepartmentRead {
  id: string;
  amo_id: string;
  code: string;
  name: string;
  default_route?: string | null;
  sort_order: number;
  is_active: boolean;
  assigned_user_count: number;
}

export interface SetupDepartmentCreate {
  code: string;
  name: string;
  default_route?: string | null;
  sort_order?: number;
  is_active?: boolean;
}

export type SetupDepartmentUpdate = Partial<SetupDepartmentCreate>;

export function listSetupDepartments(includeInactive = true): Promise<SetupDepartmentRead[]> {
  return apiGet<SetupDepartmentRead[]>(
    `/foundations/departments?include_inactive=${includeInactive ? "true" : "false"}`,
    { headers: authHeaders() },
  );
}

export function createSetupDepartment(payload: SetupDepartmentCreate): Promise<SetupDepartmentRead> {
  return apiPost<SetupDepartmentRead>("/foundations/departments", payload, { headers: authHeaders() });
}

export function updateSetupDepartment(
  departmentId: string,
  payload: SetupDepartmentUpdate,
): Promise<SetupDepartmentRead> {
  return apiPut<SetupDepartmentRead>(
    `/foundations/departments/${encodeURIComponent(departmentId)}`,
    payload,
    { headers: authHeaders() },
  );
}

export function deleteSetupDepartment(departmentId: string): Promise<void> {
  return apiDelete<void>(
    `/foundations/departments/${encodeURIComponent(departmentId)}`,
    undefined,
    { headers: authHeaders() },
  );
}
