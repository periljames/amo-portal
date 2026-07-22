import { apiJson, queryString } from "./typedApi";

export type RosterPersonRead = {
  user_id: string;
  staff_code: string;
  full_name: string;
  role: string;
  position_title?: string | null;
  department_id?: string | null;
  department_code?: string | null;
  department_name?: string | null;
  primary_base_station_id?: string | null;
  primary_base_code?: string | null;
  standard_daily_minutes?: number | null;
  standard_weekly_minutes?: number | null;
  overtime_eligible: boolean;
  night_shift_eligible: boolean;
  standby_eligible: boolean;
  active_authorisation_count: number;
  has_active_contract: boolean;
  is_active: boolean;
};

export type RosterDepartmentOption = {
  id: string;
  code: string;
  name: string;
};

export type RosterPeoplePage = {
  items: RosterPersonRead[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  has_more: boolean;
  departments: RosterDepartmentOption[];
};

export type RosterPeoplePageFilters = {
  page?: number;
  page_size?: number;
  search?: string | null;
  department_id?: string | null;
  base_station_id?: string | null;
  active_only?: boolean;
  roster_eligible_only?: boolean;
};

export function listRosterPeoplePage(filters: RosterPeoplePageFilters = {}): Promise<RosterPeoplePage> {
  return apiJson(`/workforce/roster-people${queryString(filters)}`, {
    offline: { cacheTtlMs: 10 * 60_000 },
  });
}
