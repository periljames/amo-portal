import { describe, expect, it } from "vitest";

import type { QmsEligibility, QmsPrivilege } from "../../services/qmsPeople";
import {
  allowedPrivilegeDecisions,
  bindEligibilityToPrivilege,
  defaultPrivilegeDecision,
  privilegeDisplayGates,
  privilegeDraftReason,
  privilegeReadinessLabel,
  privilegeStatusAfterDecision,
} from "./qmsPeopleDecisions";

function privilege(partial: Partial<QmsPrivilege> & Pick<QmsPrivilege, "id" | "status">): QmsPrivilege {
  return {
    user_id: "user-1",
    rule_id: "rule-1",
    privilege_code: "LEAD_AUDITOR",
    scope_key: "GLOBAL",
    scope: {},
    limitations: [],
    effective_from: null,
    expires_on: null,
    latest_decision_id: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    decisions: [],
    ...partial,
  };
}

function eligibility(partial: Partial<QmsEligibility> = {}): QmsEligibility {
  return {
    eligible: false,
    as_of: "2026-09-21",
    hard_gates: {
      workforce_active: true,
      training_current_verified: true,
      capacity: true,
      active_privilege: false,
      independence: false,
    },
    training: {
      required: ["QMS-INIT"],
      satisfied: ["QMS-INIT"],
      missing: [],
      expired: [],
      records: [],
      expired_records: [],
      tracked_records: [],
      passed: true,
    },
    person: { user_id: "user-1", full_name: "Stephen Mutambu", workforce_status: "ACTIVE" } as QmsEligibility["person"],
    rule: { id: "rule-1", privilege_code: "LEAD_AUDITOR", title: "Lead auditor", privilege_type: "LEAD_AUDITOR" },
    independence: {},
    workload: {},
    active_privilege: null,
    ...partial,
  };
}

describe("qmsPeopleDecisions", () => {
  it("limits draft privileges to grant or reject", () => {
    expect(allowedPrivilegeDecisions("DRAFT")).toEqual(["GRANT", "REJECT"]);
    expect(defaultPrivilegeDecision("DRAFT")).toBe("GRANT");
  });

  it("allows suspend and revoke on active privileges", () => {
    expect(allowedPrivilegeDecisions("ACTIVE")).toEqual(["RENEW", "SUSPEND", "REVOKE", "EXPIRE"]);
  });

  it("maps quick decisions to resulting privilege statuses", () => {
    expect(privilegeStatusAfterDecision("SUSPEND")).toBe("SUSPENDED");
    expect(privilegeStatusAfterDecision("REVOKE")).toBe("REVOKED");
    expect(privilegeStatusAfterDecision("REINSTATE")).toBe("ACTIVE");
    expect(privilegeStatusAfterDecision("REJECT")).toBe("REVOKED");
    expect(privilegeStatusAfterDecision("GRANT")).toBe("ACTIVE");
  });

  it("allows reinstate and revoke on suspended privileges", () => {
    expect(allowedPrivilegeDecisions("SUSPENDED")).toEqual(["REINSTATE", "REVOKE", "EXPIRE"]);
    expect(defaultPrivilegeDecision("SUSPENDED")).toBe("REINSTATE");
  });

  it("blocks further decisions after revoke", () => {
    expect(allowedPrivilegeDecisions("REVOKED")).toEqual([]);
  });

  it("offers renew only for expired privileges", () => {
    expect(allowedPrivilegeDecisions("EXPIRED")).toEqual(["RENEW"]);
  });

  it("does not mark draft authorizations blocked merely because no active privilege exists yet", () => {
    const bound = bindEligibilityToPrivilege(eligibility(), privilege({ id: "p1", status: "DRAFT" }));
    expect(bound.eligible).toBe(true);
    expect(bound.hard_gates.active_privilege).toBe(true);
    expect(bound.hard_gates.independence).toBe(true);
    expect(bound.hard_gates.selected_privilege_active).toBe(true);
  });

  it("keeps draft blocked when training gates fail", () => {
    const bound = bindEligibilityToPrivilege(
      eligibility({
        hard_gates: {
          workforce_active: true,
          training_current_verified: false,
          capacity: true,
          active_privilege: false,
          independence: false,
        },
      }),
      privilege({ id: "p1", status: "DRAFT" }),
    );
    expect(bound.eligible).toBe(false);
    expect(privilegeReadinessLabel(privilege({ id: "p1", status: "DRAFT" }), {
      loading: false,
      snapshot: bound,
      matchesSelection: true,
    })).toBe("Blocked from grant");
  });

  it("requires the selected active privilege to match the eligibility snapshot", () => {
    const bound = bindEligibilityToPrivilege(
      eligibility({
        eligible: true,
        hard_gates: {
          workforce_active: true,
          training_current_verified: true,
          capacity: true,
          active_privilege: true,
          independence: true,
        },
        active_privilege: { id: "other", privilege_code: "AUDITOR", status: "ACTIVE" } as QmsEligibility["active_privilege"],
      }),
      privilege({ id: "p1", status: "ACTIVE" }),
    );
    expect(bound.eligible).toBe(false);
    expect(bound.hard_gates.selected_privilege_active).toBe(false);
  });

  it("explains draft status for grant readiness", () => {
    expect(privilegeDraftReason(privilege({ id: "p1", status: "DRAFT", decisions: [] }))).toMatch(/Awaiting a Grant/i);
    expect(privilegeDraftReason(privilege({ id: "p1", status: "ACTIVE" }))).toBe("");
  });

  it("hides assignment-only gates from draft grant readiness", () => {
    const gates = privilegeDisplayGates(
      privilege({ id: "p1", status: "DRAFT" }),
      {
        workforce_active: true,
        training_current_verified: true,
        capacity: true,
        active_privilege: true,
        independence: true,
        selected_privilege_active: true,
      },
    );
    expect(gates.map(([gate]) => gate)).toEqual(["workforce_active", "training_current_verified", "capacity"]);
  });
});
