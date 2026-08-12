import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const shell = readFileSync(new URL("./DocumentControlShell.tsx", import.meta.url), "utf-8");
const launcher = readFileSync(new URL("./DocumentControlJobLauncher.tsx", import.meta.url), "utf-8");
const jobs = readFileSync(new URL("./documentControlJobs.ts", import.meta.url), "utf-8");
const library = readFileSync(new URL("./DocumentLibraryHubPage.tsx", import.meta.url), "utf-8");
const home = readFileSync(new URL("./DocumentGovernanceDashboardPage.tsx", import.meta.url), "utf-8");
const homeService = readFileSync(new URL("../../services/documentControlHome.ts", import.meta.url), "utf-8");
const compliance = readFileSync(new URL("./DocumentControlCompliancePortfolioPage.tsx", import.meta.url), "utf-8");
const integrationService = readFileSync(new URL("../../services/documentControlIntegrationCatalog.ts", import.meta.url), "utf-8");
const reportsService = readFileSync(new URL("../../services/documentControlReportsPortfolio.ts", import.meta.url), "utf-8");
const reportsPage = readFileSync(new URL("./DocumentControlReportsPage.tsx", import.meta.url), "utf-8");
const recordActions = readFileSync(new URL("./DocumentControlRecordActions.tsx", import.meta.url), "utf-8");
const integrationActions = readFileSync(new URL("./DocumentControlIntegrationActions.tsx", import.meta.url), "utf-8");
const guardedLifecycle = readFileSync(new URL("./DocumentControlLifecycleActionsGuarded.tsx", import.meta.url), "utf-8");
const reviewActions = readFileSync(new URL("./DocumentControlReviewActions.tsx", import.meta.url), "utf-8");
const temporaryRevisionActions = readFileSync(new URL("./DocumentControlTemporaryRevisionActions.tsx", import.meta.url), "utf-8");

describe("DMS operational job contract", () => {
  it("exposes one persistent controller work launcher rather than relying on tab discovery", () => {
    expect(shell).toContain("DocumentControlJobLauncher");
    expect(launcher).toContain('data-testid="document-control-start-work"');
    expect(launcher).toContain("Start Document Control work");
    for (const group of ["Change & approval", "Issue & custody", "Assurance & applicability"]) expect(launcher).toContain(group);
  });

  it("defines the major controlled jobs as reusable library-selection flows", () => {
    for (const id of [
      "raise-change",
      "start-workflow",
      "temporary-revision",
      "authority-submission",
      "distribute",
      "controlled-copy",
      "schedule-review",
      "external-source",
      "applicability",
      "integration",
    ]) expect(jobs).toContain(`"${id}"`);
    expect(jobs).toContain("documentJobSelectionPath");
    expect(jobs).toContain("documentJobTarget");
    expect(library).toContain("documentControlJob");
    expect(library).toContain("jobEligibility");
    expect(library).toContain("requiresPublished");
    expect(library).toContain("externalOnly");
  });

  it("preserves the proven raise-change selector while generalizing document selection", () => {
    expect(library).toContain('params.get("action") === "raise-change"');
    expect(library).toContain("Select a document for the change request");
    expect(library).toContain("Select for change");
    expect(library).toContain('navigate(`${basePath}/library/${item.id}?tab=changes`)');
    expect(library).toContain("selectForJob");
    expect(library).toContain("selectedJob.selectLabel");
  });

  it("surfaces specialist obligations in My Work including owned external-source assessment", () => {
    for (const kind of ["AUTHORITY_ACTION", "TEMPORARY_REVISION", "CONTROLLED_COPY", "EXTERNAL_SOURCE_ACTION"]) {
      expect(homeService).toContain(`"${kind}"`);
      expect(home).toContain(`kind === "${kind}"`);
    }
    expect(homeService).toContain('fetchWorkFeed(tenant, "external-source-work")');
    expect(home).toContain("external-source assessment");
    expect(compliance).toContain('params.get("assessment_source")');
    expect(compliance).toContain('next.set("assessment_source", sourceId)');
    expect(compliance).toContain("ExternalRevisionAssessmentPanel");
  });

  it("uses named tenant users for periodic review ownership", () => {
    expect(guardedLifecycle).toContain("DocumentControlReviewActions");
    expect(reviewActions).toContain("Select active tenant user");
    expect(reviewActions).toContain("owner_user_id: ownerId");
    expect(reviewActions).not.toContain("Owner active tenant user ID");
    expect(reviewActions).toContain("non-continuation outcome requires at least one finding and one resulting action");
  });

  it("uses real campaign and revision records for temporary revision terminal dependencies", () => {
    expect(guardedLifecycle).toContain("DocumentControlTemporaryRevisionActions");
    expect(temporaryRevisionActions).toContain("eligibleCampaigns");
    expect(temporaryRevisionActions).toContain('campaign.temporary_revision_id === selected.id');
    expect(temporaryRevisionActions).toContain("eligibleIncorporatingRevisions");
    expect(temporaryRevisionActions).toContain("Select issued campaign");
    expect(temporaryRevisionActions).toContain("Select published permanent revision");
    expect(temporaryRevisionActions).not.toContain("Issued campaign ID");
    expect(temporaryRevisionActions).not.toContain("Incorporating permanent revision ID");
  });

  it("replaces canonical integration ID entry with tenant-scoped record discovery", () => {
    expect(recordActions).toContain("DocumentControlIntegrationActions");
    expect(integrationService).toContain("integration-catalog/search");
    expect(integrationActions).toContain("Select portal module");
    expect(integrationActions).toContain("Select governed record type");
    expect(integrationActions).toContain("Canonical record");
    expect(integrationActions).toContain("Verify and link record");
    expect(integrationActions).toContain("source_table: selectedRecord.source_table");
    expect(integrationActions).not.toContain("Canonical entity ID");
  });

  it("separates current-page convenience exports from full filtered server evidence exports", () => {
    expect(reportsService).toContain("exportReportsCsv");
    expect(reportsService).toContain("reports-export.csv");
    expect(reportsPage).toContain("Export current page CSV");
    expect(reportsPage).toContain("Export full filtered CSV");
    expect(reportsPage).toContain("full filtered register generated by the server");
    expect(reportsPage).toContain("10,000 rows");
    expect(reportsPage).not.toContain("Export all loaded rows");
  });
});
