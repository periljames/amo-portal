import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const page = readFileSync(new URL("./PublicationsReaderPage.tsx", import.meta.url), "utf-8");
const panel = readFileSync(new URL("./PublicationGovernancePanel.tsx", import.meta.url), "utf-8");
const viewer = readFileSync(new URL("./PublicationPdfLayoutViewer.tsx", import.meta.url), "utf-8");
const core = readFileSync(new URL("./PdfReaderCoreV3.tsx", import.meta.url), "utf-8");

describe("Publication reader governance architecture", () => {
  it("layers governance around the reader instead of taking over PDF navigation", () => {
    expect(page).toContain('import PublicationGovernancePanel from "./PublicationGovernancePanel"');
    expect(page).toContain("<PublicationGovernancePanel");
    expect(viewer).not.toContain("readerGovernance");
    expect(viewer).not.toContain("DocumentAnnotation");
    expect(viewer).toContain("renderPageOverlay");
    expect(core).toContain("renderOverlay={renderPageOverlay}");
  });

  it("offers checksum-bound annotations, exact selections and evidence actions", () => {
    expect(panel).toContain('createAnnotation("NOTE")');
    expect(panel).toContain('createAnnotation("BOOKMARK")');
    expect(panel).toContain('createAnnotation("HIGHLIGHT")');
    expect(panel).toContain('createAnnotation("EVIDENCE")');
    expect(panel).toContain("selectedPdfLocation");
    expect(panel).toContain("range.getClientRects()");
    expect(panel).toContain("normalized_rects: selected.normalized_rects || []");
    expect(panel).toContain("createEvidenceSnapshot");
    expect(panel).toContain("getEvidenceSnapshot");
  });

  it("renders governed annotations in V3's non-navigation overlay slot", () => {
    expect(page).toContain("governedAnnotations={readerAnnotations}");
    expect(page).toContain("onAnnotationsChanged={setReaderAnnotations}");
    expect(viewer).toContain("publication-governed-annotation-mark");
    expect(viewer).toContain("publication-governed-annotation-pin");
    expect(viewer).toContain("onGovernedAnnotationClick");
  });

  it("keeps cross-revision annotation movement human-governed", () => {
    expect(panel).toContain("prepareAnnotationMigrations");
    expect(panel).toContain('decideMigration(migration, "ACCEPT")');
    expect(panel).toContain('decideMigration(migration, "REJECT")');
    expect(panel).toContain('migration.strategy === "UNRESOLVED"');
  });
});
