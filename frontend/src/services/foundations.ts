// src/services/foundations.ts
import { apiGet, apiPost, apiPut } from "./crs";
import { authHeaders } from "./auth";
import type {
  AvailabilityCreate,
  AvailabilityRead,
  BaseStationCreate,
  BaseStationRead,
  BaseStationUpdate,
  FoundationContracts,
  PersonnelIdentityHealth,
  UserBaseAssignmentCreate,
  UserBaseAssignmentRead,
} from "../types/foundations";

function toQuery(params: Record<string, string | number | boolean | null | undefined>): string {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined || value === "") return;
    qs.set(key, String(value));
  });
  const value = qs.toString();
  return value ? `?${value}` : "";
}

export function getFoundationContracts(): Promise<FoundationContracts> {
  return apiGet<FoundationContracts>("/foundations/contracts", { headers: authHeaders() });
}

export function getPersonnelIdentityHealth(): Promise<PersonnelIdentityHealth> {
  return apiGet<PersonnelIdentityHealth>("/foundations/personnel/identity-health", { headers: authHeaders() });
}

export function listBaseStations(params?: { include_inactive?: boolean }): Promise<BaseStationRead[]> {
  return apiGet<BaseStationRead[]>(`/foundations/base-stations${toQuery({ include_inactive: params?.include_inactive })}`, {
    headers: authHeaders(),
  });
}

export function createBaseStation(payload: BaseStationCreate): Promise<BaseStationRead> {
  return apiPost<BaseStationRead>("/foundations/base-stations", payload, { headers: authHeaders() });
}

export function updateBaseStation(baseStationId: string, payload: BaseStationUpdate): Promise<BaseStationRead> {
  return apiPut<BaseStationRead>(`/foundations/base-stations/${encodeURIComponent(baseStationId)}`, payload, { headers: authHeaders() });
}

export function createUserBaseAssignment(payload: UserBaseAssignmentCreate): Promise<UserBaseAssignmentRead> {
  return apiPost<UserBaseAssignmentRead>("/foundations/user-base-assignments", payload, { headers: authHeaders() });
}

export function listAvailability(params?: { user_id?: string; active_at?: string }): Promise<AvailabilityRead[]> {
  return apiGet<AvailabilityRead[]>(`/foundations/availability${toQuery(params ?? {})}`, { headers: authHeaders() });
}

export function createAvailability(payload: AvailabilityCreate): Promise<AvailabilityRead> {
  return apiPost<AvailabilityRead>("/foundations/availability", payload, { headers: authHeaders() });
}
