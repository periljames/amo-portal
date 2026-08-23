/// <reference types="node" />

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

const plannerSource = readSource("./components/RosterPlannerV2.tsx");
const batchPanelSource = readSource("./components/CycleStartBatchPanel.tsx");
const typedApiSource = readSource("../../services/typedApi.ts");

describe("large workforce roster generation", () => {
  it("groups first-time cycle starts instead of rendering every employee by default", () => {
    expect(plannerSource).toContain("CycleStartBatchPanel");
    expect(batchPanelSource).toContain("Auto set similar starting shifts");
    expect(batchPanelSource).toContain("Apply to all");
    expect(batchPanelSource).toContain("Review individuals");
    expect(batchPanelSource).toContain("combineDepartments");
  });

  it("groups only complete identical rotations and keeps department grouping by default", () => {
    expect(batchPanelSource).toContain("rotationSignature");
    expect(batchPanelSource).toContain("day.shift_template_id");
    expect(batchPanelSource).toContain("day.status");
    expect(batchPanelSource).toContain("day.start_time_local");
    expect(batchPanelSource).toContain("day.end_time_local");
    expect(batchPanelSource).toContain("candidate.person.department_id");
  });

  it("uses bounded adaptive generation batches rather than ten people per request", () => {
    expect(plannerSource).not.toContain("const batchSize = 10;");
    expect(plannerSource).toContain("Math.floor(900 / daysInPeriod)");
    expect(plannerSource).toContain("Math.min(50");
  });

  it("retries only structured retryable generator failures with the same idempotency key", () => {
    expect(plannerSource).toContain("attempt < 3");
    expect(plannerSource).toContain("retryable");
    expect(plannerSource).toContain("`${operationKey}-${batchNumber + 1}`");
    expect(plannerSource).toContain("without duplicating saved duties");
  });

  it("preserves top-level infrastructure error metadata for retry decisions", () => {
    expect(typedApiSource).toContain("nestedDetail && typeof nestedDetail === \"object\"");
    expect(typedApiSource).toContain("error_code");
    expect(typedApiSource).toContain("retryable: payload.retryable === true");
  });
});
