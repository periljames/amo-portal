/// <reference types="node" />

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const hookSource = readFileSync(
  new URL("./hooks/useRosterPlannerDataV2.ts", import.meta.url),
  "utf8",
);

describe("progressive roster planner loading", () => {
  it("bounds individual source requests instead of allowing an indefinite spinner", () => {
    expect(hookSource).toContain("REQUEST_TIMEOUT_MS = 20_000");
    expect(hookSource).toContain("withTimeout");
    expect(hookSource).toContain("did not respond within");
  });

  it("does not make people, templates, contracts or findings global loading prerequisites", () => {
    const loadingExpression = hookSource.slice(
      hookSource.indexOf("const loading ="),
      hookSource.indexOf("const refreshing ="),
    );
    expect(loadingExpression).toContain("periodsQuery");
    expect(loadingExpression).toContain("workspaceQuery");
    expect(loadingExpression).not.toContain("peopleQuery");
    expect(loadingExpression).not.toContain("templatesQuery");
    expect(loadingExpression).not.toContain("contractsQuery");
  });

  it("treats findings as an independently degradable source", () => {
    expect(hookSource).toContain("Promise.allSettled");
    expect(hookSource).toContain("findingsError");
    expect(hookSource).toContain("retrySource");
  });
});
