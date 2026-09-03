import { describe, expect, it } from "vitest";
import {
  closingCardTone,
  closingLockedReason,
  closingStepAllowsActions,
  resolveActiveClosingStep,
  type ClosingProgressInput,
} from "./closingProgress";

/** Permission flags remain in the workspace; tests document the authoritative shapes. */
function permissionFlags(input: {
  canManage: boolean;
  activeStatus: string | null;
  currentSignature: boolean;
  issuedRevision: boolean;
  executionClosed: boolean;
  executionReady: boolean;
  supplementaryPolicy: boolean;
  currentAssuranceArtifact: boolean;
}) {
  const canApprove =
    input.canManage && input.activeStatus === "INTERNAL_REVIEW";
  const canSign =
    input.canManage && input.activeStatus === "APPROVED" && !input.currentSignature;
  const canIssue =
    input.canManage && input.activeStatus === "APPROVED" && input.currentSignature;
  const canExecutionClose =
    input.canManage &&
    input.issuedRevision &&
    input.currentSignature &&
    !input.executionClosed &&
    input.executionReady;
  const canGenerateAssurance =
    input.canManage &&
    input.supplementaryPolicy &&
    input.currentSignature &&
    input.issuedRevision &&
    !input.currentAssuranceArtifact;
  return { canApprove, canSign, canIssue, canExecutionClose, canGenerateAssurance };
}

function tonesForActive(active: number) {
  return [1, 2, 3, 4, 5, 6, 7].map((step) => ({
    step,
    tone: closingCardTone(step, active),
    locked: closingLockedReason(step, active),
    allows: closingStepAllowsActions(step, active),
  }));
}

function assertSevenStageMatrix(active: number) {
  const rows = tonesForActive(active);
  expect(rows).toHaveLength(7);
  for (const row of rows) {
    if (row.step < active) {
      expect(row.tone).toBe("complete");
      expect(row.locked).toBeNull();
      expect(row.allows).toBe(false);
    } else if (row.step === active) {
      expect(row.tone).toBe("current");
      expect(row.locked).toBeNull();
      expect(row.allows).toBe(true);
    } else {
      expect(row.tone).toBe("locked");
      expect(row.locked).toBeTruthy();
      expect(typeof row.locked).toBe("string");
      expect(row.allows).toBe(false);
    }
  }
  // Future stages stay visible (matrix covers all 7) but only current allows actions.
  expect(rows.filter((r) => r.allows)).toHaveLength(1);
  expect(rows.find((r) => r.allows)?.step).toBe(active);
}

const base: ClosingProgressInput = {
  hasGeneratedDraft: false,
  activeRevisionStatus: null,
  hasAcknowledgement: false,
  hasSignature: false,
  hasIssuedRevision: false,
  executionClosed: false,
};

describe("closing progressive disclosure", () => {
  it("initial freeze/generate: stage 1 current; 2–7 locked with prerequisites", () => {
    const active = resolveActiveClosingStep(base);
    expect(active).toBe(1);
    assertSevenStageMatrix(1);
    expect(closingLockedReason(2, 1)).toMatch(/freeze|draft/i);
    expect(closingStepAllowsActions(7, 1)).toBe(false);
  });

  it("auditee acknowledgement pending: stage 2 current; later stages locked", () => {
    const active = resolveActiveClosingStep({
      ...base,
      hasGeneratedDraft: true,
      activeRevisionStatus: "DRAFT",
      hasAcknowledgement: false,
    });
    expect(active).toBe(2);
    assertSevenStageMatrix(2);
    expect(closingLockedReason(3, active)).toMatch(/acknowledgement/i);
    expect(closingStepAllowsActions(1, active)).toBe(false);
    expect(closingCardTone(1, active)).toBe("complete");
  });

  it("draft acknowledged opens Quality review (stage 3)", () => {
    const active = resolveActiveClosingStep({
      ...base,
      hasGeneratedDraft: true,
      activeRevisionStatus: "DRAFT",
      hasAcknowledgement: true,
    });
    expect(active).toBe(3);
    assertSevenStageMatrix(3);
  });

  it("internal review keeps stage 3 current and actionable", () => {
    const active = resolveActiveClosingStep({
      ...base,
      hasGeneratedDraft: true,
      activeRevisionStatus: "INTERNAL_REVIEW",
      hasAcknowledgement: true,
    });
    expect(active).toBe(3);
    assertSevenStageMatrix(3);
    expect(closingStepAllowsActions(4, active)).toBe(false);
  });

  it("approved but unsigned: passkey stage 4; issue/close/assurance locked", () => {
    const active = resolveActiveClosingStep({
      ...base,
      hasGeneratedDraft: true,
      activeRevisionStatus: "APPROVED",
      hasAcknowledgement: true,
      hasSignature: false,
    });
    expect(active).toBe(4);
    assertSevenStageMatrix(4);
    expect(closingLockedReason(5, active)).toMatch(/passkey|approved/i);
    expect(closingStepAllowsActions(5, active)).toBe(false);
  });

  it("approved and signed: issue stage 5 current", () => {
    const active = resolveActiveClosingStep({
      ...base,
      hasGeneratedDraft: true,
      activeRevisionStatus: "APPROVED",
      hasAcknowledgement: true,
      hasSignature: true,
    });
    expect(active).toBe(5);
    assertSevenStageMatrix(5);
    expect(closingStepAllowsActions(6, active)).toBe(false);
  });

  it("issued with execution open: stage 6 current", () => {
    const active = resolveActiveClosingStep({
      ...base,
      hasGeneratedDraft: true,
      activeRevisionStatus: "APPROVED",
      hasAcknowledgement: true,
      hasSignature: true,
      hasIssuedRevision: true,
      executionClosed: false,
    });
    expect(active).toBe(6);
    assertSevenStageMatrix(6);
    expect(closingLockedReason(7, active)).toMatch(/execution|assurance/i);
  });

  it("execution closed: assurance stage 7 current; completed stages readable", () => {
    const active = resolveActiveClosingStep({
      ...base,
      hasGeneratedDraft: true,
      activeRevisionStatus: "APPROVED",
      hasAcknowledgement: true,
      hasSignature: true,
      hasIssuedRevision: true,
      executionClosed: true,
    });
    expect(active).toBe(7);
    assertSevenStageMatrix(7);
    expect(closingCardTone(6, active)).toBe("complete");
    expect(closingStepAllowsActions(7, active)).toBe(true);
    expect(closingStepAllowsActions(6, active)).toBe(false);
  });

  it("stepAllowsActions is exclusive to the active gate for every stage", () => {
    for (let active = 1; active <= 7; active += 1) {
      for (let step = 1; step <= 7; step += 1) {
        expect(closingStepAllowsActions(step, active)).toBe(step === active);
      }
    }
  });

  it("step 7 mutation gate requires stepAllowsActions(7)", () => {
    expect(closingStepAllowsActions(7, 6)).toBe(false);
    expect(closingStepAllowsActions(7, 7)).toBe(true);
    // Workspace disables mutate controls when !stepAllowsActions(7) even if permission flags allow.
    const flags = permissionFlags({
      canManage: true,
      activeStatus: "APPROVED",
      currentSignature: true,
      issuedRevision: true,
      executionClosed: true,
      executionReady: true,
      supplementaryPolicy: true,
      currentAssuranceArtifact: false,
    });
    expect(flags.canGenerateAssurance).toBe(true);
    const mutateEnabled = flags.canGenerateAssurance && closingStepAllowsActions(7, 7);
    const mutateBlockedByStage = flags.canGenerateAssurance && !closingStepAllowsActions(7, 6);
    expect(mutateEnabled).toBe(true);
    expect(mutateBlockedByStage).toBe(true);
  });
});

describe("closing permission flags (authoritative shapes; not a stage machine)", () => {
  it("canApprove only when manage + INTERNAL_REVIEW", () => {
    expect(
      permissionFlags({
        canManage: true,
        activeStatus: "INTERNAL_REVIEW",
        currentSignature: false,
        issuedRevision: false,
        executionClosed: false,
        executionReady: false,
        supplementaryPolicy: false,
        currentAssuranceArtifact: false,
      }).canApprove,
    ).toBe(true);
    expect(
      permissionFlags({
        canManage: true,
        activeStatus: "APPROVED",
        currentSignature: false,
        issuedRevision: false,
        executionClosed: false,
        executionReady: false,
        supplementaryPolicy: false,
        currentAssuranceArtifact: false,
      }).canApprove,
    ).toBe(false);
  });

  it("canSign only when manage + APPROVED + no signature", () => {
    expect(
      permissionFlags({
        canManage: true,
        activeStatus: "APPROVED",
        currentSignature: false,
        issuedRevision: false,
        executionClosed: false,
        executionReady: false,
        supplementaryPolicy: false,
        currentAssuranceArtifact: false,
      }).canSign,
    ).toBe(true);
    expect(
      permissionFlags({
        canManage: true,
        activeStatus: "APPROVED",
        currentSignature: true,
        issuedRevision: false,
        executionClosed: false,
        executionReady: false,
        supplementaryPolicy: false,
        currentAssuranceArtifact: false,
      }).canSign,
    ).toBe(false);
  });

  it("canIssue only when manage + APPROVED + signature", () => {
    expect(
      permissionFlags({
        canManage: true,
        activeStatus: "APPROVED",
        currentSignature: true,
        issuedRevision: false,
        executionClosed: false,
        executionReady: false,
        supplementaryPolicy: false,
        currentAssuranceArtifact: false,
      }).canIssue,
    ).toBe(true);
  });

  it("canExecutionClose requires issued + signature + not closed + readiness", () => {
    expect(
      permissionFlags({
        canManage: true,
        activeStatus: "APPROVED",
        currentSignature: true,
        issuedRevision: true,
        executionClosed: false,
        executionReady: true,
        supplementaryPolicy: false,
        currentAssuranceArtifact: false,
      }).canExecutionClose,
    ).toBe(true);
    expect(
      permissionFlags({
        canManage: true,
        activeStatus: "APPROVED",
        currentSignature: true,
        issuedRevision: true,
        executionClosed: false,
        executionReady: false,
        supplementaryPolicy: false,
        currentAssuranceArtifact: false,
      }).canExecutionClose,
    ).toBe(false);
  });

  it("canGenerateAssurance is conditional on supplementary policy and no existing artifact", () => {
    expect(
      permissionFlags({
        canManage: true,
        activeStatus: "APPROVED",
        currentSignature: true,
        issuedRevision: true,
        executionClosed: true,
        executionReady: true,
        supplementaryPolicy: true,
        currentAssuranceArtifact: false,
      }).canGenerateAssurance,
    ).toBe(true);
    expect(
      permissionFlags({
        canManage: true,
        activeStatus: "APPROVED",
        currentSignature: true,
        issuedRevision: true,
        executionClosed: true,
        executionReady: true,
        supplementaryPolicy: false,
        currentAssuranceArtifact: false,
      }).canGenerateAssurance,
    ).toBe(false);
    expect(
      permissionFlags({
        canManage: true,
        activeStatus: "APPROVED",
        currentSignature: true,
        issuedRevision: true,
        executionClosed: true,
        executionReady: true,
        supplementaryPolicy: true,
        currentAssuranceArtifact: true,
      }).canGenerateAssurance,
    ).toBe(false);
  });
});
