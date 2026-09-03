import type { QmsPrivilege, QmsPrivilegeDecision } from "../../services/qmsPeople";

const DECISIONS_BY_STATUS: Record<QmsPrivilege["status"], QmsPrivilegeDecision["decision_type"][]> = {
  DRAFT: ["GRANT", "REJECT"],
  ACTIVE: ["RENEW", "SUSPEND", "REVOKE", "EXPIRE"],
  SUSPENDED: ["REINSTATE", "REVOKE", "EXPIRE"],
  REVOKED: [],
  EXPIRED: ["RENEW"],
};

const DECISION_LABELS: Record<QmsPrivilegeDecision["decision_type"], string> = {
  GRANT: "Grant — activate authorization",
  RENEW: "Renew — extend active authorization",
  SUSPEND: "Suspend — block use without revoking history",
  REINSTATE: "Reinstate — restore suspended authorization",
  REVOKE: "Revoke — permanently end authorization",
  EXPIRE: "Expire — mark authorization lapsed",
  REJECT: "Reject — discard draft without granting",
};

export function allowedPrivilegeDecisions(status: QmsPrivilege["status"]): QmsPrivilegeDecision["decision_type"][] {
  return DECISIONS_BY_STATUS[status] || [];
}

export function privilegeDecisionLabel(decision: QmsPrivilegeDecision["decision_type"]): string {
  return DECISION_LABELS[decision];
}

export function defaultPrivilegeDecision(status: QmsPrivilege["status"]): QmsPrivilegeDecision["decision_type"] {
  return allowedPrivilegeDecisions(status)[0] || "GRANT";
}
