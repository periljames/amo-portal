import { apiGet } from "./crs";
import { authHeaders } from "./auth";
import type {
  AccountRole,
  AdminUserDirectoryItem,
  AdminUserDirectoryMetrics,
} from "./adminUsers";

export type AdminUserAccountFilter = "all" | "active" | "inactive";
export type AdminUserSortField = "name" | "staff_code" | "role" | "department" | "created_at" | "last_login_at";
export type AdminUserSortDirection = "asc" | "desc";

export interface AdminUserDirectoryPageParams {
  amo_id?: string | null;
  page?: number;
  page_size?: number;
  search?: string;
  role?: AccountRole | "all";
  account_status?: AdminUserAccountFilter;
  department_id?: string | "all" | "unassigned";
  sort_by?: AdminUserSortField;
  sort_direction?: AdminUserSortDirection;
}

export interface AdminUserDirectoryPageResponse {
  items: AdminUserDirectoryItem[];
  metrics: AdminUserDirectoryMetrics;
  total: number;
  page: number;
  page_size: number;
  pages: number;
  has_next: boolean;
  has_previous: boolean;
}

export async function getAdminUserDirectoryPage(
  params: AdminUserDirectoryPageParams = {},
): Promise<AdminUserDirectoryPageResponse> {
  const searchParams = new URLSearchParams();
  if (params.amo_id?.trim()) searchParams.set("amo_id", params.amo_id.trim());
  searchParams.set("page", String(Math.max(1, params.page ?? 1)));
  searchParams.set("page_size", String(Math.min(100, Math.max(10, params.page_size ?? 50))));
  if (params.search?.trim()) searchParams.set("search", params.search.trim());
  if (params.role && params.role !== "all") searchParams.set("role", params.role);
  if (params.account_status && params.account_status !== "all") {
    searchParams.set("account_status", params.account_status);
  }
  if (params.department_id && params.department_id !== "all") {
    searchParams.set("department_id", params.department_id);
  }
  if (params.sort_by) searchParams.set("sort_by", params.sort_by);
  if (params.sort_direction) searchParams.set("sort_direction", params.sort_direction);

  return apiGet<AdminUserDirectoryPageResponse>(
    `/accounts/admin/user-directory?${searchParams.toString()}`,
    { headers: authHeaders() },
  );
}
