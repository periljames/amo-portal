import { beforeEach, describe, expect, it, vi } from "vitest";

let currentUser: { id: string } | null = null;

vi.mock("../../../services/auth", () => ({
  getCachedUser: () => currentUser,
}));

vi.mock("../../../app/routeGuards", () => ({
  hasQmsRolePermission: (permission: string) => ["qms.audit.execute", "qms.audit.manage"].includes(permission),
}));

import { canCompleteAuditFieldwork, canExecuteAssignedAudit } from "./qmsAuditActionGates";

const audit = {
  lead_auditor_user_id: "lead-1",
  observer_auditor_user_id: "observer-1",
  assistant_auditor_user_id: "assistant-1",
  supporting_auditor_user_ids: ["support-1"],
};

describe("QMS audit assignment action gates", () => {
  beforeEach(() => {
    currentUser = null;
  });

  it("lets lead, assistant and governed supporting auditors execute fieldwork", () => {
    currentUser = { id: "lead-1" };
    expect(canExecuteAssignedAudit(audit)).toBe(true);

    currentUser = { id: "assistant-1" };
    expect(canExecuteAssignedAudit(audit)).toBe(true);

    currentUser = { id: "support-1" };
    expect(canExecuteAssignedAudit(audit)).toBe(true);
  });

  it("keeps the observer and unrelated users read-only", () => {
    currentUser = { id: "observer-1" };
    expect(canExecuteAssignedAudit(audit)).toBe(false);

    currentUser = { id: "other-1" };
    expect(canExecuteAssignedAudit(audit)).toBe(false);
  });

  it("does not convert a legacy duplicated observer into a supporting auditor", () => {
    currentUser = { id: "observer-1" };
    expect(canExecuteAssignedAudit({
      ...audit,
      supporting_auditor_user_ids: ["support-1", "observer-1"],
    })).toBe(false);
  });

  it("reserves fieldwork completion to the assigned lead", () => {
    currentUser = { id: "lead-1" };
    expect(canCompleteAuditFieldwork(audit)).toBe(true);

    currentUser = { id: "assistant-1" };
    expect(canCompleteAuditFieldwork(audit)).toBe(false);

    currentUser = { id: "support-1" };
    expect(canCompleteAuditFieldwork(audit)).toBe(false);

    currentUser = { id: "observer-1" };
    expect(canCompleteAuditFieldwork(audit)).toBe(false);
  });
});