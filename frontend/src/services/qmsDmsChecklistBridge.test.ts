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
    expect(prepareSource).toContain("await refresh(binding)");
    expect(prepareSource).toContain("registered as a DMS draft");
  });

  it("does not synchronously set guard state from query-cache render notifications", () => {
    expect(enhancementsSource).not.toContain("getQueryCache().subscribe");
    expect(enhancementsSource).toContain("auditOccurrenceQueryKey");
    expect(enhancementsSource).toContain("getAuditSession");
  });
});
