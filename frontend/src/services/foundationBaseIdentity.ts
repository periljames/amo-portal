import type {
  BaseStationCreate,
  BaseStationRead,
  BaseStationUpdate,
} from "../types/foundations";

export type BaseStationIdentityCandidate = {
  code?: string | null;
  aliases?: readonly string[] | null;
};

export type BaseStationIdentityConflict = {
  field: "code" | "aliases";
  requestedValue: string;
  existingKind: "code" | "alias";
  existingValue: string;
  existingBase: Pick<BaseStationRead, "id" | "code" | "name" | "is_active">;
};

function identityKey(value: string | null | undefined): string {
  return String(value || "").trim().toLocaleUpperCase("en-US");
}

function uniqueValues(values: readonly string[] | null | undefined): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const raw of values || []) {
    const value = String(raw || "").trim();
    const key = identityKey(value);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    result.push(value);
  }
  return result;
}

/**
 * Return only identities introduced by an update.
 *
 * Codes and aliases have separate database constraints, so historic tenants can
 * legally contain a code on one base that matches an alias on another. Those
 * overlaps must remain editable. We therefore grandfather unchanged identity
 * values and preflight only a changed code or aliases newly added by the user.
 */
export function changedBaseStationIdentityCandidate(
  current: BaseStationRead,
  payload: BaseStationUpdate,
): BaseStationIdentityCandidate | null {
  const candidate: BaseStationIdentityCandidate = {};

  if (payload.code !== undefined && identityKey(payload.code) !== identityKey(current.code)) {
    candidate.code = payload.code;
  }

  if (payload.aliases !== undefined) {
    const currentAliases = new Set(
      (current.aliases || []).map((alias) => identityKey(alias.alias)).filter(Boolean),
    );
    const introducedAliases = uniqueValues(payload.aliases)
      .filter((alias) => !currentAliases.has(identityKey(alias)));
    if (introducedAliases.length) candidate.aliases = introducedAliases;
  }

  return candidate.code !== undefined || (candidate.aliases?.length || 0) > 0
    ? candidate
    : null;
}

export function findBaseStationIdentityConflict(
  existingBases: readonly BaseStationRead[],
  candidate: BaseStationIdentityCandidate,
  excludeBaseStationId?: string | null,
): BaseStationIdentityConflict | null {
  const requestedCode = String(candidate.code || "").trim();
  const requestedAliases = uniqueValues(candidate.aliases);
  const requested = [
    ...(requestedCode ? [{ field: "code" as const, value: requestedCode }] : []),
    ...requestedAliases.map((value) => ({ field: "aliases" as const, value })),
  ];

  for (const base of existingBases) {
    if (excludeBaseStationId && base.id === excludeBaseStationId) continue;
    const existing = [
      { kind: "code" as const, value: base.code },
      ...(base.aliases || []).map((alias) => ({ kind: "alias" as const, value: alias.alias })),
    ];

    for (const requestedIdentity of requested) {
      const requestedKey = identityKey(requestedIdentity.value);
      const match = existing.find((identity) => identityKey(identity.value) === requestedKey);
      if (!match) continue;
      return {
        field: requestedIdentity.field,
        requestedValue: requestedIdentity.value,
        existingKind: match.kind,
        existingValue: match.value,
        existingBase: {
          id: base.id,
          code: base.code,
          name: base.name,
          is_active: base.is_active,
        },
      };
    }
  }

  return null;
}

export function baseStationIdentityConflictMessage(conflict: BaseStationIdentityConflict): string {
  const requestedLabel = conflict.field === "code" ? "Base code" : "Alias";
  const existingLabel = conflict.existingKind === "code" ? "base code" : "alias";
  const inactiveGuidance = conflict.existingBase.is_active
    ? "Edit the existing base or choose a different identifier."
    : "The existing base is inactive; reactivate or edit it instead of creating a duplicate.";

  return `${requestedLabel} "${conflict.requestedValue}" matches ${existingLabel} "${conflict.existingValue}" on ${conflict.existingBase.code} · ${conflict.existingBase.name}. ${inactiveGuidance}`;
}

export function baseStationIdentityConflictError(conflict: BaseStationIdentityConflict): Error {
  const error = new Error(baseStationIdentityConflictMessage(conflict)) as Error & {
    status?: number;
    code?: string;
    conflict?: BaseStationIdentityConflict;
  };
  error.name = "BaseStationIdentityConflictError";
  error.status = 409;
  error.code = "BASE_STATION_IDENTITY_CONFLICT";
  error.conflict = conflict;
  return error;
}
