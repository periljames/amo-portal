import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const shell = readFileSync(new URL("./DocumentControlShell.tsx", import.meta.url), "utf-8");
const router = readFileSync(new URL("../../router.tsx", import.meta.url), "utf-8");
const recordEntry = readFileSync(new URL("./DocumentControlRecordEntryPage.tsx", import.meta.url), "utf-8");
const recordPage = readFileSync(new URL("./DocumentControlRecordPage.tsx", import.meta.url), "utf-8");
const recordActions = readFileSync(new URL("./DocumentControlRecordActions.tsx", import.meta.url), "utf-8");
const changesPortfolio = readFileSync(new URL("./DocumentControlChangesPortfolioPage.tsx", import.meta.url), "utf-8");
const portfolioService = readFileSync(new URL("../../services/documentControlPortfolios.ts", import.meta.url), "utf-8");
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

  it("does not mount the documentation assistant as permanent DMS chrome", () => {
    expect(shell).not.toContain("DocumentationAssistantPanel");
  });

  it("provides stable canonical entry URLs without deleting compatibility routes", () => {
    for (const route of [
      "/maintenance/:amoCode/document-control/changes",
      "/maintenance/:amoCode/document-control/compliance",
      "/maintenance/:amoCode/document-control/reports",
      "/maintenance/:amoCode/document-control/administration",
    ]) {
      expect(router).toContain(`path="${route}"`);
    }

    for (const compatibilityRoute of [
      "/maintenance/:amoCode/document-control/drafts",
      "/maintenance/:amoCode/document-control/change-proposals",
      "/maintenance/:amoCode/document-control/tr",
      "/maintenance/:amoCode/document-control/reviews",
      "/maintenance/:amoCode/document-control/external-sources",
      "/maintenance/:amoCode/document-control/integrations",
      "/maintenance/:amoCode/document-control/registers",
      "/maintenance/:amoCode/document-control/settings",
    ]) {
      expect(router).toContain(`path="${compatibilityRoute}"`);
    }
  });

  it("routes canonical Changes to a bounded paginated portfolio without replacing compatibility worklists", () => {
    expect(router).toContain("DocControlChangesPortfolioPage");
    expect(router).toContain('path="/maintenance/:amoCode/document-control/changes" element={<WorkspaceRequireAuth><DocControlChangesPortfolioPage />');
    expect(router).toContain('path="/maintenance/:amoCode/document-control/drafts" element={<WorkspaceRequireAuth><DocControlDraftsPage />');
    expect(portfolioService).toContain("changes-portfolio");
    expect(portfolioService).toContain("per_page");
    expect(changesPortfolio).toContain("SEARCH_DEBOUNCE_MS = 320");
    expect(changesPortfolio).toContain('aria-busy={refreshing}');
    for (const label of ["Requests", "Draft", "In Review", "Awaiting Quality", "Awaiting Management", "Authority", "Temporary Revisions", "Ready for Release", "Closed"]) {
      expect(changesPortfolio).toContain(`label: "${label}"`);
    }
  });

  it("routes controllers into the lifecycle-rich document workspace while preserving governance tools", () => {
    expect(recordEntry).toContain("<DocumentControlRecordPage />");
    expect(recordEntry).toContain('searchParams.get("governance") === "assignments"');
    expect(recordEntry).toContain("<DocumentGovernanceRecordPage />");
    expect(recordActions).toContain("Responsibilities");
    expect(recordActions).toContain("?governance=assignments");
  });

  it("exposes exactly eight operational document workspace tabs and maps legacy views into them", () => {
    for (const tab of ["Overview", "Content", "Changes", "Workflow", "Distribution", "Compliance", "Relationships", "History"]) {
      expect(recordPage).toContain(`"${tab}"`);
    }
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
    expect(recordActions).toContain('activeView="external"');
    expect(recordActions).toContain('activeView === "relationships"');
    expect(recordActions).toContain('activeView="integrations"');
  });

  it("retains the proven Publications reader and adds URL-addressable immersive/fullscreen experience controls", () => {
    expect(router).toContain("./pages/manuals/ManualReaderPage");
    expect(router).toContain("/maintenance/:amoCode/publications/:manualId/rev/:revId/read");
    expect(router).toContain("<PublicationReaderPage />");
    expect(manualReader).toContain('type ReaderExperienceMode = "standard" | "immersive"');
    expect(manualReader).toContain('searchParams.get("readerMode")');
    expect(manualReader).toContain('next.set("readerMode", nextMode)');
    expect(manualReader).toContain("requestFullscreen()");
    expect(manualReader).toContain("document.exitFullscreen()");
    expect(readerExperience).toContain(".dms-reader-shell--immersive .publication-document-header");
    expect(readerExperience).toContain(".dms-reader-shell--immersive .tenant-shell__sidebar");
    expect(readerExperience).toContain(".dms-reader-shell--fullscreen .publication-document-tabs");
    expect(readerExperience).toContain(".dms-reader-shell--fullscreen .publication-metadata");
  });
});
