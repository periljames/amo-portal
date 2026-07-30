import { describe, expect, it } from "vitest";

import { resolvePostLoginReturnTarget } from "./loginRedirect";

describe("resolvePostLoginReturnTarget", () => {
  it("allows verified platform users to return to the requested platform page", () => {
    expect(resolvePostLoginReturnTarget("/platform/security?tab=alerts", true)).toBe(
      "/platform/security?tab=alerts",
    );
  });

  it("blocks tenant users from returning to any platform route", () => {
    expect(resolvePostLoginReturnTarget("/platform/control", false)).toBeNull();
    expect(resolvePostLoginReturnTarget("/platform/integrations?tab=email", false)).toBeNull();
  });

  it("keeps valid tenant return routes available to tenant users", () => {
    expect(resolvePostLoginReturnTarget("/maintenance/safarilink/quality/inbox", false)).toBe(
      "/maintenance/safarilink/quality/inbox",
    );
  });

  it("rejects login loops and non-relative targets", () => {
    expect(resolvePostLoginReturnTarget("/login", true)).toBeNull();
    expect(resolvePostLoginReturnTarget("/maintenance/safarilink/login", false)).toBeNull();
    expect(resolvePostLoginReturnTarget("https://example.com/platform/control", true)).toBeNull();
    expect(resolvePostLoginReturnTarget("//example.com/platform/control", true)).toBeNull();
  });

  it("rejects missing or malformed route state", () => {
    expect(resolvePostLoginReturnTarget(undefined, false)).toBeNull();
    expect(resolvePostLoginReturnTarget({ from: "/platform/control" }, true)).toBeNull();
    expect(resolvePostLoginReturnTarget("   ", false)).toBeNull();
  });
});
