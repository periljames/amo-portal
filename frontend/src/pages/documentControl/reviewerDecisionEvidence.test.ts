import { describe, expect, it } from "vitest";

import type { DocumentDetailResponse, DocumentWorkflow } from "../../services/documentControl";
import type { DocumentEvidenceReference } from "../../services/documentControlEvidence";
import { buildReviewerDecisionEvidence } from "./reviewerDecisionEvidence";

function fixture() {
  const workflow = {
    id: "workflow-1",
    manual_id: "manual-1",
    revision_id: "revision-2",
    state: "TECHNICAL_REVIEW",
    requires_authority: false,
    training_impact_required: false,
    training_readiness_status: "NOT_REQUIRED",
    qms_readiness_status: "NOT_REQUIRED",
    distribution_readiness_status: "NOT_REQUIRED",
    version: 1,
  } as DocumentWorkflow;

  const detail = {
    revisions: [
      {
        id: "revision-2",
        manual_id: "manual-1",
        revision_number: "2",
        status: "DEPARTMENT_REVIEW",
        immutable: false,
        requires_authority_approval: false,
        source_sha256: "abc123",
      },
    ],
  } as DocumentDetailResponse;

  return { detail, workflow };
}

const asset: DocumentEvidenceReference = {
  asset_id: "asset-1",
  filename: "technical-review-checklist.pdf",
  mime_type: "application/pdf",
  sha256: "1".repeat(64),
  size_bytes: 1250,
  category: "REVIEW",
};

describe("reviewer decision evidence", () => {
  it("does not manufacture the reviewed revision checksum in the browser", () => {
    const { detail, workflow } = fixture();
    expect(buildReviewerDecisionEvidence(detail, workflow, [])).toEqual([]);
  });

  it("preserves only governed evidence assets selected from the DMS", () => {
    const { detail, workflow } = fixture();
    expect(buildReviewerDecisionEvidence(detail, workflow, [asset])).toEqual([asset]);
  });

  it("returns defensive copies rather than mutating the picker selection", () => {
    const { detail, workflow } = fixture();
    const result = buildReviewerDecisionEvidence(detail, workflow, [asset]);
    expect(result[0]).not.toBe(asset);
    expect(result[0]).toEqual(asset);
  });
});
