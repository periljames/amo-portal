// src/services/foundations.ts
import { apiDelete, apiGet, apiPost, apiPut } from "./crs";
import { authHeaders, getCachedUser } from "./auth";
import { readAdminPageTenantScope } from "./adminPageTenantScope";
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

export type BaseStationRequestScope = {
  amo_id?: string | null;
};

const AMO_CONTEXT_HEADER = "X-AMO-Context-Id";
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

function normalisedScopeAmoId(scope?: BaseStationRequestScope): string {
  return String(scope?.amo_id || "").trim();
}

function pageScopeError(message: string, code: string): Error {
  const error = new Error(message) as Error & { status?: number; code?: string };
  error.name = "BaseStationPageScopeError";
  error.status = 409;
  error.code = code;
  return error;
}

/**
 * Resolve the AMO selected by this browser tab after the setup page's successful
 * /accounts/admin/context request. The server-side support context and other tabs
 * are deliberately not consulted when constructing a base request.
 */
export function captureBaseStationRequestScope(
  scope?: BaseStationRequestScope,
): BaseStationRequestScope {
  const explicitAmoId = normalisedScopeAmoId(scope);
  if (explicitAmoId) return { amo_id: explicitAmoId };

  const user = getCachedUser();
  if (!user?.is_superuser) return {};

  const selectedAmoId = String(readAdminPageTenantScope(user.id) || "").trim();
  if (!selectedAmoId) {
    throw pageScopeError(
      "Select an AMO on the setup page before accessing its operating bases.",
      "BASE_STATION_PAGE_SCOPE_UNAVAILABLE",
    );
  }
  return { amo_id: selectedAmoId };
}

/** Fail if a retained dialog scope no longer matches this tab's page selector. */
export function validateBaseStationRequestScope(
  scope: BaseStationRequestScope,
): BaseStationRequestScope {
  const expectedAmoId = normalisedScopeAmoId(scope);
  const user = getCachedUser();
  if (!user?.is_superuser) {
    return expectedAmoId ? { amo_id: expectedAmoId } : {};
  }

  const selectedAmoId = String(readAdminPageTenantScope(user.id) || "").trim();
  if (!expectedAmoId || !selectedAmoId || selectedAmoId !== expectedAmoId) {
    throw pageScopeError(
      "The setup page changed to another AMO after this base action began. Close the editor, confirm the intended AMO, and retry.",
      "BASE_STATION_PAGE_SCOPE_CHANGED",
    );
  }
  return { amo_id: expectedAmoId };
}

function resolvedRequestScope(scope?: BaseStationRequestScope): BaseStationRequestScope {
  return validateBaseStationRequestScope(captureBaseStationRequestScope(scope));
}

function scopedAuthHeaders(scope?: BaseStationRequestScope): Headers {
  const headers = new Headers(authHeaders());
  const amoId = normalisedScopeAmoId(scope);
  if (amoId) headers.set(AMO_CONTEXT_HEADER, amoId);
  return headers;
}

function errorStatus(error: unknown): number | null {
  if (!error || typeof error !== "object") return null;
  const status = (error as { status?: unknown }).status;
  return typeof status === "number" ? status : null;
}

function baseWriteKey(
  action: "create" | "update",
  id: string | null,
  payload: BaseStationCreate | BaseStationUpdate,
  scope?: BaseStationRequestScope,
): string {
  return `${normalisedScopeAmoId(scope) || "account-amo"}:${action}:${id || "new"}:${JSON.stringify(payload)}`;
}

function identityScopeUnavailableError(cause: unknown): Error {
  const suffix = cause instanceof Error && cause.message.trim() ? ` ${cause.message}` : "";
  const error = new Error(
    `The live operating-base register could not be verified. No base change was sent.${suffix}`,
  ) as Error & { status?: number; code?: string; cause?: unknown };
  error.name = "BaseStationIdentityScopeUnavailableError";
  error.status = 503;
  error.code = "BASE_STATION_IDENTITY_SCOPE_UNAVAILABLE";
  error.cause = cause;
  return error;
}

function tenantMismatchError(message: string): Error {
  const error = new Error(message) as Error & { status?: number; code?: string };
  error.name = "BaseStationTenantMismatchError";
  error.status = 409;
  error.code = "BASE_STATION_TENANT_MISMATCH";
  return error;
}

function assertRegisterTenant(
  items: BaseStationRead[],
  scope?: BaseStationRequestScope,
): BaseStationRead[] {
  const expectedAmoId = normalisedScopeAmoId(scope);
  if (expectedAmoId && items.some((item) => item.amo_id !== expectedAmoId)) {
    throw tenantMismatchError(
      "The server returned an operating-base register from a different AMO. The response was rejected and the setup page must be refreshed.",
    );
  }
  return items;
}

function assertResponseTenant(item: BaseStationRead, scope?: BaseStationRequestScope): BaseStationRead {
  const expectedAmoId = normalisedScopeAmoId(scope);
  if (expectedAmoId && item.amo_id !== expectedAmoId) {
    throw tenantMismatchError(
      "The server returned a base from a different AMO. The response was rejected and the setup page must be refreshed.",
    );
  }
  return item;
}

async function requiredBaseIdentityScope(scope: BaseStationRequestScope): Promise<BaseStationRead[]> {
  try {
    return await listBaseStations({
      include_inactive: true,
      amo_id: scope.amo_id,
    });
  } catch (cause) {
    throw identityScopeUnavailableError(cause);
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
  scope: BaseStationRequestScope,
): Promise<never> {
  if (errorStatus(error) !== 409) throw error;
  const refreshed = await requiredBaseIdentityScope(scope);
  const conflict = findBaseStationIdentityConflict(refreshed, candidate);
  if (conflict) throw baseStationIdentityConflictError(conflict);
  throw error;
}

async function explainUpdateServerConflict(
  error: unknown,
  baseStationId: string,
  payload: BaseStationUpdate,
  scope: BaseStationRequestScope,
): Promise<never> {
  if (errorStatus(error) !== 409) throw error;
  const refreshed = await requiredBaseIdentityScope(scope);
  const candidate = changedUpdateCandidate(refreshed, baseStationId, payload);
  if (candidate) {
    const conflict = findBaseStationIdentityConflict(refreshed, candidate, baseStationId);
    if (conflict) throw baseStationIdentityConflictError(conflict);
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

export async function listBaseStations(params?: {
  include_inactive?: boolean;
  amo_id?: string | null;
}): Promise<BaseStationRead[]> {
  const requestScope = resolvedRequestScope({ amo_id: params?.amo_id });
  const items = await apiGet<BaseStationRead[]>(
    `/foundations/base-stations${toQuery({ include_inactive: params?.include_inactive })}`,
    {
      headers: scopedAuthHeaders(requestScope),
      offline: {
        cache: false,
        allowStaleFallback: false,
      },
    },
  );
  return assertRegisterTenant(items, requestScope);
}

export function createBaseStation(
  payload: BaseStationCreate,
  scope?: BaseStationRequestScope,
): Promise<BaseStationRead> {
  const requestScope = resolvedRequestScope(scope);
  const candidate: BaseStationIdentityCandidate = { code: payload.code, aliases: payload.aliases || [] };
  const key = baseWriteKey("create", null, payload, requestScope);
  return singleFlightBaseWrite(key, async () => {
    const bases = await requiredBaseIdentityScope(requestScope);
    assertIdentityAvailable(bases, candidate);
    try {
      const created = await apiPost<BaseStationRead>("/foundations/base-stations", payload, {
        headers: scopedAuthHeaders(requestScope),
      });
      return assertResponseTenant(created, requestScope);
    } catch (error) {
      return await explainCreateServerConflict(error, candidate, requestScope);
    }
  });
}

export function updateBaseStation(
  baseStationId: string,
  payload: BaseStationUpdate,
  scope?: BaseStationRequestScope,
): Promise<BaseStationRead> {
  const requestScope = resolvedRequestScope(scope);
  const key = baseWriteKey("update", baseStationId, payload, requestScope);
  return singleFlightBaseWrite(key, async () => {
    const bases = await requiredBaseIdentityScope(requestScope);
    const current = bases.find((base) => base.id === baseStationId);
    if (!current) throw new Error("The selected base no longer exists in the requested AMO register.");
    const candidate = changedBaseStationIdentityCandidate(current, payload);
    if (candidate) assertIdentityAvailable(bases, candidate, baseStationId);
    try {
      const updated = await apiPut<BaseStationRead>(
        `/foundations/base-stations/${encodeURIComponent(baseStationId)}`,
        payload,
        { headers: scopedAuthHeaders(requestScope) },
      );
      return assertResponseTenant(updated, requestScope);
    } catch (error) {
      return await explainUpdateServerConflict(error, baseStationId, payload, requestScope);
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
