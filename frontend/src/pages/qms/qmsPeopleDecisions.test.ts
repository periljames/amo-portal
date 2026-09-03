import { describe, expect, it } from "vitest";

import { allowedPrivilegeDecisions, defaultPrivilegeDecision } from "./qmsPeopleDecisions";

describe("qmsPeopleDecisions", () => {
  it("limits draft privileges to grant or reject", () => {
    expect(allowedPrivilegeDecisions("DRAFT")).toEqual(["GRANT", "REJECT"]);
    expect(defaultPrivilegeDecision("DRAFT")).toBe("GRANT");
  });

  it("allows suspend and revoke on active privileges", () => {
    expect(allowedPrivilegeDecisions("ACTIVE")).toEqual(["RENEW", "SUSPEND", "REVOKE", "EXPIRE"]);
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
});
