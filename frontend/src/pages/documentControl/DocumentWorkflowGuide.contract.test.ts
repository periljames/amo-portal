import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const shell = readFileSync(new URL("./DocumentControlShell.tsx", import.meta.url), "utf-8");
const guide = readFileSync(new URL("./DocumentWorkflowGuide.tsx", import.meta.url), "utf-8");
const lifecycle = readFileSync(new URL("./DocumentControlLifecycleActions.tsx", import.meta.url), "utf-8");
const reports = readFileSync(new URL("./DocumentControlReportsPage.tsx", import.meta.url), "utf-8");

describe("DMS guided workflow contract", () => {
  it("mounts a persistent document workflow guide in the document shell", () => {
    expect(shell).toContain('import DocumentWorkflowGuide from "./DocumentWorkflowGuide"');
    expect(shell).toContain("assistantDocumentId");
    expect(shell).toContain("<DocumentWorkflowGuide");
    expect(shell).toContain("refreshKey={workflowRefreshKey}");
  });

  it("derives the primary CTA from authoritative document workflow state", () => {
    expect(guide).toContain("getDocumentControlDocument");
    for (const state of [
      "CORRECTIONS_REQUIRED",
      "DRAFT",
      "TECHNICAL_REVIEW",
      "TECHNICAL_APPROVED",
      "QUALITY_REVIEW",
      "QUALITY_APPROVED",
      "ACCOUNTABLE_MANAGER_APPROVAL",
      "AUTHORITY_SUBMITTED",
      "AUTHORITY_APPROVED",
      "SCHEDULED_FOR_EFFECTIVITY",
      "PUBLISHED",
    ]) expect(guide).toContain(`workflow.state === "${state}"`);

    for (const action of [
      "Upload revision",
      "Start workflow",
      "Submit technical review",
      "Open technical review",
      "Start Quality review",
      "Open Quality review",
      "Submit to management",
      "Open approval controls",
      "Open authority controls",
      "Schedule effectivity",
      "Resolve blockers",
      "Publish revision",
      "Track distribution",
      "Open compliance controls",
    ]) expect(guide).toContain(`label: "${action}"`);
  });

  it("surfaces server readiness and blockers instead of inventing a parallel workflow", () => {
    expect(guide).toContain("workflow?.blockers");
    expect(guide).toContain("training_readiness_status");
    expect(guide).toContain("qms_readiness_status");
    expect(guide).toContain("distribution_readiness_status");
    expect(guide).not.toContain("transitionDocumentWorkflow");
    expect(lifecycle).toContain("transitionDocumentWorkflow");
  });

  it("provides direct input/form and output/evidence launchers", () => {
    expect(guide).toContain("Inputs & forms");
    for (const input of ["Revision", "Change", "Workflow", "Authority", "Distribution", "Compliance", "Relationship"]) {
      expect(guide).toContain(`["${input}"`);
    }
    expect(guide).toContain("#document-control-record-actions");
    expect(guide).toContain("Outputs & evidence");
    for (const output of ["Audit history", "Distribution evidence", "Compliance evidence"]) {
      expect(guide).toContain(`["${output}"`);
    }
    expect(guide).toContain('navigate(`${basePath}/reports`)');
  });

  it("keeps reports operational with printable and exportable evidence", () => {
    expect(reports).toContain("Print / PDF");
    expect(reports).toContain("Export current page CSV");
    expect(reports).toContain("downloadCsv");
  });
});
