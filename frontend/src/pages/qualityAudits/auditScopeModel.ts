import type { PortalUser } from "../../services/auth";
import type { QMSAuditScopeOut } from "../../services/qms";

export type AuditScopePartyLevel = "FIRST_PARTY" | "SECOND_PARTY" | "THIRD_PARTY" | "REGULATORY";
export type AuditScopeDefaultKind = "INTERNAL" | "EXTERNAL" | "THIRD_PARTY";

export type AuditScopeFormState = {
  id: string | null;
  code: string;
  name: string;
  description: string;
  partyLevel: AuditScopePartyLevel;
  defaultKind: AuditScopeDefaultKind;
  active: boolean;
  sortOrder: string;
};

export function emptyAuditScopeForm(): AuditScopeFormState {
  return {
    id: null,
    code: "",
    name: "",
    description: "",
    partyLevel: "FIRST_PARTY",
    defaultKind: "INTERNAL",
    active: true,
    sortOrder: "100",
  };
}

export function auditScopeFormFromRecord(scope: QMSAuditScopeOut): AuditScopeFormState {
  return {
    id: scope.id,
    code: scope.code,
    name: scope.name,
    description: scope.description || "",
    partyLevel: scope.party_level as AuditScopePartyLevel,
    defaultKind: scope.default_kind as AuditScopeDefaultKind,
    active: scope.is_active,
    sortOrder: String(scope.sort_order),
  };
}

export function auditScopeValidationError(form: AuditScopeFormState): string | null {
  const code = form.code.trim();
  if (!/^[A-Z0-9]{2,16}$/.test(code)) return "Scope code must contain 2–16 uppercase letters or numbers.";
  if (!form.name.trim()) return "Scope name is required.";
  const sortOrder = Number(form.sortOrder);
  if (!Number.isInteger(sortOrder) || sortOrder < 0 || sortOrder > 9999) {
    return "Sort order must be a whole number from 0 to 9999.";
  }
  return null;
}

/** Mirrors backend `_require_scope_admin`: Quality Manager or standing AMO Administrator. */
export function canManageAuditScopes(user: PortalUser | null | undefined): boolean {
  if (!user || user.is_superuser || !user.amo_id) return false;
  return user.role === "QUALITY_MANAGER" || user.role === "AMO_ADMIN" || Boolean(user.is_amo_admin);
}
