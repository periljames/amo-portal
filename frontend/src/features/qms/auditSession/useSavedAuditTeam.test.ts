import { describe, expect, it } from "vitest";

import {
  resolveSavedTeamStatus,
  type SavedTeamCheck,
} from "./useSavedAuditTeam";

function check(partial: Partial<SavedTeamCheck> & Pick<SavedTeamCheck, "hasAssignee">): SavedTeamCheck {
  return {
    eligible: null,
    pending: false,
    error: false,
    hasData: false,
    ...partial,
  };
}

describe("resolveSavedTeamStatus", () => {
  it("requires a lead auditor before anything else", () => {
    expect(
      resolveSavedTeamStatus({
        online: false,
        assigned: false,
        checks: [],
      }).message,
    ).toBe("Assign a lead auditor");
  });

  it("trusts a prior online verification while offline for the same fingerprint", () => {
    const status = resolveSavedTeamStatus({
      online: false,
      assigned: true,
      checks: [
        check({ hasAssignee: true, eligible: null, hasData: false, error: true }),
      ],
      cachedFingerprint: "audit|lead||",
      currentFingerprint: "audit|lead||",
    });
    expect(status.ready).toBe(true);
    expect(status.offlineTrusted).toBe(true);
    expect(status.message).toBe("");
  });

  it("asks to reconnect offline when no prior verification matches", () => {
    const status = resolveSavedTeamStatus({
      online: false,
      assigned: true,
      checks: [check({ hasAssignee: true, hasData: false, error: true })],
      cachedFingerprint: "audit|old||",
      currentFingerprint: "audit|lead||",
    });
    expect(status.ready).toBe(false);
    expect(status.message).toBe("Reconnect to verify team");
  });

  it("uses live eligible results when online", () => {
    const status = resolveSavedTeamStatus({
      online: true,
      assigned: true,
      checks: [
        check({ hasAssignee: true, eligible: true, hasData: true }),
        check({ hasAssignee: false }),
      ],
    });
    expect(status.ready).toBe(true);
    expect(status.offlineTrusted).toBe(false);
    expect(status.message).toBe("");
  });

  it("keeps live cache ready while offline without session cache", () => {
    const status = resolveSavedTeamStatus({
      online: false,
      assigned: true,
      checks: [check({ hasAssignee: true, eligible: true, hasData: true })],
    });
    expect(status.ready).toBe(true);
    expect(status.offlineTrusted).toBe(false);
    expect(status.message).toBe("");
  });
});
