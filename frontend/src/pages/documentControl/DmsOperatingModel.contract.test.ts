import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const shell = readFileSync(new URL("./DocumentControlShell.tsx", import.meta.url), "utf-8");
const router = readFileSync(new URL("../../router.tsx", import.meta.url), "utf-8");
const pageExports = readFileSync(new URL("../DocControlPages.tsx", import.meta.url), "utf-8");
const homePage = readFileSync(new URL("./DocumentGovernanceDashboardPage.tsx", import.meta.url), "utf-8");
const libraryPage = readFileSync(new URL("./DocumentLibraryHubPage.tsx", import.meta.url), "utf-8");
const libraryService = readFileSync(new URL("../../services/documentLibrary.ts", import.meta.url), "utf-8");
const recordEntry = readFileSync(new URL("./DocumentControlRecordEntryPage.tsx", import.meta.url), "utf-8");
const recordPage = readFileSync(new URL("./DocumentControlRecordPage.tsx", import.meta.url), "utf-8");
const recordActions = readFileSync(new URL("./DocumentControlRecordActions.tsx", import.meta.url), "utf-8");
const recordActionsBase = readFileSync(new URL("./DocumentControlRecordActionsBase.tsx", import.meta.url), "utf-8");
const changesPortfolio = readFileSync(new URL("./DocumentControlChangesPortfolioPage.tsx", import.meta.url), "utf-8");
const changesService = readFileSync(new URL("../../services/documentControlPortfolios.ts", import.meta.url), "utf-8");
const distributionPortfolio = readFileSync(new URL("./DocumentControlDistributionPortfolioPage.tsx", import.meta.url), "utf-8");
const distributionService = readFileSync(new URL("../../services/documentControlDistributionPortfolio.ts", import.meta.url), "utf-8");
const compliancePortfolio = readFileSync(new URL("./DocumentControlCompliancePortfolioPage.tsx", import.meta.url), "utf-8");
const complianceService = readFileSync(new URL("../../services/documentControlCompliancePortfolio.ts", import.meta.url), "utf-8");
const externalActions = readFileSync(new URL("./DocumentControlExternalSourceActions.tsx", import.meta.url), "utf-8");
const reportsPage = readFileSync(new URL("./DocumentControlReportsPage.tsx", import.meta.url), "utf-8");
const reportsService = readFileSync(new URL("../../services/documentControlReportsPortfolio.ts", import.meta.url), "utf-8");
const administrationPage = readFileSync(new URL("./DocumentControlAdministrationPage.tsx", import.meta.url), "utf-8");
const administrationService = readFileSync(new URL("../../services/documentControlReports.ts", import.meta.url), "utf-8");
const manualReader = readFileSync(new URL("../manuals/ManualReaderPage.tsx", import.meta.url), "utf-8");
const readerExperience = readFileSync(new URL("../manuals/dmsReaderExperience.css", import.meta.url), "utf-8");

describe("DMS frontend operating-model contract", () => {
  it("keeps permanent Document Control navigation bounded to seven daily workspaces", () => {
    for (const label of ["Home", "Library", "Changes", "Distribution", "Compliance", "Reports", "Administration"]) {
      expect(shell).toContain(`label: "${label}"`);
    }
    expect(shell).not.toContain("Document structure");
    expect(shell).not.toContain("Generated records");
    expect(shell).not.toContain("Authority submissions");
    expect(shell).not.toContain("Temporary revisions");
    expect(shell).not.toContain("QMS and module links");
  });

  it("mounts assisted search only in Library/document context rather than permanent DMS chrome", () => {
    expect(shell).toContain("DocumentationAssistantPanel");
    expect(shell).toContain("showContextualAssistant");
    expect(shell).toContain('location.pathname.includes("/document-control/library")');
    expect(shell).toContain('title={assistantDocumentId ? "Document evidence search" : "Controlled information search"}');
    expect(shell).not.toContain('label: "Assistant"');
  });

  it("keeps canonical and specialist compatibility URLs addressable while converging legacy lists", () => {
    for (const route of [
      "/maintenance/:amoCode/document-control/changes",
      "/maintenance/:amoCode/document-control/distribution",
      "/maintenance/:amoCode/document-control/compliance",
      "/maintenance/:amoCode/document-control/reports",
      "/maintenance/:amoCode/document-control/administration",
      "/maintenance/:amoCode/document-control/controlled-copies",
      "/maintenance/:amoCode/document-control/structure",
      "/maintenance/:amoCode/document-control/records",
    ]) expect(router).toContain(`path="${route}"`);

    expect(pageExports).toContain('suffix="/changes" view="in-review"');
    expect(pageExports).toContain('suffix="/changes" view="requests"');
    expect(pageExports).toContain('suffix="/changes" view="authority"');
    expect(pageExports).toContain('suffix="/changes" view="temporary-revisions"');
    expect(pageExports).toContain('suffix="/compliance" view="reviews"');
    expect(pageExports).toContain('suffix="/compliance" view="external-sources"');
    expect(pageExports).toContain('suffix="/compliance" view="relationships"');
    expect(pageExports).toContain('query.set("status", "ARCHIVED")');
    expect(pageExports).toContain('suffix="/reports"');
    expect(pageExports).toContain('suffix="/administration"');
  });

  it("gives Library the MD preset views and bounded rich controlled-information discovery", () => {
    for (const label of ["All Documents", "My Documents", "Favorites", "Recently Opened", "Recently Revised", "Awaiting My Review", "External Technical Data", "Due for Review", "Superseded", "Archived"]) {
      expect(libraryPage).toContain(`label: "${label}"`);
    }
    expect(libraryPage).toContain("discoverLibrary");
    expect(libraryPage).toContain("Permission-filtered discovery · server-bounded");
    expect(libraryPage).toContain("alias, owner, revision, filename, hierarchy or indexed text");
    expect(libraryService).toContain("library-discovery");
    expect(libraryService).toContain("per_page");
  });

  it("routes canonical Changes to a bounded paginated portfolio", () => {
    expect(router).toContain("DocControlChangesPortfolioPage");
    expect(router).toContain('path="/maintenance/:amoCode/document-control/changes" element={<WorkspaceRequireAuth><DocControlChangesPortfolioPage />');
    expect(changesService).toContain("changes-portfolio");
    expect(changesService).toContain("per_page");
    expect(changesPortfolio).toContain("SEARCH_DEBOUNCE_MS = 320");
    expect(changesPortfolio).toContain('data-testid="document-control-changes"');
    for (const label of ["Requests", "Draft", "In Review", "Awaiting Quality", "Awaiting Management", "Authority", "Temporary Revisions", "Ready for Release", "Closed"]) expect(changesPortfolio).toContain(`label: "${label}"`);
  });

  it("makes raising a change request a real document-selection to canonical mutation flow", () => {
    expect(changesPortfolio).toContain("/library?action=raise-change");
    expect(changesPortfolio).not.toContain("`${basePath}/change-proposals`");
    expect(libraryPage).toContain('params.get("action") === "raise-change"');
    expect(libraryPage).toContain("Select a document for the change request");
    expect(libraryPage).toContain("Select for change");
    expect(libraryPage).toContain('navigate(`${basePath}/library/${item.id}?tab=changes`)');
    expect(recordActions).toContain('activeView === "changes"');
    expect(recordActions).toContain('activeView="changes"');
    expect(recordActionsBase).toContain("function ChangeRequestForm");
    expect(recordActionsBase).toContain("createDocumentChangeRequest");
  });

  it("routes canonical Distribution to the bounded custody portfolio", () => {
    expect(pageExports).toContain('DocControlDistributionPage } from "./documentControl/DocumentControlDistributionPortfolioPage"');
    expect(distributionService).toContain("distribution-portfolio");
    expect(distributionService).toContain("per_page");
    expect(distributionPortfolio).toContain('data-testid="document-control-distribution"');
    for (const label of ["Current Distributions", "Pending Acknowledgements", "Overdue Acknowledgements", "Physical Copies", "Recalls"]) expect(distributionPortfolio).toContain(`label: "${label}"`);
  });

  it("routes canonical Compliance to the bounded assurance portfolio", () => {
    expect(pageExports).toContain("function DocControlReviewsPage()");
    expect(pageExports).toContain("<CompliancePage />");
    expect(complianceService).toContain("compliance-portfolio");
    expect(complianceService).toContain("per_page");
    expect(compliancePortfolio).toContain('data-testid="document-control-compliance"');
    expect(compliancePortfolio).toContain("useDocumentControlRoute");
    expect(compliancePortfolio).not.toContain("window.location.pathname.split");
    for (const label of ["Periodic Reviews", "External Technical Data", "Relationship Review", "Applicability", "Superseded References"]) expect(compliancePortfolio).toContain(`label: "${label}"`);
  });

  it("keeps compliance links canonical and clears status when changing assurance domains", () => {
    expect(homePage).toContain("/compliance?view=external-sources");
    expect(homePage).not.toContain("/compliance?view=external\"");
    expect(compliancePortfolio).toContain('if (raw === "external") return "external-sources"');
    expect(compliancePortfolio).toMatch(/if \(key === "view"\) \{\s*next\.delete\("status"\)/);
    expect(compliancePortfolio).toContain('if (value !== "external-sources") next.delete("assessment_source")');
  });

  it("makes Reports a bounded controlled-evidence catalogue instead of a master-register-only page", () => {
    expect(pageExports).toContain("function DocControlRegistersPage()");
    expect(pageExports).toContain("<ReportsPage />");
    expect(reportsService).toContain("reports-portfolio");
    expect(reportsService).toContain("reports-register");
    expect(reportsService).toContain("per_page");
    expect(reportsService).toContain("authHeaders()");
    expect(reportsPage).toContain('data-testid="document-control-reports"');
    for (const label of ["Master Documents", "LEP", "Revisions", "Distribution", "Acknowledgements", "Controlled Copies", "External Sources", "Review Due", "Temporary Revisions", "Authority", "Archive", "Change History", "Retention / Disposition"]) {
      expect(reportsPage).toContain(`label: "${label}"`);
    }
    expect(reportsPage).toContain("Export current page CSV");
    expect(reportsPage).toContain("Print / PDF");
  });

  it("makes Administration a backend-governed low-frequency policy workspace", () => {
    expect(pageExports).toContain("function DocControlSettingsPage()");
    expect(pageExports).toContain("<AdministrationPage />");
    expect(administrationPage).toContain('data-testid="document-control-administration"');
    for (const heading of ["Governance defaults", "Workflow policy", "Retention classes", "Indexing and integration policy", "Physical controlled-copy policy", "Administrative tools"]) {
      expect(administrationPage).toContain(heading);
    }
    expect(administrationPage).toContain("Document classes");
    expect(administrationPage).toContain("Hierarchy & taxonomy");
    expect(administrationPage).toContain("Controlled templates");
    expect(administrationPage).toContain("Integration mappings");
    expect(administrationService).toContain("getDocumentControlAdministration");
    expect(administrationService).toContain("updateDocumentControlAdministration");
  });

  it("neutralizes spreadsheet formulas before producing controlled CSV exports", () => {
    expect(reportsPage).toContain("/^\\s*[=+\\-@]/");
    expect(reportsPage).toContain("? `'${text}` : text");
  });

  it("routes controllers into the lifecycle-rich document workspace while preserving governance tools", () => {
    expect(recordEntry).toContain("<DocumentControlRecordPage />");
    expect(recordEntry).toContain('searchParams.get("governance") === "assignments"');
    expect(recordEntry).toContain("<DocumentGovernanceRecordPage />");
    expect(recordActions).toContain("Responsibilities");
    expect(recordActions).toContain("?governance=assignments");
  });

  it("exposes exactly eight operational document workspace tabs and maps legacy views into them", () => {
    for (const tab of ["Overview", "Content", "Changes", "Workflow", "Distribution", "Compliance", "Relationships", "History"]) expect(recordPage).toContain(`"${tab}"`);
    expect(recordPage).toContain('revisions: "content"');
    expect(recordPage).toContain('authority: "workflow"');
    expect(recordPage).toContain('"temporary-revisions": "changes"');
    expect(recordPage).toContain('copies: "distribution"');
    expect(recordPage).toContain('reviews: "compliance"');
    expect(recordPage).toContain('external: "compliance"');
    expect(recordPage).toContain('integrations: "relationships"');
    expect(recordPage).toContain('next.set("tab", tab)');
  });

  it("aggregates backend entities beneath operational tabs instead of restoring entity tabs", () => {
    expect(recordActions).toContain('activeView === "changes"');
    expect(recordActions).toContain('activeView="temporary-revisions"');
    expect(recordActions).toContain('activeView === "workflow"');
    expect(recordActions).toContain('activeView="authority"');
    expect(recordActions).toContain('activeView === "distribution"');
    expect(recordActions).toContain('activeView="copies"');
    expect(recordActions).toContain('activeView === "compliance"');
    expect(recordActions).toContain('activeView="reviews"');
    expect(recordActions).toContain("DocumentControlExternalSourceActions");
    expect(recordActions).not.toContain('activeView="external"');
    expect(externalActions).toContain("createExternalRevisionReceipt");
    expect(externalActions).toContain('applicability_status: "PENDING"');
    expect(recordActions).toContain('activeView === "relationships"');
    expect(recordActions).toContain("DocumentControlIntegrationActions");
  });

  it("retains the proven Publications reader and exposes Standard, Immersive, Fullscreen and Review Changes", () => {
    expect(router).toContain("./pages/manuals/ManualReaderPage");
    expect(router).toContain("/maintenance/:amoCode/publications/:manualId/rev/:revId/read");
    expect(router).toContain("<PublicationReaderPage />");
    expect(manualReader).toContain('type ReaderExperienceMode = "standard" | "immersive"');
    expect(manualReader).toContain('searchParams.get("readerMode")');
    expect(manualReader).toContain('next.set("readerMode", nextMode)');
    expect(manualReader).toContain("requestFullscreen()");
    expect(manualReader).toContain("document.exitFullscreen()");
    expect(manualReader).toContain("Review changes");
    expect(manualReader).toContain("/diff");
    expect(readerExperience).toContain(".dms-reader-shell--immersive .publication-document-header");
    expect(readerExperience).toContain(".dms-reader-shell--immersive .tenant-shell__sidebar");
    expect(readerExperience).toContain(".dms-reader-shell--fullscreen .publication-document-tabs");
    expect(readerExperience).toContain(".dms-reader-shell--fullscreen .publication-metadata");
  });
});
