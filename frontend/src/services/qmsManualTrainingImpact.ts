import { apiRequest, qmsPath } from "./apiClient";

export type ManualTrainingImpactCourse = { id: string; code: string; title: string };
export type ManualTrainingImpactPerson = { id: string; name: string };
export type ManualTrainingRequirement = {
  id: string;
  immutable_source_sha256: string;
  rationale: string;
  requirement_id: string;
  course_id: string;
  user_id: string;
  required_by_date: string | null;
  is_active: boolean;
  is_mandatory: boolean;
  blocking: boolean;
  course_completion?: {
    course_record_id: string | null;
    course_record_state: "NO_ACTIVE_RECORD" | "VERIFIED_COURSE_RECORD" | "NOT_CURRENTLY_VERIFIED";
  };
};
export type ManualTrainingImpactResponse = {
  manual: { id: string; code: string; title: string };
  revision: {
    id: string;
    number: string;
    published_current: boolean;
    status: string;
    immutable_source_sha256: string | null;
    immutable_locked: boolean;
  };
  requirements: ManualTrainingRequirement[];
  acknowledgement: {
    assigned_count: number;
    acknowledged_count: number;
    pending_count: number;
    authority: "DOCUMENT_CONTROL";
  };
  training_authority: "TRAINING";
  warning: string;
};
export type ManualTrainingImpactAssignment = {
  course_id: string;
  target_user_ids: string[];
  required_by_date: string;
  mandatory: boolean;
  blocking: boolean;
  decision_basis: string;
};

function impactUrl(amoCode: string, manualId?: string, revisionId?: string, suffix = ""): string {
  const revisionPath = manualId && revisionId
    ? "/manuals/" + encodeURIComponent(manualId) + "/revisions/" + encodeURIComponent(revisionId)
    : "";
  return qmsPath(amoCode, "/manual-impact" + revisionPath + suffix);
}

export function listManualImpactCatalog(amoCode: string) {
  return apiRequest<{ courses: ManualTrainingImpactCourse[]; people: ManualTrainingImpactPerson[] }>(
    impactUrl(amoCode, undefined, undefined, "/catalog"), { cacheTtlMs: 0, timeoutMs: 15000 },
  );
}
export function readManualTrainingImpact(amoCode: string, manualId: string, revisionId: string) {
  return apiRequest<ManualTrainingImpactResponse>(
    impactUrl(amoCode, manualId, revisionId),
    { cacheTtlMs: 0, timeoutMs: 15000 },
  );
}
export function assignManualRevisionTraining(
  amoCode: string, manualId: string, revisionId: string,
  assignment: ManualTrainingImpactAssignment,
) {
  return apiRequest<{
    manual_id: string;
    revision_id: string;
    source_sha256: string;
    assignments: Array<{ training_requirement_id: string; user_id: string; link_id: string | null; existing_link: boolean }>;
    message: string;
  }>(impactUrl(amoCode, manualId, revisionId, "/assign"), {
    method: "POST", body: JSON.stringify(assignment), cacheTtlMs: 0, timeoutMs: 20000,
  });
}
