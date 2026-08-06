/// <reference types="node" />

import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

const directorySource = readSource("./components/WorkforcePeopleDirectory.tsx");
const bulkSource = readSource("./components/WorkforceBulkSetupPanel.tsx");
const wrapperSource = readSource("./components/WorkforceHrWorkspaceV2.tsx");
const operationsSource = readSource("./components/WorkforceOperationsWorkspace.tsx");
const pagesSource = readSource("./WorkforceRosteringPagesV2.tsx");
const serviceSource = readSource("../../services/workforceHr.ts");
const typeSource = readSource("../../types/workforceHr.ts");
const cssSource = readSource("./components/workforce-people-directory.css");
const bulkCssSource = readSource("./components/workforce-bulk-setup.css");

describe("Scalable Workforce people directory", () => {
  it("uses server-side pagination with bounded page sizes", () => {
    expect(serviceSource).toContain("/workforce/hr/people");
    expect(serviceSource).toContain("page_size");
    expect(directorySource).toContain("const PAGE_SIZES = [25, 50, 100, 200]");
    expect(bulkSource).toContain("const PAGE_SIZES = [25, 50, 100, 250]");
    expect(directorySource).toContain("Rows per page");
    expect(directorySource).toContain("First page");
    expect(directorySource).toContain("Last page");
    expect(cssSource).toContain("max-height: min(65vh, 720px)");
    expect(cssSource).toContain("position: sticky");
    expect(bulkCssSource).toContain("position:sticky");
  });

  it("offers meaningful organization, employment and readiness filters", () => {
    for (const label of ["Department", "Portal role", "Job title", "Contract type", "Employment status", "Primary base", "Group", "Readiness", "Contract record", "Work pattern", "Contract expiry"]) {
      expect(directorySource).toContain(label);
    }
    expect(serviceSource).toContain("/workforce/hr/people/facets");
    expect(typeSource).toContain("HrPeopleFacets");
    expect(typeSource).toContain("department_id");
    expect(typeSource).toContain("group_id");
  });

  it("supports explicit page selection and select-all-matching semantics", () => {
    expect(directorySource).toContain("Select current page");
    expect(directorySource).toContain("Select all");
    expect(directorySource).toContain("All matching filters selected");
    expect(directorySource).toContain("exclude_user_ids");
    expect(bulkSource).toContain("Select all");
    expect(bulkSource).toContain("Changing filters clears the current bulk selection");
    expect(typeSource).toContain('mode: "EXPLICIT"');
    expect(typeSource).toContain('mode: "FILTERED"');
  });

  it("provides preview, idempotent submission, progress, failure export and retry", () => {
    expect(serviceSource).toContain("/people/contracts/preview");
    expect(serviceSource).toContain("/bulk-operations/contracts");
    expect(serviceSource).toContain("Idempotency-Key");
    expect(serviceSource).toContain("/failures.csv");
    expect(serviceSource).toContain("/retry");
    expect(serviceSource).toContain("/resume");
    expect(typeSource).toContain("HrBulkOperation");
    expect(bulkSource).toContain("Preview contract batch");
    expect(bulkSource).toContain("Retry failed only");
    expect(bulkSource).toContain("Failure report");
    expect(bulkSource).toContain("progress_percent");
    expect(bulkSource).toContain("bulk_search");
  });

  it("keeps default-pattern changes behind an eligibility snapshot", () => {
    expect(serviceSource).toContain("/people/default-day-pattern/preview");
    expect(serviceSource).toContain("/bulk-operations/default-day-pattern");
    expect(serviceSource).toContain("expected_match_count");
    expect(serviceSource).toContain("expected_selection_token");
    expect(typeSource).toContain("selection_token");
    expect(bulkSource).toContain("This never blindly processes the tenant");
  });

  it("separates the register, batch setup and operational queues", () => {
    expect(pagesSource).toContain("WorkforceHrWorkspaceV2");
    expect(wrapperSource).toContain("People & contracts");
    expect(wrapperSource).toContain("Batch setup");
    expect(wrapperSource).toContain("Leave, time & patterns");
    expect(wrapperSource).toContain("WorkforceOperationsWorkspace");
    expect(wrapperSource).not.toContain('import("./WorkforceHrWorkspace")');
    expect(operationsSource).toMatch(/type (OperationsSection|Section) = "overview" \| "leave" \| "time" \| "patterns"/);
    expect(operationsSource).not.toContain('label: "People & contracts"');
    expect(operationsSource).toContain('pattern_state: "MISSING"');
    expect(operationsSource).toContain("page_size: 25");
    expect(wrapperSource).toContain("getWorkforceHrDashboard(1)");
  });
});
