import { describe, expect, it } from "vitest";
import { buildCarInviteHash, buildCarInviteUrl, parseCarInviteLocation } from "./carInviteUrl";

describe("public CAR invitation URL handling", () => {
  it("reads a bearer token from the fragment", () => {
    expect(parseCarInviteLocation("", "#token=abc123&capture=1")).toMatchObject({
      token: "abc123", tokens: ["abc123"], captureMode: true, legacyQuery: false,
    });
  });
  it("prefers the fragment bearer over any stale query token", () => {
    expect(parseCarInviteLocation("?token=legacy-token", "#token=current-token").token).toBe("current-token");
  });
  it("uses fragment capture settings ahead of stale query settings", () => {
    expect(parseCarInviteLocation("?capture=1", "#token=current-token&capture=0").captureMode).toBe(false);
  });
  it("accepts and identifies legacy query-token links for migration", () => {
    expect(parseCarInviteLocation("?token=old-token&capture=1", "")).toMatchObject({
      token: "old-token", captureMode: true, legacyQuery: true,
    });
  });
  it("retains explicitly delivered multiple CAR tokens", () => {
    expect(parseCarInviteLocation("", "#token=one,two").tokens).toEqual(["one", "two"]);
  });
  it("creates a fragment URL without a token in path or query", () => {
    expect(buildCarInviteUrl("https://portal.example/", "abc", true))
      .toBe("https://portal.example/qms/car-access#token=abc&capture=1");
    expect(buildCarInviteHash("abc")).toBe("#token=abc");
  });
});
