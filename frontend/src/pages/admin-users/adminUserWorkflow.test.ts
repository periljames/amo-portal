/// <reference types="node" />

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

function source(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

describe("admin user workflow regressions", () => {
  it("invalidates profile caches after account mutations", () => {
    const service = source("../../services/adminUsers.ts");
    expect(service).toContain("invalidateAdminUserCache(userId)");
    expect(service).toContain("payload.user_ids.forEach((userId) => invalidateAdminUserCache(userId))");
  });

  it("uses browser cryptographic randomness for temporary passwords", () => {
    const page = source("../AdminUserNewPage.tsx");
    expect(page).toContain("crypto.getRandomValues");
    expect(page).not.toContain("Math.random");
  });

  it("makes the platform ROOT scope explicit when creating a superuser", () => {
    const page = source("../AdminUserNewPage.tsx");
    expect(page).toContain('creatingPlatformSuperuser = form.role === "SUPERUSER"');
    expect(page).toContain('title="Platform ROOT identity"');
    expect(page).toContain("creatingPlatformSuperuser ? undefined : selectedDepartmentId");
  });
});
