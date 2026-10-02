import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";


const serviceSource = readFileSync(new URL("./qmsChecklistTemplates.ts", import.meta.url), "utf8");
const prepareSource = readFileSync(
  new URL("../features/qms/auditSession/AuditPrepareWorkspace.tsx", import.meta.url),
  "utf8",
);
const intakeSource = readFileSync(
  new URL("../components/documentControl/ControlledDocumentUploadDialog.tsx", import.meta.url),
  "utf8",
);
const enhancementsSource = readFileSync(
  new URL("../components/QMS/QualityEnhancementsHost.tsx", import.meta.url),
  "utf8",
);


describe("QMS and DMS checklist integration contract", () => {
  it("binds documents through a server-resolved current-revision endpoint", () => {
    expect(serviceSource).toContain("/checklist-library/${encodeURIComponent(documentId)}/bind-current");
    expect(prepareSource).toContain("Current controlled document");
    expect(prepareSource).toContain("Use current revision");
    expect(prepareSource).not.toContain("Select exact revision");
    expect(prepareSource).not.toContain("Exact controlled revision");
  });

  it("supports DMS search, remembered suggestions, and governed in-context upload", () => {
    expect(prepareSource).toContain("Suggested from a similar audit");
    expect(prepareSource).toContain("Upload to DMS");
    expect(serviceSource).toContain("/checklist-library/upload");
    expect(intakeSource).toContain("Confirm metadata");
    expect(intakeSource).toContain("Parent controlled document");
    expect(intakeSource).toContain('value: "WORK_INSTRUCTION"');
    expect(intakeSource).toContain('value: "RECORD"');
  });

  it("keeps draft intake out of fieldwork and binds an approved current revision", () => {
    expect(intakeSource).toContain("Already approved final PDF");
    expect(intakeSource).toContain("approvePublicationIntake");
    expect(intakeSource).toContain('approval_kind: "INTERNAL"');
    expect(prepareSource).toContain("allowApprovedIntake");
    expect(prepareSource).toContain("result.approved_intake === true");
    expect(prepareSource).toContain("await bindCurrentDmsChecklist");
    expect(prepareSource).toContain("const confirmed = await confirmChecklistBinding(binding);");
    expect(prepareSource).toContain("registered as a DMS draft");
  });

  it("fails closed when either live binding authority read cannot confirm persistence", () => {
    expect(prepareSource).toContain("const confirmChecklistBinding");
    expect(prepareSource).toContain("getAuditPreparationContext(amoCode, auditId)");
    expect(prepareSource).toContain("listChecklistBindings(amoCode, auditId)");
    expect(prepareSource).not.toContain("const cacheChecklistBinding");
    expect(prepareSource).not.toContain("contextQuery.refetch()");
    expect(prepareSource).not.toContain("fullBindingsQuery.refetch()");
    expect(prepareSource).not.toContain("refresh(binding)");
    expect(prepareSource).toContain('["qms", "prepare-checklist-bindings", amoCode, auditId]');
    const confirmIndex = prepareSource.indexOf("const confirmed = await confirmChecklistBinding(binding);");
    const successIndex = prepareSource.indexOf('setLocalSuccess("The current effective DMS checklist is bound to fieldwork.");');
    expect(confirmIndex).toBeGreaterThan(-1);
    expect(successIndex).toBeGreaterThan(confirmIndex);
  });

  it("uses the same live confirmation after approved DMS intake", () => {
    const approvedIntake = prepareSource.indexOf("if (result.approved_intake === true)");
    const confirmation = prepareSource.indexOf("const confirmed = await confirmChecklistBinding(binding);", approvedIntake);
    const success = prepareSource.indexOf("The approved checklist is now current in DMS and populated for this audit.", approvedIntake);
    expect(approvedIntake).toBeGreaterThan(-1);
    expect(confirmation).toBeGreaterThan(approvedIntake);
    expect(success).toBeGreaterThan(confirmation);
    expect(prepareSource).toContain("throw error instanceof Error ? error : new Error(message);");
  });
  it("does not synchronously set guard state from query-cache render notifications", () => {
    expect(enhancementsSource).not.toContain("getQueryCache().subscribe");
    expect(enhancementsSource).toContain("auditOccurrenceQueryKey");
    expect(enhancementsSource).toContain("getAuditSession");
  });
});
