import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const host = readFileSync(new URL("./QualityChecklistTemplateHost.tsx", import.meta.url), "utf-8");
const page = readFileSync(new URL("../../pages/qms/QmsCanonicalPage.tsx", import.meta.url), "utf-8");
const service = readFileSync(new URL("../../services/qmsChecklistTemplates.ts", import.meta.url), "utf-8");

describe("QualityChecklistTemplateHost library contract", () => {
  it("uses an Audits-like toolbar without a duplicate Checklist library H1", () => {
    expect(host).toContain('className="qms-checklist-library__toolbar"');
    expect(host).not.toMatch(/<h1>\s*Checklist library\s*<\/h1>/);
    expect(host).not.toContain("qms-checklist-template-page__header");
  });

  it("gates manage actions and retires the floating launcher path", () => {
    expect(host).toContain('hasQmsRolePermission("qms.audit.manage")');
    expect(host).toContain("if (!libraryRoute || !resolvedAmo) return null");
    expect(host).not.toContain("qms-checklist-template-launcher");
    expect(host).not.toContain("PanelRightOpen");
  });

  it("keeps Prepare-bind guidance on the library surface", () => {
    expect(host).toContain("Apply checklists to an audit from Prepare.");
    expect(host).toContain("qms-checklist-library__bind-note");
    expect(page).toContain("Controlled DMS checklists and structured fieldwork templates. Bind during Prepare.");
  });

  it("defers revision item editing until a template exists", () => {
    expect(host).toContain("openBlankEditor");
    expect(host).toContain("setCreatingTemplate(true)");
    expect(host).toContain("setItems([])");
    expect(host).toContain("const showRevisionEditor = Boolean(selectedTemplateId)");
  });

  it("opens AI drafting as an overlay drawer without a library split or resizer", () => {
    expect(host).toContain("qms-checklist-ai--overlay");
    expect(host).toContain("qms-checklist-ai-backdrop");
    expect(host).not.toContain("qms-checklist-library__split");
    expect(host).not.toContain("qms-checklist-library__resizer");
    expect(host).not.toContain("beginResize");
    expect(host).not.toContain("splitPercent");
  });

  it("selects readable criteria without requiring PUBLISHED-only kind", () => {
    expect(host).toContain("hasReadableCriteriaRevision");
    expect(host).toContain("isCriteriaCandidate");
    expect(host).toContain("read_target?.revision_id || row.current_revision?.id");
    expect(host).not.toContain('read_target.kind === "PUBLISHED"');
    expect(host).toContain("No readable controlled criteria yet. Publish or approve a manual/procedure/checklist in Document Control, or upload one here.");
    expect(host).toContain("qms-checklist-ai__criteria-row");
  });

  it("wires manage delete and retire actions through existing services", () => {
    expect(host).toContain("deleteDocument");
    expect(host).toContain("retireChecklistTemplate");
    expect(service).toContain("export function retireChecklistTemplate");
    expect(service).toContain('method: "DELETE"');
  });
});
