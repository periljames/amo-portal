import type {
  DocumentDetailResponse,
  DocumentWorkflow,
} from "../../services/documentControl";

export type ReviewerDecisionEvidence = Record<string, string>;

export function parseAdditionalEvidenceReferences(value: string): ReviewerDecisionEvidence[] {
  return value
    .split(/[\n,;]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((reference) => ({ reference }));
}

export function buildReviewerDecisionEvidence(
  detail: DocumentDetailResponse,
  workflow: DocumentWorkflow,
  additionalReferences: string,
): ReviewerDecisionEvidence[] {
  const revision = detail.revisions.find((item) => item.id === workflow.revision_id);
  const checksum = revision?.source_sha256?.trim();
  const evidence: ReviewerDecisionEvidence[] = [];

  if (checksum) {
    evidence.push({
      reference: `manual-revision:${workflow.revision_id}`,
      checksum_sha256: checksum,
    });
  }

  evidence.push(...parseAdditionalEvidenceReferences(additionalReferences));
  return evidence;
}
