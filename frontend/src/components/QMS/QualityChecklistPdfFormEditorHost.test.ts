import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const componentSource = readFileSync(new URL("./QualityChecklistPdfFormEditorHost.tsx", import.meta.url), "utf8");
const editorCss = readFileSync(new URL("../../styles/quality-checklist-pdf-form-editor.css", import.meta.url), "utf8");
const inviteCss = readFileSync(new URL("../../styles/car-invite-responsive.css", import.meta.url), "utf8");

describe("Quality checklist PDF form editor contract", () => {
  it("renders AcroForm controls and persists PDF.js annotation storage", () => {
    expect(componentSource).toContain("renderForms");
    expect(componentSource).toContain("saveDocument()");
    expect(componentSource).toContain("qmsUploadAuditChecklist");
    expect(componentSource).toContain("getFieldObjects()");
  });

  it("does not silently discard edited form data", () => {
    expect(componentSource).toContain("Unsaved PDF form changes");
    expect(componentSource).toContain("setDirty(true)");
    expect(componentSource).toContain("Save to portal");
  });

  it("keeps the PDF editor and public CAR workspace usable at normal zoom", () => {
    expect(editorCss).toContain("height: min(94dvh, 1080px)");
    expect(inviteCss).toContain(".car-invite-stage:not(.is-active)");
    expect(inviteCss).toContain("max-height: none");
    expect(inviteCss).toContain(":has(.car-invite-badge--success)");
  });
});
