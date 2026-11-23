import type { CARInviteOut } from "./qms";

export type CarInviteDraftForm = {
  submitted_by_name: string;
  submitted_by_email: string;
  containment_action: string;
  root_cause: string;
  corrective_action: string;
  evidence_ref: string;
  due_date: string;
  target_closure_date: string;
};

const fields: Array<keyof CarInviteDraftForm> = [
  "submitted_by_name", "submitted_by_email", "containment_action", "root_cause",
  "corrective_action", "evidence_ref", "due_date", "target_closure_date",
];
const key = (carId: string) => `amo.qms.cap-draft.${carId}`;
const combined = (first: unknown, second: unknown) => [...new Set([first, second].filter((value): value is string => typeof value === "string" && Boolean(value.trim())).map(value => value.trim()))].join("\n\n");
export function consolidateCarInviteForm(form: Record<string, string>): CarInviteDraftForm {
  const result = Object.fromEntries(fields.map(field => [field, form[field] || ""])) as CarInviteDraftForm;
  if (form.preventive_action?.trim()) result.corrective_action = combined(result.corrective_action, form.preventive_action);
  return result;
}
const revision = (invite: CARInviteOut) => JSON.stringify([
  invite.submitted_at, invite.root_cause_status, invite.capa_status,
  invite.containment_action, invite.root_cause, invite.corrective_action,
  invite.evidence_ref, invite.due_date, invite.target_closure_date,
]);

export function removeCarInviteDraft(carId: string): void {
  try { sessionStorage.removeItem(key(carId)); } catch { /* storage may be disabled */ }
}

export function readCarInviteDraft(invite: CARInviteOut): CarInviteDraftForm | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(key(invite.car_id)) || "null");
    if (!value) return null;
    // Preserve unfinished text saved by the former two-field form in this tab.
    if (value.form && "preventive_action" in value.form) {
      value.form.corrective_action = combined(value.form.corrective_action, value.form.preventive_action);
      delete value.form.preventive_action;
    }
    const previous = JSON.parse(value.revision);
    if (Array.isArray(previous) && previous.length === 10) {
      previous.splice(5, 2, typeof previous[6] === "string" && previous[6].trim() ? combined(previous[5], previous[6]) : previous[5]);
      value.revision = JSON.stringify(previous);
    }
    if (value.revision !== revision(invite) || !fields.every((field) => typeof value.form?.[field] === "string")) {
      removeCarInviteDraft(invite.car_id);
      return null;
    }
    return Object.fromEntries(fields.map((field) => [field, value.form[field]])) as CarInviteDraftForm;
  } catch { return null; }
}

export function saveCarInviteDraft(invite: CARInviteOut, form: CarInviteDraftForm): boolean {
  // Keep unfinished responses in this browser tab; invitation credentials and
  // declarations are never stored, and server revisions invalidate old drafts.
  try { sessionStorage.setItem(key(invite.car_id), JSON.stringify({ revision: revision(invite), form })); return true; } catch { return false; }
}
