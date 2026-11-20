import type { ReviewMember, ReviewPayload, ReviewRecord } from "./qmsManagementReview";

/** Export the retained record, including accountability; never infer approval. */
export function managementReviewRecordText(row: ReviewRecord, members: ReviewMember[]): string {
  const person = (id?: string) => {
    const member = members.find(item => item.id === id);
    const name = member ? `${member.first_name || ""} ${member.last_name || ""}`.trim() || member.email : "";
    return name ? `${name} (${id})` : id || "Not recorded";
  };
  const decision = (value: ReviewPayload["approval"]) => value ? `${person(value.by)} · ${value.at}\nReason: ${value.reason}` : "Not recorded";
  const history = (value: ReviewPayload) => (value.history || []).map(event => `${event.at} · ${event.event} · ${person(event.by)}${event.reason ? `\nReason: ${event.reason}` : ""}`);
  const p = row.payload;
  return [row.title, `Record: ${row.id} · Version: ${row.version}`,
    `Date: ${row.due_date} · Status: ${row.status}`, `Chair: ${person(row.owner_user_id)}`,
    `Attendees: ${(p.attendee_user_ids || []).map(person).join(", ") || "Not recorded"}`,
    "APPROVAL", decision(p.approval), "AGENDA", p.agenda || "Not recorded",
    "INPUTS", ...(p.inputs || []).map(value => `${value.topic}\n${value.summary}\nSource: ${value.source_reference}`),
    "MINUTES", p.minutes || "Not recorded", "DECISIONS",
    ...(p.decisions || []).map(value => `${value.id} · ${value.title}\n${value.rationale}`),
    "ACTIONS", ...(row.actions || []).flatMap(action => [
      `${action.id} · ${action.title} · ${action.status} · Due ${action.due_date}`,
      `Owner: ${person(action.owner_user_id)}`,
      `Decision: ${p.decisions?.find(value => value.id === action.payload.decision_id)?.title || action.payload.decision_id || "Not recorded"}`,
      action.description || "", `Evidence: ${action.payload.completion_evidence || "Not recorded"}`,
      `Verification: ${decision(action.payload.verification)}`, ...history(action.payload),
    ]), "REVIEW HISTORY", ...history(p),
  ].join("\n\n");
}
