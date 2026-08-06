/// <reference types="node" />

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

const directorySource = readSource("./components/WorkforcePeopleDirectory.tsx");
const wrapperSource = readSource("./components/WorkforceHrWorkspaceV2.tsx");
const pagesSource = readSource("./WorkforceRosteringPagesV2.tsx");
const serviceSource = readSource("../../services/workforceHr.ts");
const typeSource = readSource("../../types/workforceHr.ts");
const cssSource = readSource("./components/workforce-people-directory.css");


describe("Scalable Workforce people directory", () => {
  it("uses server-side pagination with bounded page sizes", () => {
    expect(serviceSource).toContain("/workforce/hr/people");
    expect(serviceSource).toContain("page_size");
    expect(directorySource).toContain("const PAGE_SIZES = [25, 50, 100, 200]");
    expect(directorySource).toContain("Rows per page");
    expect(directorySource).toContain("First page");
    expect(directorySource).toContain("Last page");
    expect(cssSource).toContain("max-height: min(65vh, 720px)");
    expect(cssSource).toContain("position: sticky");
  });

  it("offers meaningful organization, employment and readiness filters", () => {
    for (const label of [
      "Department",
      "Portal role",
      "Job title",
      "Contract type",
      "Employment status",
      "Primary base",
      "Group",
      "Readiness",
      "Contract record",
      "Work pattern",
      "Contract expiry",
    ]) {
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
    expect(typeSource).toContain('mode: "EXPLICIT"');
    expect(typeSource).toContain('mode: "FILTERED"');
  });

  it("previews controlled batch changes before applying them", () => {
    expect(serviceSource).toContain("/people/default-day-pattern/preview");
    expect(serviceSource).toContain("/people/default-day-pattern/apply");
    expect(directorySource).toContain("Controlled batch preview");
    expect(directorySource).toContain("expectedMatchCount");
    expect(directorySource).toContain("Existing active patterns are preserved");
    expect(directorySource).toContain("Export CSV");
  });

  it("loads the large people register separately from HR operations", () => {
    expect(pagesSource).toContain("WorkforceHrWorkspaceV2");
    expect(wrapperSource).toContain("People & contracts");
    expect(wrapperSource).toContain("Leave, time & patterns");
    expect(wrapperSource).toContain("lazy(() => import(\"./WorkforceHrWorkspace\")");
    expect(wrapperSource).toContain("getWorkforceHrDashboard(1)");
  });
});
