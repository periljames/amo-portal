import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const shell = readFileSync(new URL("./DocumentControlShell.tsx", import.meta.url), "utf-8");
const router = readFileSync(new URL("../../router.tsx", import.meta.url), "utf-8");
const recordEntry = readFileSync(new URL("./DocumentControlRecordEntryPage.tsx", import.meta.url), "utf-8");
const recordPage = readFileSync(new URL("./DocumentControlRecordPage.tsx", import.meta.url), "utf-8");
const recordActions = readFileSync(new URL("./DocumentControlRecordActions.tsx", import.meta.url), "utf-8");

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

  it("retains the proven Publications reader route family as the canonical reading owner", () => {
    expect(router).toContain("./pages/manuals/ManualReaderPage");
    expect(router).toContain("/maintenance/:amoCode/publications/:manualId/rev/:revId/read");
    expect(router).toContain("<PublicationReaderPage />");
  });
});
