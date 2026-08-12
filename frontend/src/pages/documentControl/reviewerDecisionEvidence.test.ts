import { describe, expect, it } from "vitest";

import type { DocumentDetailResponse, DocumentWorkflow } from "../../services/documentControl";
import {
  buildReviewerDecisionEvidence,
  parseAdditionalEvidenceReferences,
} from "./reviewerDecisionEvidence";

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

describe("reviewer decision evidence", () => {
  it("retains the exact reviewed revision and source checksum", () => {
    const { detail, workflow } = fixture();

    expect(buildReviewerDecisionEvidence(detail, workflow, "")).toEqual([
      {
        reference: "manual-revision:revision-2",
        checksum_sha256: "abc123",
      },
    ]);
  });

  it("preserves additional controlled evidence references without inventing asset IDs", () => {
    const { detail, workflow } = fixture();

    expect(buildReviewerDecisionEvidence(detail, workflow, "QMS-CHK-42\nATT-9001")).toEqual([
      {
        reference: "manual-revision:revision-2",
        checksum_sha256: "abc123",
      },
      { reference: "QMS-CHK-42" },
      { reference: "ATT-9001" },
    ]);
  });

  it("requires an entered retained reference when the reviewed source has no checksum", () => {
    const { detail, workflow } = fixture();
    detail.revisions[0].source_sha256 = null;

    expect(buildReviewerDecisionEvidence(detail, workflow, "")).toEqual([]);
    expect(parseAdditionalEvidenceReferences("CR-17")).toEqual([{ reference: "CR-17" }]);
  });
});
