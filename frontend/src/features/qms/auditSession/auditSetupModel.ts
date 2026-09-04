export type AuditSetupReadinessInput = {
  title: string;
  scope: string;
  criteria: string;
  plannedStart: string;
  plannedEnd: string;
  auditee: string;
  auditeeEmail: string;
  leadAuditorUserId?: string | null;
};

export type AuditSetupReadiness = {
  definitionReady: boolean;
  leadAssigned: boolean;
  ready: boolean;
  issues: string[];
};

/** Mirrors the authoritative setup gate returned by the audit-session API. */
export function auditSetupReadiness(input: AuditSetupReadinessInput): AuditSetupReadiness {
  const titleReady = input.title.trim().length >= 3;
  const scopeReady = Boolean(input.scope.trim());
  const criteriaReady = Boolean(input.criteria.trim());
  const datesReady = Boolean(input.plannedStart && input.plannedEnd);
  const datesOrdered = !datesReady || input.plannedEnd >= input.plannedStart;
  const auditeeReady = Boolean(input.auditee.trim() || input.auditeeEmail.trim());
  const leadAssigned = Boolean(input.leadAuditorUserId);
  const definitionReady =
    titleReady && scopeReady && criteriaReady && datesReady && datesOrdered && auditeeReady;
  const issues: string[] = [];

  if (!titleReady) issues.push("Enter an audit title.");
  if (!scopeReady) issues.push("Define the audit scope.");
  if (!criteriaReady) issues.push("Identify the applicable audit criteria and standards.");
  if (!datesReady) issues.push("Set the planned start and end dates.");
  if (datesReady && !datesOrdered) issues.push("Planned end cannot be before planned start.");
  if (!auditeeReady) issues.push("Identify the auditee or provide the auditee email.");
  if (!leadAssigned) issues.push("Assign an eligible lead auditor.");

  return {
    definitionReady,
    leadAssigned,
    ready: definitionReady && leadAssigned,
    issues,
  };
}

