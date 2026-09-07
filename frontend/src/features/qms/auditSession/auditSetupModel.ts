export type AuditSetupReadinessInput = {
  title: string;
  scope: string;
  criteria: string;
  plannedStart: string;
  plannedEnd: string;
  plannedStartTime: string;
  plannedEndTime: string;
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

export type AuditSetupFieldId =
  | "title"
  | "scope"
  | "criteria"
  | "auditee"
  | "plannedStart"
  | "plannedEnd"
  | "plannedStartTime"
  | "plannedEndTime"
  | "leadAuditorUserId";

export type AuditSetupIssue = {
  field: AuditSetupFieldId;
  tile: "definition" | "team";
  message: string;
};

function setupIssues(input: AuditSetupReadinessInput): AuditSetupIssue[] {
  const issues: AuditSetupIssue[] = [];
  const datesReady = Boolean(input.plannedStart && input.plannedEnd);
  const timesReady = Boolean(input.plannedStartTime && input.plannedEndTime);

  if (input.title.trim().length < 3) issues.push({ field: "title", tile: "definition", message: "Enter an audit title." });
  if (!input.scope.trim()) issues.push({ field: "scope", tile: "definition", message: "Define the audit scope." });
  if (!input.criteria.trim()) issues.push({ field: "criteria", tile: "definition", message: "Identify the applicable audit criteria and standards." });
  if (!datesReady) {
    issues.push({
      field: input.plannedStart ? "plannedEnd" : "plannedStart",
      tile: "definition",
      message: "Set the planned start and end dates.",
    });
  } else if (input.plannedEnd < input.plannedStart) {
    issues.push({ field: "plannedEnd", tile: "definition", message: "Planned end cannot be before planned start." });
  }
  if (!timesReady) {
    issues.push({
      field: input.plannedStartTime ? "plannedEndTime" : "plannedStartTime",
      tile: "definition",
      message: "Set the planned start and end times.",
    });
  } else if (
    input.plannedStartTime < "09:00" || input.plannedStartTime > "17:00" ||
    input.plannedEndTime < "09:00" || input.plannedEndTime > "17:00"
  ) {
    issues.push({ field: "plannedStartTime", tile: "definition", message: "Audit times must be between 09:00 and 17:00 tenant local time." });
  } else if (datesReady && input.plannedEndTime <= input.plannedStartTime) {
    issues.push({ field: "plannedEndTime", tile: "definition", message: "End time must be after start time on each audit day; overnight audits are not permitted." });
  }
  if (!input.auditee.trim() && !input.auditeeEmail.trim()) {
    issues.push({ field: "auditee", tile: "definition", message: "Identify the auditee representative or provide their email." });
  }
  if (!input.leadAuditorUserId) {
    issues.push({ field: "leadAuditorUserId", tile: "team", message: "Assign an eligible lead auditor." });
  }
  return issues;
}

export function auditSetupIssues(input: AuditSetupReadinessInput): AuditSetupIssue[] {
  return setupIssues(input);
}

/** Mirrors the authoritative setup gate returned by the audit-session API. */
export function auditSetupReadiness(input: AuditSetupReadinessInput): AuditSetupReadiness {
  const titleReady = input.title.trim().length >= 3;
  const scopeReady = Boolean(input.scope.trim());
  const criteriaReady = Boolean(input.criteria.trim());
  const datesReady = Boolean(input.plannedStart && input.plannedEnd);
  const datesOrdered = !datesReady || input.plannedEnd >= input.plannedStart;
  const timesReady = Boolean(input.plannedStartTime && input.plannedEndTime);
  const timesInBusinessHours = !timesReady || (
    input.plannedStartTime >= "09:00" && input.plannedStartTime <= "17:00" &&
    input.plannedEndTime >= "09:00" && input.plannedEndTime <= "17:00"
  );
  const timesOrdered = !datesReady || !timesReady || input.plannedEndTime > input.plannedStartTime;
  const auditeeReady = Boolean(input.auditee.trim() || input.auditeeEmail.trim());
  const leadAssigned = Boolean(input.leadAuditorUserId);
  const definitionReady =
    titleReady && scopeReady && criteriaReady && datesReady && datesOrdered && timesReady && timesInBusinessHours && timesOrdered && auditeeReady;
  const issues = setupIssues(input).map((issue) => issue.message);

  return {
    definitionReady,
    leadAssigned,
    ready: definitionReady && leadAssigned,
    issues,
  };
}
