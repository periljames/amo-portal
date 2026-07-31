// src/services/foundations.ts
import { apiDelete, apiGet, apiPost, apiPut } from "./crs";
import { authHeaders } from "./auth";
import type {
  AirportCatalogSearchRead,
  AvailabilityCreate,
  AvailabilityRead,
  BaseLocationConsensusRead,
  BaseLocationObservationCreate,
  BaseStationCreate,
  BaseStationRead,
  BaseStationUpdate,
  FoundationContracts,
  LocationEvaluationRead,
  LocationEvaluationRequest,
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

export function searchAirportCatalog(params: {
  q: string;
  latitude?: number | null;
  longitude?: number | null;
  limit?: number;
}): Promise<AirportCatalogSearchRead> {
  return apiGet<AirportCatalogSearchRead>(`/foundations/airport-catalog/search${toQuery(params)}`, {
    headers: authHeaders(),
  });
}

export function contributeBaseLocation(
  baseStationId: string,
  payload: BaseLocationObservationCreate,
): Promise<BaseLocationConsensusRead> {
  return apiPost<BaseLocationConsensusRead>(
    `/foundations/base-stations/${encodeURIComponent(baseStationId)}/location-observations`,
    payload,
    { headers: authHeaders() },
  );
}

export function getBaseLocationConsensus(baseStationId: string): Promise<BaseLocationConsensusRead> {
  return apiGet<BaseLocationConsensusRead>(
    `/foundations/base-stations/${encodeURIComponent(baseStationId)}/location-consensus`,
    { headers: authHeaders() },
  );
}

export function approveBaseLocationConsensus(
  baseStationId: string,
  expectedSampleCount: number,
): Promise<BaseStationRead> {
  return apiPost<BaseStationRead>(
    `/foundations/base-stations/${encodeURIComponent(baseStationId)}/location-consensus/approve`,
    { expected_sample_count: expectedSampleCount },
    { headers: authHeaders() },
  );
}

export function clearBaseLocationObservations(baseStationId: string): Promise<void> {
  return apiDelete<void>(
    `/foundations/base-stations/${encodeURIComponent(baseStationId)}/location-observations`,
    { headers: authHeaders() },
  );
}

export function evaluateBaseLocation(payload: LocationEvaluationRequest): Promise<LocationEvaluationRead> {
  return apiPost<LocationEvaluationRead>("/foundations/location/evaluate", payload, { headers: authHeaders() });
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
