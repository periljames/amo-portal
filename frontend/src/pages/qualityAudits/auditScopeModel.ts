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

export const DEFAULT_AUDIT_REFERENCE_FAMILY = "QAR";

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

export function normalizeAuditReferenceFamily(value: string | null | undefined): string {
  return String(value || "")
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, "")
    .slice(0, 16);
}

export function auditReferenceFamilyValidationError(value: string): string | null {
  const family = normalizeAuditReferenceFamily(value);
  if (!/^[A-Z0-9]{2,16}$/.test(family)) {
    return "Reference family must be 2–16 letters or numbers.";
  }
  return null;
}

export function formatAuditReferenceExample(
  family: string,
  scopeCode: string,
  year = new Date().getFullYear(),
  sequence = 1,
): string {
  const safeFamily = normalizeAuditReferenceFamily(family) || DEFAULT_AUDIT_REFERENCE_FAMILY;
  const safeScope = String(scopeCode || "SCOPE")
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, "") || "SCOPE";
  const yy = String(year).slice(-2);
  const seq = String(Math.max(1, sequence)).padStart(3, "0");
  return `${safeFamily}/${safeScope}/${yy}/${seq}`;
}

export function auditScopeUsageLabel(scope: Pick<QMSAuditScopeOut, "issued_this_year" | "next_sequence">): string {
  const issued = Number(scope.issued_this_year ?? 0);
  const next = Number(scope.next_sequence ?? 1);
  return `${issued} issued · next ${String(Math.max(1, next)).padStart(3, "0")}`;
}
