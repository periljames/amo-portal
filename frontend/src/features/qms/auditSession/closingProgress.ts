/**
 * Progressive disclosure helpers for Audit Closing.
 * Permission flags stay in the workspace; this only derives the current gate.
 */

export type ClosingRevisionStatus = "DRAFT" | "INTERNAL_REVIEW" | "APPROVED" | "ISSUED" | string;

export type ClosingProgressInput = {
  hasGeneratedDraft: boolean;
  activeRevisionStatus: ClosingRevisionStatus | null;
  hasAcknowledgement: boolean;
  hasSignature: boolean;
  hasIssuedRevision: boolean;
  executionClosed: boolean;
};

/** 1=freeze/generate … 7=assurance/verification */
export function resolveActiveClosingStep(input: ClosingProgressInput): number {
  if (!input.hasGeneratedDraft || !input.activeRevisionStatus) return 1;
  const status = input.activeRevisionStatus;
  if (status === "DRAFT" && !input.hasAcknowledgement) return 2;
  if (status === "DRAFT" || status === "INTERNAL_REVIEW") return 3;
  // Issued revision wins over an APPROVED active pointer still present after issue.
  if (input.hasIssuedRevision && !input.executionClosed) return 6;
  if (input.hasIssuedRevision && input.executionClosed) return 7;
  if (status === "APPROVED" && !input.hasSignature) return 4;
  if (status === "APPROVED" && input.hasSignature) return 5;
  return 7;
}

export function closingCardTone(step: number, activeStep: number): "current" | "complete" | "locked" {
  if (step === activeStep) return "current";
  if (step < activeStep) return "complete";
  return "locked";
}

export function closingLockedReason(step: number, activeStep: number): string | null {
  if (step <= activeStep) return null;
  if (activeStep === 1) return "Complete freeze and generate/adopt a closing draft first.";
  if (activeStep === 2) return "Awaiting auditee acknowledgement on the governed draft.";
  if (activeStep === 3) return "Complete Quality review/approval before this step unlocks.";
  if (activeStep === 4) return "Passkey approval of the exact approved report is required first.";
  if (activeStep === 5) return "Issue the passkey-approved report before this step unlocks.";
  if (activeStep === 6) return "Close execution before assurance/verification outputs.";
  return "Complete the preceding closing gate first.";
}

/** Mutating controls only on the current gate. */
export function closingStepAllowsActions(step: number, activeStep: number): boolean {
  return step === activeStep;
}
