// src/types/foundations.ts
export type BaseStationType = "MAIN_BASE" | "LINE_STATION" | "OUTSTATION" | "WORKSHOP" | "HANGAR" | "TRAINING_SITE" | "OTHER";
export type BaseAssignmentKind = "HOME_BASE" | "TEMPORARY" | "TRAINING" | "RELIEF" | "OTHER";
export type AvailabilityStatus = "ON_DUTY" | "AWAY" | "ON_LEAVE";

export interface BaseStationAliasRead {
  id: string;
  amo_id: string;
  base_station_id: string;
  alias: string;
  source_module?: string | null;
  created_at: string;
}

export interface BaseStationRead {
  id: string;
  amo_id: string;
  code: string;
  name: string;
  icao_code?: string | null;
  iata_code?: string | null;
  base_type: BaseStationType;
  time_zone?: string | null;
  description?: string | null;
  is_active: boolean;
  aliases: BaseStationAliasRead[];
  created_by_user_id?: string | null;
  updated_by_user_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface BaseStationCreate {
  code: string;
  name: string;
  icao_code?: string | null;
  iata_code?: string | null;
  base_type?: BaseStationType;
  time_zone?: string | null;
  description?: string | null;
  is_active?: boolean;
  aliases?: string[];
}

export type BaseStationUpdate = Partial<BaseStationCreate>;

export interface UserBaseAssignmentCreate {
  user_id: string;
  base_station_id: string;
  assignment_kind?: BaseAssignmentKind;
  effective_from?: string;
  effective_to?: string | null;
  is_primary?: boolean;
  note?: string | null;
}

export interface UserBaseAssignmentRead extends Required<Omit<UserBaseAssignmentCreate, "effective_to" | "note">> {
  id: string;
  amo_id: string;
  effective_to?: string | null;
  note?: string | null;
  created_by_user_id?: string | null;
  created_at: string;
  updated_at: string;
  base_station?: BaseStationRead | null;
}

export interface AvailabilityRead {
  id: string;
  amo_id: string;
  user_id: string;
  status: AvailabilityStatus;
  effective_from: string;
  effective_to?: string | null;
  note?: string | null;
  updated_by_user_id?: string | null;
  updated_at: string;
}

export interface AvailabilityCreate {
  user_id: string;
  status: AvailabilityStatus;
  effective_from?: string | null;
  effective_to?: string | null;
  note?: string | null;
}

export interface PersonnelIdentityIssue {
  issue_type: string;
  user_id?: string | null;
  personnel_profile_id?: string | null;
  staff_code?: string | null;
  person_id?: string | null;
  full_name?: string | null;
  email?: string | null;
  detail: string;
}

export interface PersonnelIdentityHealth {
  amo_id: string;
  canonical_key: "users.id";
  active_users: number;
  active_personnel_profiles: number;
  linked_active_profiles: number;
  active_users_without_profile: number;
  active_profiles_without_user: number;
  issues: PersonnelIdentityIssue[];
}

export interface FoundationContracts {
  canonical_personnel_key: "users.id";
  ownership: Record<string, string>;
  service_contracts: Record<string, unknown>;
  canonical_frontend_routes: Record<string, string>;
}
