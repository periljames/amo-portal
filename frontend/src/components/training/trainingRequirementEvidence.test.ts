import { describe, expect, it } from "vitest";

import type { TrainingFileRead } from "../../services/training";
import type { TrainingRecordRead } from "../../types/training";
import { resolveRecordEvidence } from "./trainingRequirementEvidence";

function file(partial: Partial<TrainingFileRead> & Pick<TrainingFileRead, "id" | "original_filename">): TrainingFileRead {
  return {
    amo_id: "amo-1",
    owner_user_id: "user-1",
    kind: "CERTIFICATE",
    storage_path: `/files/${partial.id}`,
    review_status: "APPROVED",
    uploaded_at: "2026-01-01T00:00:00Z",
    ...partial,
  };
}

function record(partial: Partial<TrainingRecordRead> & Pick<TrainingRecordRead, "id">): TrainingRecordRead {
  return {
    amo_id: "amo-1",
    user_id: "user-1",
    course_id: "course-1",
    completion_date: "2026-01-01",
    ...partial,
  };
}

describe("resolveRecordEvidence", () => {
  it("prefers the latest file linked by record_id", () => {
    const linked = file({ id: "file-linked", original_filename: "linked.pdf", record_id: "rec-1", uploaded_at: "2026-02-01T00:00:00Z" });
    const attachment = file({ id: "file-attach", original_filename: "attach.pdf" });
    const latestByRecordId = new Map([["rec-1", linked]]);
    const filesById = new Map([
      ["file-linked", linked],
      ["file-attach", attachment],
    ]);

    const result = resolveRecordEvidence(
      record({ id: "rec-1", attachment_file_id: "file-attach" }),
      latestByRecordId,
      filesById,
    );

    expect(result?.id).toBe("file-linked");
  });

  it("falls back to attachment_file_id when no record_id link exists", () => {
    const attachment = file({ id: "file-attach", original_filename: "cert.png", content_type: "image/png" });
    const result = resolveRecordEvidence(
      record({ id: "rec-2", attachment_file_id: "file-attach" }),
      new Map(),
      new Map([["file-attach", attachment]]),
    );

    expect(result?.id).toBe("file-attach");
  });

  it("returns null when neither link resolves", () => {
    expect(resolveRecordEvidence(record({ id: "rec-3" }), new Map(), new Map())).toBeNull();
    expect(resolveRecordEvidence(record({ id: "rec-3", attachment_file_id: "missing" }), new Map(), new Map())).toBeNull();
    expect(resolveRecordEvidence(null, new Map(), new Map())).toBeNull();
  });
});
