// src/services/qmsManagementReview.ts
import { apiRequest, qmsPath } from "./apiClient";
import type { QmsListResponse } from "../types/qms";

export function getQmsManagementReview(amoCode: string): Promise<QmsListResponse> {
  return apiRequest<QmsListResponse>(qmsPath(amoCode, "/management-review"));
}


/** Canonical governed management review; generic register writes are deliberately denied. */
export type ReviewMeeting = {
  id: string;
  title: string;
  description: string | null;
  status: "DRAFT" | "PENDING_APPROVAL" | "APPROVED" | "CLOSED";
  created_by: string;
  created_at: string;
  payload: { version: number; meeting_date: string; agenda: string[]; attendees: string[]; purpose: string };
};
export type ReviewItem = {
  id: string;
  title: string;
  description: string;
  status: string;
  created_at: string;
  owner_user_id?: string | null;
  due_date?: string | null;
  payload: {
    meeting_id: string; decision_id?: string; source_type?: string; source_id?: string;
    action_required?: boolean; implementation_evidence?: string[];
    implemented_by?: string; verification_reason?: string; verified_by?: string;
  };
};
export type ReviewDetail = {
  meeting: ReviewMeeting;
  inputs: ReviewItem[];
  minutes: ReviewItem[];
  decisions: ReviewItem[];
  actions: ReviewItem[];
  approvals: ReviewItem[];
};
export type ReviewParticipant = { id: string; name: string; position: string };
export type ReviewSource = { id: string; label: string };
export type ReviewSourceType = "AUDIT" | "CAR" | "RISK" | "SUPPLIER" | "EQUIPMENT" | "TRAINING";
export type ReviewTransition = "submit" | "approve" | "close";

function reviewEndpoint(amoCode: string, suffix: string): string {
  return qmsPath(amoCode, "/management-review" + suffix);
}
function reviewPost<T>(amoCode: string, suffix: string, payload: Record<string, unknown>): Promise<T> {
  return apiRequest<T>(reviewEndpoint(amoCode, suffix), {
    method: "POST", body: JSON.stringify(payload), cacheTtlMs: 0, timeoutMs: 20000,
  });
}
function itemEndpoint(meetingId: string, suffix = ""): string {
  return "/meetings/" + encodeURIComponent(meetingId) + suffix;
}

export function listReviewMeetings(amoCode: string, offset = 0) {
  return apiRequest<{ items: ReviewMeeting[]; total: number; limit: number; offset: number }>(
    reviewEndpoint(amoCode, "/meetings?limit=25&offset=" + offset), { cacheTtlMs: 0 }
  );
}
export function listReviewParticipants(amoCode: string) {
  return apiRequest<{ items: ReviewParticipant[] }>(reviewEndpoint(amoCode, "/participants"), { cacheTtlMs: 30000 });
}
export function listReviewSources(amoCode: string, sourceType: ReviewSourceType, search = "") {
  return apiRequest<{ items: ReviewSource[] }>(
    reviewEndpoint(amoCode, "/sources?source_type=" + encodeURIComponent(sourceType) + "&q=" + encodeURIComponent(search)),
    { cacheTtlMs: 10000 }
  );
}
export function readReviewMeeting(amoCode: string, meetingId: string) {
  return apiRequest<ReviewDetail>(reviewEndpoint(amoCode, itemEndpoint(meetingId)), { cacheTtlMs: 0 });
}
export function createReviewMeeting(amoCode: string, fields: {
  title: string; meeting_date: string; agenda: string[]; attendees: string[]; purpose: string;
}) {
  return reviewPost<{ meeting: ReviewMeeting }>(amoCode, "/meetings", fields);
}
export function addReviewItem(
  amoCode: string, meetingId: string, kind: "inputs" | "minutes" | "decisions" | "actions",
  fields: Record<string, unknown>
) {
  return reviewPost<{ item: ReviewItem; meeting_version: number }>(amoCode, itemEndpoint(meetingId, "/" + kind), fields);
}
export function transitionReview(
  amoCode: string, meetingId: string, action: ReviewTransition, expectedVersion: number, rationale: string,
) {
  return reviewPost<{ meeting: ReviewMeeting }>(
    amoCode, itemEndpoint(meetingId, "/" + action), { expected_version: expectedVersion, rationale },
  );
}
export function completeReviewAction(
  amoCode: string, meetingId: string, actionId: string, evidence: string[], statement: string,
) {
  return reviewPost<{ action_id: string; status: string }>(
    amoCode, itemEndpoint(meetingId, "/actions/" + encodeURIComponent(actionId) + "/complete"),
    { evidence_references: evidence, statement },
  );
}
export function verifyReviewAction(
  amoCode: string, meetingId: string, actionId: string, accepted: boolean, reason: string,
) {
  return reviewPost<{ action_id: string; status: string }>(
    amoCode, itemEndpoint(meetingId, "/actions/" + encodeURIComponent(actionId) + "/verify"),
    { accepted, reason },
  );
}
