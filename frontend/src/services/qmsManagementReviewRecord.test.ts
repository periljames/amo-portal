import { describe, expect, it } from "vitest";
import { managementReviewRecordText } from "./qmsManagementReviewRecord";
import type { ReviewRecord } from "./qmsManagementReview";

const record: ReviewRecord = { id: "review-1", title: "Quarterly review", status: "APPROVED", owner_user_id: "chair", due_date: "2026-11-18", version: 4,
  payload: { attendee_user_ids: ["chair", "peer"], decisions: [{ id: "decision-1", title: "Improve the control", rationale: "Evidence identified a gap" }], approval: { by: "chair", at: "2026-11-18T08:00:00Z", reason: "Minutes checked" } },
  actions: [{ id: "action-1", title: "Implement the control", status: "CLOSED", owner_user_id: "peer", due_date: "2026-12-01", version: 3,
    payload: { decision_id: "decision-1", completion_evidence: "Retained verification evidence", verification: { by: "chair", at: "2026-11-18T09:00:00Z", reason: "Independently checked" } } }],
};
describe("retained management review download", () => {
  it("includes attendance, action ownership, decisions and actual approval/verification provenance", () => {
    const text = managementReviewRecordText(record, [{ id: "chair", first_name: "Quality", last_name: "Chair", email: "chair@example.test" }, { id: "peer", first_name: "Action", last_name: "Owner", email: "peer@example.test" }]);
    expect(text).toContain("Attendees: Quality Chair (chair), Action Owner (peer)");
    expect(text).toContain("Owner: Action Owner (peer)");
    expect(text).toContain("Decision: Improve the control");
    expect(text).toContain("Reason: Minutes checked");
    expect(text).toContain("Verification: Quality Chair (chair) · 2026-11-18T09:00:00Z");
    expect(text).toContain("Retained verification evidence");
  });
  it("keeps unknown actor IDs and does not manufacture approval for legacy records", () => {
    const text = managementReviewRecordText({ ...record, payload: { attendee_user_ids: ["former-member"] }, actions: [] }, []);
    expect(text).toContain("Chair: chair");
    expect(text).toContain("Attendees: former-member");
    expect(text).toContain("APPROVAL\n\nNot recorded");
    expect(text).not.toContain("Minutes checked");
  });
});
