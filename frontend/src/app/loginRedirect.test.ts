import { describe, expect, it } from "vitest";

import { resolvePostLoginReturnTarget } from "./loginRedirect";

describe("resolvePostLoginReturnTarget", () => {
  it("allows verified platform users to return to the requested platform page", () => {
    expect(resolvePostLoginReturnTarget("/platform/security?tab=alerts", true)).toBe(
      "/platform/security?tab=alerts",
    );
    expect(resolvePostLoginReturnTarget("/Platform/security?tab=alerts", true)).toBe(
      "/Platform/security?tab=alerts",
    );
  });

  it("blocks tenant users from returning to raw, case-variant, or encoded platform routes", () => {
    expect(resolvePostLoginReturnTarget("/platform/control", false)).toBeNull();
    expect(resolvePostLoginReturnTarget("/platform/integrations?tab=email", false)).toBeNull();
    expect(resolvePostLoginReturnTarget("/Platform/control", false)).toBeNull();
    expect(resolvePostLoginReturnTarget("/%70latform/control", false)).toBeNull();
    expect(resolvePostLoginReturnTarget("/PLATFORM/%63ontrol", false)).toBeNull();
  });

  it("keeps valid tenant return routes available to tenant users", () => {
    expect(resolvePostLoginReturnTarget("/maintenance/safarilink/quality/inbox", false)).toBe(
      "/maintenance/safarilink/quality/inbox",
    );
  });

  it("rejects login loops and non-relative targets", () => {
    expect(resolvePostLoginReturnTarget("/login", true)).toBeNull();
    expect(resolvePostLoginReturnTarget("/LOGIN", true)).toBeNull();
    expect(resolvePostLoginReturnTarget("/maintenance/safarilink/login", false)).toBeNull();
    expect(resolvePostLoginReturnTarget("/maintenance/safarilink/%6Cogin", false)).toBeNull();
    expect(resolvePostLoginReturnTarget("https://example.com/platform/control", true)).toBeNull();
    expect(resolvePostLoginReturnTarget("//example.com/platform/control", true)).toBeNull();
    expect(resolvePostLoginReturnTarget("/%2Fexample.com/platform/control", true)).toBeNull();
  });

  it("rejects missing, malformed, or undecodable route state", () => {
    expect(resolvePostLoginReturnTarget(undefined, false)).toBeNull();
    expect(resolvePostLoginReturnTarget({ from: "/platform/control" }, true)).toBeNull();
    expect(resolvePostLoginReturnTarget("   ", false)).toBeNull();
    expect(resolvePostLoginReturnTarget("/%E0%A4%A", false)).toBeNull();
  });
});
