import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

function source(relative: string): string {
  return readFileSync(new URL(relative, import.meta.url), "utf-8");
}

describe("QMS compliance intelligence frontend contract", () => {
  it("keeps audit applicability context as a governed preparation input", () => {
    const prepare = source("./AuditPrepareWorkspace.tsx");
    const service = source("../../../services/qmsChecklistExecutionGovernance.ts");

    expect(service).toContain("/applicability-context");
    expect(prepare).toContain("Applicability context");
    expect(prepare).toContain("Select only governed DMS applicability rules");
    expect(prepare).toContain("addAuditApplicabilityFact");
    expect(prepare).toContain("removeAuditApplicabilityFact");
  });

  it("shows the frozen applicability context and documentary recommendation during fieldwork", () => {
    const live = source("./LiveAuditWorkspace.tsx");

    expect(live).toContain("Audit scope context");
    expect(live).toContain("applicability_context");
    expect(live).toContain("Documentary recommendation");
    expect(live).toContain("Use documentary recommendation");
    expect(live).toContain("does not decide implementation, field verification or the final audit response");
  });

  it("presents context-specific precedence without claiming a universal legal hierarchy", () => {
    const live = source("./LiveAuditWorkspace.tsx");

    expect(live).toContain("Evidence precedence for this question");
    expect(live).toContain("not a universal legal hierarchy");
    expect(live).toContain("authority_policy");
  });

  it("preserves documentary conflict visibility and human decision authority", () => {
    const live = source("./LiveAuditWorkspace.tsx");

    expect(live).toContain("Competing controlled statements");
    expect(live).toContain("No source is silently selected as the winner");
    expect(live).toContain("Auditor decision / override rationale");
    expect(live).toContain("Preserve conflicts in assessment");
  });

  it("keeps attached evidence distinct from evidence explicitly relied upon", () => {
    const evidence = source("./LiveAuditEvidenceStrip.tsx");
    const live = source("./LiveAuditWorkspace.tsx");

    expect(evidence).toContain("Use in assessment");
    expect(evidence).toContain("selectedAssessmentEvidenceIds");
    expect(evidence).toContain("onAssessmentEvidenceChange");
    expect(live).toContain("selectedAssessmentEvidenceIds={assessment?.evidence_ids || []}");
  });

  it("does not permit N/A without an explicit governed basis", () => {
    const live = source("./LiveAuditWorkspace.tsx");

    expect(live).toContain("N/A requires an explicit governed applicability basis");
    expect(live).toContain("applicability_basis");
    expect(live).toContain("applicability_reason");
  });

  it("lets auditors save structured assessment without changing the checklist outcome", () => {
    const live = source("./LiveAuditWorkspace.tsx");

    expect(live).toContain("Save assessment");
    expect(live).toContain("Save notes & assessment");
    expect(live).toContain("unsaved fieldwork changes");
    expect(live).toContain("setSampleDrafts");
    expect(live).toContain("setAssessmentDrafts");
  });

  it("makes completed fieldwork explicitly read-only and preserves supporting-auditor execution", () => {
    const live = source("./LiveAuditWorkspace.tsx");
    const gates = source("./qmsAuditActionGates.ts");

    expect(live).toContain("Fieldwork is complete. This workspace is read-only");
    expect(live).toContain("canExecuteAssignedAudit(auditQuery.data) && !fieldworkComplete");
    expect(gates).toContain("supporting_auditor_user_ids");
  });

  it("keeps documentary, implementation and field verification states independent", () => {
    const live = source("./LiveAuditWorkspace.tsx");

    expect(live).toContain("Documentary status");
    expect(live).toContain("Implementation status");
    expect(live).toContain("Field verification");
    expect(live).toContain("FIELD_VERIFICATION_REQUIRED");
  });
});


describe("QMS governed lifecycle frontend contract", () => {
  it("freezes checklist and applicability preparation inputs once fieldwork opens", () => {
    const prepare = source("./AuditPrepareWorkspace.tsx");

    expect(prepare).toContain("canEditFrozenPreparation");
    expect(prepare).toContain("Applicability context is frozen for the active fieldwork package");
    expect(prepare).toContain("issued checklist baseline is locked while fieldwork is active");
  });

  it("does not present archive as available before governed follow-up is complete", () => {
    const followUp = source("./AuditFollowUpWorkspace.tsx");

    expect(followUp).toContain('closure.follow_up_status === "COMPLETE"');
    expect(followUp).toContain("Archive locked");
    expect(followUp).toContain("COMPLETE_MILESTONE_STATUSES");
    expect(followUp).toContain("qms-followup-milestones");
  });
});
