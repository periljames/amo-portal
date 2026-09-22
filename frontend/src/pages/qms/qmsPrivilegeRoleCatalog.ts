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
    label: "Lead Auditor",
    summary: "Authoritative lead for governed internal audits. Required before committing a lead auditor on an audit occurrence.",
    auditAssignmentRoles: ["Lead auditor"],
    typicalScope: "GLOBAL or programme/line scope (e.g. LINE_MAINTENANCE)",
  },
  {
    type: "AUDITOR",
    label: "Auditor",
    summary: "Quality audit authorization. Observer / Trainee is a supervised development authorization under the same governed audit-authorization family.",
    auditAssignmentRoles: ["Observer / Trainee Auditor", "Assistant Auditor"],
    typicalScope: "Global, unless a governed scope is configured",
  },
  {
    type: "QUALITY_INSPECTOR",
    label: "Quality Assurance Inspector",
    summary: "Quality-assurance inspection authorization only. It does not represent maintenance certifying, Airworthiness Release, Duplicate Inspection or maintenance Quality Control authority.",
    auditAssignmentRoles: ["Not used for audit team assignment"],
    typicalScope: "As defined by the applicable Quality assurance procedure",
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
