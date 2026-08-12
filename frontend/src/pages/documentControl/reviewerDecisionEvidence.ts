import type {
  DocumentDetailResponse,
  DocumentWorkflow,
} from "../../services/documentControl";
import type { DocumentEvidenceReference } from "../../services/documentControlEvidence";

export type ReviewerDecisionEvidence = DocumentEvidenceReference;

/**
 * Browser clients submit only governed evidence assets selected from the DMS.
 * The reviewed revision ID and source checksum are appended by the server from
 * authoritative revision data; the browser must never manufacture that evidence.
 */
export function buildReviewerDecisionEvidence(
  _detail: DocumentDetailResponse,
  _workflow: DocumentWorkflow,
  controlledAssets: DocumentEvidenceReference[],
): ReviewerDecisionEvidence[] {
  return controlledAssets.map((item) => ({ ...item }));
}
