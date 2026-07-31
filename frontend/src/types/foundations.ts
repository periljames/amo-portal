// src/types/foundations.ts
export type BaseStationType = "MAIN_BASE" | "LINE_STATION" | "OUTSTATION" | "WORKSHOP" | "HANGAR" | "TRAINING_SITE" | "OTHER";
export type BaseAssignmentKind = "HOME_BASE" | "TEMPORARY" | "TRAINING" | "RELIEF" | "OTHER";
export type AvailabilityStatus = "ON_DUTY" | "AWAY" | "ON_LEAVE";
export type BaseLocationSource = "MANUAL" | "DEVICE_SINGLE" | "DEVICE_CONSENSUS" | "AERODROME_DATASET";

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
  latitude?: number | null;
  longitude?: number | null;
  coordinate_accuracy_m?: number | null;
  location_source?: BaseLocationSource | null;
  airport_reference_ident?: string | null;
  location_verified_at?: string | null;
  location_verified_by_user_id?: string | null;
  geofence_radius_m: number;
  checkin_prompt_enabled: boolean;
  checkout_reminder_enabled: boolean;
  suspicious_location_review_enabled: boolean;
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
  latitude?: number | null;
  longitude?: number | null;
  coordinate_accuracy_m?: number | null;
  location_source?: BaseLocationSource | null;
  airport_reference_ident?: string | null;
  geofence_radius_m?: number;
  checkin_prompt_enabled?: boolean;
  checkout_reminder_enabled?: boolean;
  suspicious_location_review_enabled?: boolean;
  is_active?: boolean;
  aliases?: string[];
}

export type BaseStationUpdate = Partial<BaseStationCreate>;

export interface BaseLocationObservationCreate {
  latitude: number;
  longitude: number;
  accuracy_m: number;
  captured_at: string;
}

export interface BaseLocationConsensusRead {
  base_station_id: string;
  sample_count: number;
  distinct_contributor_count: number;
  candidate_latitude?: number | null;
  candidate_longitude?: number | null;
  median_accuracy_m?: number | null;
  max_spread_m?: number | null;
  ready_for_approval: boolean;
  reason: string;
  expires_at?: string | null;
}

export interface LocationEvaluationRequest {
  latitude: number;
  longitude: number;
  accuracy_m: number;
  base_station_id?: string | null;
}

export interface LocationEvaluationRead {
  base_station_id?: string | null;
  base_code?: string | null;
  base_name?: string | null;
  distance_m?: number | null;
  geofence_radius_m?: number | null;
  inside_geofence: boolean;
  location_confidence: "HIGH" | "MEDIUM" | "LOW" | "UNAVAILABLE";
  checkin_prompt_enabled: boolean;
  checkout_reminder_enabled: boolean;
  review_signal: boolean;
  review_reason?: string | null;
  note: string;
}

export interface AirportCatalogItem {
  ident: string;
  name: string;
  airport_type?: string | null;
  municipality?: string | null;
  iso_country?: string | null;
  iso_region?: string | null;
  icao_code?: string | null;
  iata_code?: string | null;
  local_code?: string | null;
  latitude: number;
  longitude: number;
  distance_km?: number | null;
  source: "OURAIRPORTS";
}

export interface AirportCatalogSearchRead {
  items: AirportCatalogItem[];
  provider: string;
  advisory: string;
  cached_at?: string | null;
}

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
