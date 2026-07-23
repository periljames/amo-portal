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

function fetchRosterPeoplePage(filters: RosterPeoplePageFilters): Promise<RosterPeoplePage> {
  return apiJson(`/workforce/roster-people${queryString(filters)}`, {
    offline: { cacheTtlMs: 10 * 60_000 },
  });
}

export async function listRosterPeoplePage(filters: RosterPeoplePageFilters = {}): Promise<RosterPeoplePage> {
  const first = await fetchRosterPeoplePage(filters);

  // Setup deliberately requests the backend's large page with non-eligible
  // personnel included so administrators can create missing contracts. Load
  // every remaining tenant page for that workspace; planner searches retain
  // normal page-by-page behaviour at their smaller page size.
  const aggregateSetupPeople =
    (filters.page ?? 1) === 1
    && (filters.page_size ?? 100) >= 200
    && filters.roster_eligible_only === false
    && !filters.search
    && !filters.department_id
    && !filters.base_station_id
    && first.has_more;

  if (!aggregateSetupPeople) return first;

  const remainingPages = await Promise.all(
    Array.from({ length: Math.max(first.pages - 1, 0) }, (_, index) =>
      fetchRosterPeoplePage({
        ...filters,
        page: index + 2,
        page_size: first.page_size,
      }),
    ),
  );
  const items = [first, ...remainingPages].flatMap((page) => page.items);

  return {
    ...first,
    items,
    total: items.length,
    page: 1,
    page_size: items.length || first.page_size,
    pages: items.length ? 1 : 0,
    has_more: false,
  };
}
