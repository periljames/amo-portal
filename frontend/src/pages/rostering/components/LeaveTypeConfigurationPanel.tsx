import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Save } from "lucide-react";

import { createLeaveType, listLeaveTypes, updateLeaveType } from "../../../services/workforce";
import type { AvailabilityType, LeaveTypeRead } from "../../../types/workforce";
import { errorMessage } from "../rosterUi";
import { EmptyState, RosterLoading, StatusPill } from "./RosterShell";

const AVAILABILITY: AvailabilityType[] = ["ANNUAL_LEAVE", "SICK_LEAVE", "COMPASSIONATE_LEAVE", "MATERNITY_LEAVE", "PATERNITY_LEAVE", "STUDY_LEAVE", "UNPAID_LEAVE", "OTHER"];
type Draft = Pick<LeaveTypeRead, "code" | "name" | "availability_type" | "eligible_gender" | "paid" | "deducts_balance" | "requires_attachment" | "supervisor_approval_required" | "hr_approval_required" | "allow_negative_balance" | "is_active" | "display_order"> & { description: string };
const blank: Draft = { code: "", name: "", availability_type: "OTHER", eligible_gender: "ALL", description: "", paid: true, deducts_balance: true, requires_attachment: false, supervisor_approval_required: true, hr_approval_required: true, allow_negative_balance: false, is_active: true, display_order: 100 };

export function LeaveTypeConfigurationPanel({ canManage }: { canManage: boolean }) {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["workforce", "leave-types", "configuration"], queryFn: () => listLeaveTypes(true) });
  const [editing, setEditing] = useState<LeaveTypeRead | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [draft, setDraft] = useState<Draft>(blank);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const start = (row?: LeaveTypeRead) => { setEditing(row || null); setDraft(row ? { ...row, description: row.description || "" } : blank); setEditorOpen(true); setFailure(null); };
  const save = async () => {
    if (!draft.code.trim() || !draft.name.trim()) return;
    setBusy(true); setFailure(null);
    try {
      if (editing) await updateLeaveType(editing.id, draft);
      else await createLeaveType({ ...draft, code: draft.code.trim().toUpperCase(), name: draft.name.trim() });
      await client.invalidateQueries({ queryKey: ["workforce", "leave-types"] });
      setEditing(null); setDraft(blank); setEditorOpen(false);
    } catch (cause) { setFailure(errorMessage(cause)); } finally { setBusy(false); }
  };
  if (query.isPending) return <RosterLoading label="Loading leave configuration…" />;
  return <section className="wr-panel rs-leave-config">
    <div className="wr-section-heading"><div><span className="wr-eyebrow">Policy configuration</span><h2>Leave types</h2><p>Changes made here apply immediately to employee requests. Gender eligibility is checked against each linked personnel profile.</p></div>{canManage ? <button className="wr-button wr-button--primary" type="button" onClick={() => start()}><Plus size={15} /> Add leave type</button> : null}</div>
    {failure || query.error ? <div className="wr-inline-error" role="alert">{failure || errorMessage(query.error)}</div> : null}
    <div className="rs-leave-list">{(query.data || []).map(row => <button type="button" key={row.id} onClick={() => canManage && start(row)}><span><strong>{row.name}</strong><small>{row.code} · {row.eligible_gender === "ALL" ? "All employees" : `${row.eligible_gender.toLowerCase()} employees`} · {row.supervisor_approval_required ? "Supervisor approval" : "No supervisor approval"}</small></span><StatusPill value={row.is_active ? "ACTIVE" : "INACTIVE"} /></button>)}</div>
    {!query.data?.length ? <EmptyState title="No leave types" description="Add the first leave type to enable leave requests." /> : null}
    {canManage && editorOpen ? <div className="rs-leave-editor">
      <div className="rs-form-grid"><label><span>Code</span><input value={draft.code} disabled={Boolean(editing)} onChange={e => setDraft({ ...draft, code: e.target.value })} /></label><label><span>Name</span><input value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })} /></label><label><span>Calendar category</span><select value={draft.availability_type} onChange={e => setDraft({ ...draft, availability_type: e.target.value as AvailabilityType })}>{AVAILABILITY.map(value => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select></label><label><span>Eligible gender</span><select value={draft.eligible_gender} onChange={e => setDraft({ ...draft, eligible_gender: e.target.value as Draft["eligible_gender"] })}><option value="ALL">All</option><option value="FEMALE">Female</option><option value="MALE">Male</option></select></label><label className="rs-form-grid__wide"><span>Description</span><input value={draft.description} onChange={e => setDraft({ ...draft, description: e.target.value })} /></label></div>
      <div className="rs-leave-checks">{([['paid','Paid'],['deducts_balance','Deduct balance'],['requires_attachment','Attachment required'],['supervisor_approval_required','Supervisor approval'],['hr_approval_required','Final HR approval'],['allow_negative_balance','Allow negative balance'],['is_active','Active']] as const).map(([key,label]) => <label key={key}><input type="checkbox" checked={draft[key]} onChange={e => setDraft({ ...draft, [key]: e.target.checked })} /> {label}</label>)}</div>
      <div className="wr-actions wr-actions--end"><button type="button" className="wr-button wr-button--secondary" onClick={() => { setEditing(null); setDraft(blank); setEditorOpen(false); }}>Cancel</button><button type="button" className="wr-button wr-button--primary" disabled={busy || !draft.code.trim() || !draft.name.trim()} onClick={() => void save()}><Save size={15} /> Save leave type</button></div>
    </div> : null}
  </section>;
}
