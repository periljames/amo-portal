/// <reference types="node" />

import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

function readSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, import.meta.url), "utf8");
}

const directorySource = readSource("./components/WorkforcePeopleDirectory.tsx");
const bulkSource = readSource("./components/WorkforceBulkSetupPanel.tsx");
const governanceSource = readSource("./components/WorkforceGovernancePanel.tsx");
const wrapperSource = readSource("./components/WorkforceHrWorkspaceV2.tsx");
const operationsSource = readSource("./components/WorkforceOperationsWorkspace.tsx");
const pagesSource = readSource("./WorkforceRosteringPagesV2.tsx");
const serviceSource = readSource("../../services/workforceHr.ts");
const typeSource = readSource("../../types/workforceHr.ts");
const cssSource = readSource("./components/workforce-people-directory.css");
const bulkCssSource = readSource("./components/workforce-bulk-setup.css");
const governanceCssSource = readSource("./components/workforce-governance.css");

describe("Scalable Workforce people directory", () => {
  it("uses server-side pagination with bounded page sizes", () => {
    expect(serviceSource).toContain("/workforce/hr/people/governed");
    expect(serviceSource).toContain("page_size");
    expect(directorySource).toContain("const PAGE_SIZES = [25, 50, 100, 200]");
    expect(bulkSource).toContain("const PAGE_SIZES = [25, 50, 100, 250]");
    expect(governanceSource).toContain("const PAGE_SIZES = [25, 50, 100, 250]");
    expect(directorySource).toContain("Rows per page");
    expect(directorySource).toContain("First page");
    expect(directorySource).toContain("Last page");
    expect(cssSource).toContain("max-height: min(65vh, 720px)");
    expect(cssSource).toContain("position: sticky");
    expect(bulkCssSource).toContain("position:sticky");
    expect(governanceCssSource).toContain("position:sticky");
    expect(governanceSource).toContain("10,000 or fewer personnel");
  });

  it("offers governed hierarchy, employment and readiness filters", () => {
    for (const label of ["Department", "Portal role", "Job title", "Contract type", "Employment status", "Primary base", "Group", "Readiness", "Contract record", "Work pattern", "Contract expiry"]) {
      expect(directorySource).toContain(label);
    }
    for (const label of ["Organisation", "Placement", "Job family", "Grade", "Supervisor", "Secondary base", "Lifecycle", "Contract start from", "Contract end to", "Direction"]) {
      expect(governanceSource).toContain(label);
    }
    expect(serviceSource).toContain("/workforce/hr/people/governed/facets");
    expect(serviceSource).toContain("/workforce/hr/supervisors");
    expect(typeSource).toContain("HrPeopleFacets");
    expect(typeSource).toContain("org_unit_id");
    expect(typeSource).toContain("secondary_base_station_id");
    expect(typeSource).toContain("contract_effective_from_on_or_after");
    expect(typeSource).toContain("lifecycle_state");
  });

  it("supports explicit page selection and select-all-matching semantics", () => {
    expect(directorySource).toContain("Select current page");
    expect(directorySource).toContain("Select all");
    expect(directorySource).toContain("All matching filters selected");
    expect(directorySource).toContain("exclude_user_ids");
    expect(bulkSource).toContain("Select all");
    expect(bulkSource).toContain("Changing filters clears the current bulk selection");
    expect(governanceSource).toContain("Select all {total.toLocaleString()} matching");
    expect(governanceSource).toContain("previewWorkforceHrSelection");
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
    expect(governanceSource).toContain("submitWorkforceHrPersonnelMutation");
  });

  it("covers every governed personnel mutation through one durable operation contract", () => {
    for (const operation of [
      "ASSIGN_ORGANIZATION",
      "ASSIGN_POSITION",
      "ASSIGN_BASES",
      "ASSIGN_SUPERVISOR",
      "UPDATE_GROUPS",
      "UPDATE_CONTRACT_SETTINGS",
      "SCHEDULE_OFFBOARDING",
    ]) {
      expect(typeSource).toContain(operation);
      expect(governanceSource).toContain(operation);
    }
    expect(serviceSource).toContain("/workforce/hr/bulk-operations/personnel");
    expect(serviceSource).toContain("/workforce/hr/people/governed/selection-preview");
  });

  it("keeps default-pattern changes behind an eligibility snapshot", () => {
    expect(serviceSource).toContain("/people/default-day-pattern/preview");
    expect(serviceSource).toContain("/bulk-operations/default-day-pattern");
    expect(serviceSource).toContain("expected_match_count");
    expect(serviceSource).toContain("expected_selection_token");
    expect(typeSource).toContain("selection_token");
    expect(bulkSource).toContain("This never blindly processes the tenant");
    expect(serviceSource).toContain("Tenant-wide bootstrap is default-denied");
  });

  it("separates the register, governance, batch setup and operational queues", () => {
    expect(pagesSource).toContain("WorkforceHrWorkspaceV2");
    expect(wrapperSource).toContain("People & contracts");
    expect(wrapperSource).toContain("Organization & roles");
    expect(wrapperSource).toContain("Batch setup");
    expect(wrapperSource).toContain("Leave, time & patterns");
    expect(wrapperSource).toContain("WorkforceGovernancePanel");
    expect(wrapperSource).toContain("WorkforceOperationsWorkspace");
    expect(wrapperSource).not.toContain('import("./WorkforceHrWorkspace")');
    expect(operationsSource).toMatch(/type (OperationsSection|Section) = "overview" \| "leave" \| "time" \| "patterns"/);
    expect(operationsSource).not.toContain('label: "People & contracts"');
    expect(operationsSource).toContain('pattern_state: "MISSING"');
    expect(operationsSource).toContain("page_size: 25");
    expect(wrapperSource).toContain("getWorkforceHrDashboard(1)");
  });
});
