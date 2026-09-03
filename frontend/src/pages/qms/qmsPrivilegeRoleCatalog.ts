import type { QmsPrivilegeRule } from "../../services/qmsPeople";

export type QmsPrivilegeType = QmsPrivilegeRule["privilege_type"];

export type QmsRoleCatalogEntry = {
  type: QmsPrivilegeType;
  label: string;
  summary: string;
  auditAssignmentRoles: string[];
  typicalScope: string;
};

export const QMS_PRIVILEGE_ROLE_CATALOG: QmsRoleCatalogEntry[] = [
  {
    type: "LEAD_AUDITOR",
    label: "Lead auditor",
    summary: "Authoritative lead for governed internal audits. Required before committing a lead auditor on an audit occurrence.",
    auditAssignmentRoles: ["Lead auditor"],
    typicalScope: "GLOBAL or programme/line scope (e.g. LINE_MAINTENANCE)",
  },
  {
    type: "AUDITOR",
    label: "Auditor / Observer",
    summary: "Default tenant catalog includes Auditor (full) and Observer / Trainee (supervised development) rules under this type.",
    auditAssignmentRoles: ["Observer auditor", "Assistant auditor"],
    typicalScope: "GLOBAL or the same scope code used on the assignment preflight",
  },
  {
    type: "QUALITY_INSPECTOR",
    label: "Quality inspector",
    summary: "Release/inspection privileges used outside the audit assignment guard.",
    auditAssignmentRoles: ["Not used for audit team assignment"],
    typicalScope: "Hangar, line station or product family scope",
  },
  {
    type: "AUTHORIZATION_REVIEWER",
    label: "Authorization reviewer",
    summary: "Committee or reviewer role for competence and authorization decisions.",
    auditAssignmentRoles: ["Not used for audit team assignment"],
    typicalScope: "GLOBAL or committee scope",
  },
  {
    type: "CUSTOM",
    label: "Custom privilege",
    summary: "Tenant-defined privilege contract. Document scope and training requirements explicitly.",
    auditAssignmentRoles: ["Defined by tenant rule metadata"],
    typicalScope: "As defined in the rule scope schema",
  },
];

export function catalogEntryForType(type: QmsPrivilegeType): QmsRoleCatalogEntry | undefined {
  return QMS_PRIVILEGE_ROLE_CATALOG.find((entry) => entry.type === type);
}

export function humanisePrivilegeType(type: string): string {
  return catalogEntryForType(type as QmsPrivilegeType)?.label || type.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
}
