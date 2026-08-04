// src/services/foundations.ts
import { apiDelete, apiGet, apiPost, apiPut } from "./crs";
import { authHeaders } from "./auth";
import {
  baseStationIdentityConflictError,
  changedBaseStationIdentityCandidate,
  findBaseStationIdentityConflict,
  type BaseStationIdentityCandidate,
} from "./foundationBaseIdentity";
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

const inFlightBaseWrites = new Map<string, Promise<BaseStationRead>>();

function toQuery(params: Record<string, string | number | boolean | null | undefined>): string {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined || value === "") return;
    qs.set(key, String(value));
  });
  const value = qs.toString();
  return value ? `?${value}` : "";
}

function errorStatus(error: unknown): number | null {
  if (!error || typeof error !== "object") return null;
  const status = (error as { status?: unknown }).status;
  return typeof status === "number" ? status : null;
}

function baseWriteKey(action: "create" | "update", id: string | null, payload: BaseStationCreate | BaseStationUpdate): string {
  return `${action}:${id || "new"}:${JSON.stringify(payload)}`;
}

async function availableBaseIdentityScope(): Promise<BaseStationRead[] | null> {
  try {
    return await listBaseStations({ include_inactive: true });
  } catch {
    // Identity preflight improves feedback but must not replace server authority.
    return null;
  }
}

function changedUpdateCandidate(
  bases: readonly BaseStationRead[],
  baseStationId: string,
  payload: BaseStationUpdate,
): BaseStationIdentityCandidate | null {
  const current = bases.find((base) => base.id === baseStationId);
  return current ? changedBaseStationIdentityCandidate(current, payload) : null;
}

function assertIdentityAvailable(
  bases: readonly BaseStationRead[],
  candidate: BaseStationIdentityCandidate,
  excludeBaseStationId?: string | null,
): void {
  const conflict = findBaseStationIdentityConflict(bases, candidate, excludeBaseStationId);
  if (conflict) throw baseStationIdentityConflictError(conflict);
}

async function explainCreateServerConflict(
  error: unknown,
  candidate: BaseStationIdentityCandidate,
): Promise<never> {
  if (errorStatus(error) !== 409) throw error;
  const refreshed = await availableBaseIdentityScope();
  if (refreshed) {
    const conflict = findBaseStationIdentityConflict(refreshed, candidate);
    if (conflict) throw baseStationIdentityConflictError(conflict);
  }
  throw error;
}

async function explainUpdateServerConflict(
  error: unknown,
  baseStationId: string,
  payload: BaseStationUpdate,
): Promise<never> {
  if (errorStatus(error) !== 409) throw error;
  const refreshed = await availableBaseIdentityScope();
  if (refreshed) {
    const candidate = changedUpdateCandidate(refreshed, baseStationId, payload);
    if (candidate) {
      const conflict = findBaseStationIdentityConflict(refreshed, candidate, baseStationId);
      if (conflict) throw baseStationIdentityConflictError(conflict);
    }
  }
  throw error;
}

function singleFlightBaseWrite(key: string, write: () => Promise<BaseStationRead>): Promise<BaseStationRead> {
  const existing = inFlightBaseWrites.get(key);
  if (existing) return existing;
  const pending = write().finally(() => {
    if (inFlightBaseWrites.get(key) === pending) inFlightBaseWrites.delete(key);
  });
  inFlightBaseWrites.set(key, pending);
  return pending;
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
  const candidate: BaseStationIdentityCandidate = { code: payload.code, aliases: payload.aliases || [] };
  const key = baseWriteKey("create", null, payload);
  return singleFlightBaseWrite(key, async () => {
    const bases = await availableBaseIdentityScope();
    if (bases) assertIdentityAvailable(bases, candidate);
    try {
      return await apiPost<BaseStationRead>("/foundations/base-stations", payload, { headers: authHeaders() });
    } catch (error) {
      return await explainCreateServerConflict(error, candidate);
    }
  });
}

export function updateBaseStation(baseStationId: string, payload: BaseStationUpdate): Promise<BaseStationRead> {
  const key = baseWriteKey("update", baseStationId, payload);
  return singleFlightBaseWrite(key, async () => {
    const bases = await availableBaseIdentityScope();
    const candidate = bases ? changedUpdateCandidate(bases, baseStationId, payload) : null;
    if (bases && candidate) assertIdentityAvailable(bases, candidate, baseStationId);
    try {
      return await apiPut<BaseStationRead>(`/foundations/base-stations/${encodeURIComponent(baseStationId)}`, payload, { headers: authHeaders() });
    } catch (error) {
      return await explainUpdateServerConflict(error, baseStationId, payload);
    }
  });
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
    undefined,
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
