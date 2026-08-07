import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const page = readFileSync(new URL("./PublicationsReaderPage.tsx", import.meta.url), "utf-8");
const panel = readFileSync(new URL("./PublicationGovernancePanel.tsx", import.meta.url), "utf-8");
const viewer = readFileSync(new URL("./PublicationPdfLayoutViewer.tsx", import.meta.url), "utf-8");

describe("Publication reader governance architecture", () => {
  it("layers governance around the reader instead of inside the PDF navigation engine", () => {
    expect(page).toContain('import PublicationGovernancePanel from "./PublicationGovernancePanel"');
    expect(page).toContain("<PublicationGovernancePanel");
    expect(viewer).not.toContain("readerGovernance");
    expect(viewer).not.toContain("DocumentAnnotation");
  });

  it("offers revision-bound annotation and evidence actions", () => {
    expect(panel).toContain('createAnnotation("NOTE")');
    expect(panel).toContain('createAnnotation("BOOKMARK")');
    expect(panel).toContain('createAnnotation("HIGHLIGHT")');
    expect(panel).toContain("createEvidenceSnapshot");
  });

  it("keeps cross-revision annotation movement human-governed", () => {
    expect(panel).toContain("prepareAnnotationMigrations");
    expect(panel).toContain('decideMigration(migration, "ACCEPT")');
    expect(panel).toContain('decideMigration(migration, "REJECT")');
    expect(panel).toContain('migration.strategy === "UNRESOLVED"');
  });
});
