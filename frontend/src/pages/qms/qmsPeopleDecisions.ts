import type { QmsEligibility, QmsPrivilege, QmsPrivilegeDecision } from "../../services/qmsPeople";

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
  REJECT: "Reject — discard this draft (marks revoked)",
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

const RESULTING_STATUS: Record<QmsPrivilegeDecision["decision_type"], QmsPrivilege["status"]> = {
  GRANT: "ACTIVE",
  RENEW: "ACTIVE",
  SUSPEND: "SUSPENDED",
  REINSTATE: "ACTIVE",
  REVOKE: "REVOKED",
  EXPIRE: "EXPIRED",
  // Align with backend: rejected drafts are discarded (revoked), not left hanging as draft.
  REJECT: "REVOKED",
};

export function privilegeStatusAfterDecision(
  decision: QmsPrivilegeDecision["decision_type"],
): QmsPrivilege["status"] {
  return RESULTING_STATUS[decision];
}

/** Gates that must pass to GRANT / RENEW / REINSTATE (independence is assignment-only). */
const ACTIVATION_GATES = ["workforce_active", "training_current_verified", "capacity"] as const;

/**
 * Bind an eligibility snapshot to the selected authorization for display.
 * Draft / inactive rows must not look "Blocked" merely because no ACTIVE privilege exists yet.
 */
export function bindEligibilityToPrivilege(snapshot: QmsEligibility, privilege: QmsPrivilege): QmsEligibility {
  if (privilege.status === "ACTIVE") {
    const selectedPrivilegeMatches = snapshot.active_privilege?.id === privilege.id;
    return {
      ...snapshot,
      eligible: Boolean(snapshot.eligible && selectedPrivilegeMatches),
      hard_gates: {
        ...snapshot.hard_gates,
        selected_privilege_active: selectedPrivilegeMatches,
      },
    };
  }

  const hard_gates: Record<string, boolean> = { ...snapshot.hard_gates };
  // Activation decisions ignore these (backend pops them for GRANT).
  hard_gates.active_privilege = true;
  hard_gates.independence = true;
  hard_gates.selected_privilege_active = privilege.status === "DRAFT";
  const eligible = ACTIVATION_GATES.every((gate) => hard_gates[gate] !== false);
  return {
    ...snapshot,
    eligible,
    hard_gates,
  };
}

export function privilegeDraftReason(privilege: QmsPrivilege): string {
  if (privilege.status !== "DRAFT") return "";
  if ((privilege.decisions?.length || 0) === 0) {
    return "Awaiting a Grant decision — competence can be checked before activation.";
  }
  return "Still draft — record Grant to activate, or Reject to discard.";
}

export function privilegeReadinessLabel(
  privilege: QmsPrivilege,
  options: { loading: boolean; snapshot: QmsEligibility | null; matchesSelection: boolean },
): string {
  if (options.loading || !options.matchesSelection) return "Checking authoritative gates…";
  if (!options.snapshot) return "Readiness unavailable";
  if (privilege.status === "DRAFT") {
    return options.snapshot.eligible ? "Ready to grant" : "Blocked from grant";
  }
  if (privilege.status === "REVOKED") return "Revoked";
  if (privilege.status === "EXPIRED") return "Expired";
  return options.snapshot.eligible ? "Ready" : "Blocked";
}

/** Assignment-only gates — hide on Draft grant readiness so the panel doesn't contradict itself. */
const ASSIGNMENT_ONLY_GATES = new Set(["active_privilege", "independence", "selected_privilege_active"]);

export function privilegeDisplayGates(
  privilege: QmsPrivilege,
  hardGates: Record<string, boolean>,
): Array<[string, boolean]> {
  return Object.entries(hardGates).filter(([gate]) => {
    if (privilege.status === "DRAFT" && ASSIGNMENT_ONLY_GATES.has(gate)) return false;
    return true;
  });
}
