import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import QmsSectionTabs from "../../components/QMS/QmsSectionTabs";
import { hasQmsRolePermission } from "../../app/routeGuards";
import { getCachedUser } from "../../services/auth";
import { apiRequest, qmsPath } from "../../services/apiClient";
import { reviewRequest, type MeetingBody, type ReviewRecord, type ReviewList, type ReviewMember, type ReviewActionBody } from "../../services/qmsManagementReview";
import { managementReviewRecordText } from "../../services/qmsManagementReviewRecord";
import { classifyQmsPath, qmsModulePath } from "./routes/qmsRouteRegistry";
import "./qms-management-review.css";

const meetingTransitions: Record<string, [string, string][]> = {
  DRAFT: [["SCHEDULED", "Schedule review"], ["CANCELLED", "Cancel review"]],
  SCHEDULED: [["IN_PROGRESS", "Start review"], ["DRAFT", "Return to draft"], ["CANCELLED", "Cancel review"]],
  IN_PROGRESS: [["PENDING_APPROVAL", "Submit minutes for approval"], ["CANCELLED", "Cancel review"]],
  PENDING_APPROVAL: [["APPROVED", "Approve minutes & decisions"], ["IN_PROGRESS", "Return for revision"]],
  APPROVED: [["CLOSED", "Close review"]],
};
const actionTransitions: Record<string, [string, string][]> = {
  OPEN: [["IN_PROGRESS", "Start action"], ["CANCELLED", "Cancel action"]],
  IN_PROGRESS: [["PENDING_VERIFICATION", "Submit for verification"], ["CANCELLED", "Cancel action"]],
  PENDING_VERIFICATION: [["CLOSED", "Verify & close"], ["IN_PROGRESS", "Return for more work"]],
  CLOSED: [["IN_PROGRESS", "Reopen action"]],
};
const label = (value: string) => value.toLowerCase().replaceAll("_", " ");
const failure = (e: unknown) => e instanceof Error ? e.message : "The request failed. Your changes have not been saved; retry.";
const memberName = (m: ReviewMember) => `${m.first_name || ""} ${m.last_name || ""}`.trim() || m.email;
const dateLabel = (value?: string) => value ? new Date(`${value.slice(0, 10)}T12:00:00`).toLocaleDateString() : "Not dated";

export default function QmsManagementReviewPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const context = classifyQmsPath(location.pathname);
  const amoCode = context.amoCode || "";
  const parts = context.relativePath?.split("/").slice(1) || [];
  const view = parts[0] || "dashboard";
  const creating = view === "new" || (view === "meetings" && parts[1] === "new");
  const detailId = !creating && !["dashboard", "meetings", "actions", "open-actions", "closed-actions"].includes(view) ? view : "";
  const [revision, setRevision] = useState(0);
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [message, setMessage] = useState("");
  const canManage = hasQmsRolePermission("qms.management_review.manage");
  const root = qmsModulePath(amoCode, "management-review").replace(/\/dashboard$/, "");
  const linkedActionId = view.includes("actions") ? new URLSearchParams(location.search).get("record") : null;
  const linkedAction = useQuery({ queryKey: ["management-review-action-link", amoCode, linkedActionId], enabled: !!linkedActionId,
    queryFn: () => reviewRequest<ReviewRecord>(amoCode, `/actions/${encodeURIComponent(linkedActionId!)}`) });
  useEffect(() => {
    if (linkedAction.data?.payload.review_id) navigate(`${root}/${linkedAction.data.payload.review_id}/overview?action=${linkedAction.data.id}#action-${linkedAction.data.id}`, { replace: true });
  }, [linkedAction.data, root, navigate]);
  useEffect(() => { if (detailId && location.hash.startsWith("#action-")) document.getElementById(location.hash.slice(1))?.scrollIntoView({ block: "start" }); }, [detailId, location.hash, revision]);
  useEffect(() => {
    const reset = window.setTimeout(() => {
      setOffset(0);
      setQuery("");
      setMessage("");
    }, 0);
    return () => window.clearTimeout(reset);
  }, [location.pathname]);
  const members = useQuery({ queryKey: ["management-review-members", amoCode], queryFn: () => reviewRequest<{ items: ReviewMember[] }>(amoCode, "/members"), staleTime: 60_000 });
  const list = useQuery({ queryKey: ["management-reviews", amoCode, view, query, offset, revision], enabled: !detailId && !creating,
    queryFn: () => reviewRequest<ReviewList>(amoCode, `?${new URLSearchParams({ view, q: query, offset: String(offset) })}`) });
  const detail = useQuery({ queryKey: ["management-review", amoCode, detailId, revision], enabled: !!detailId,
    queryFn: () => reviewRequest<ReviewRecord>(amoCode, `/meetings/${encodeURIComponent(detailId)}`) });
  const briefing = useQuery({ queryKey: ["management-review-briefing", amoCode, revision], enabled: view === "dashboard",
    queryFn: () => apiRequest<{ generated_at: string; executive_summary: string[]; decisions_required: { title: string; count: number; path: string }[] }>(qmsPath(amoCode, "/excellence/management-review-pack"), { cacheTtlMs: 0 }) });
  function saved(text: string) { setMessage(text); setRevision(r => r + 1); }
  const rows = list.data?.items || [];
  const actionsView = view.includes("actions");
  const people = members.data?.items || [];
  const person = (id: string) => people.find(m => m.id === id) ? memberName(people.find(m => m.id === id)!) : "Former / unavailable member";
  return <DepartmentLayout amoCode={amoCode} activeDepartment="quality"><section className="qms-review" aria-label="Management review workspace">
    <header className="qms-review__heading"><div><h1>Management Review</h1><p>Review performance, retain decisions and verify follow-up to closure.</p></div>
      <div className="qms-review__buttons"><Link to={`${root}/meetings`}>All meetings</Link>{canManage && !creating && <Link className="qms-review__primary" to={`${root}/new`}>Plan a review</Link>}
      <button type="button" onClick={() => setRevision(r => r + 1)} disabled={list.isFetching || detail.isFetching}>Refresh</button></div></header>
    <QmsSectionTabs amoCode={amoCode} />
    {message && <p role="status" className="qms-review__success">{message}</p>}
    {linkedAction.isError && <p role="alert">{failure(linkedAction.error)} <button onClick={() => void linkedAction.refetch()}>Retry action link</button></p>}
    {members.isError && <p role="alert">Members could not be loaded. <button onClick={() => void members.refetch()}>Retry members</button></p>}
    {creating && (canManage ? <MeetingEditor members={people} disabled={members.isPending || members.isError} onSave={async body => {
      const row = await reviewRequest<ReviewRecord>(amoCode, "/meetings", body); navigate(`${root}/${row.id}/overview`); saved("Review created as a draft.");
    }} /> : <p role="alert">Management Review manage permission is required to create a meeting.</p>)}
    {(list.isPending && !creating && !detailId || detail.isPending && !!detailId) && <p role="status">Loading management review…</p>}
    {(list.isError && !creating && !detailId || detail.isError && !!detailId) && <div role="alert" className="qms-review__error">{failure(detailId ? detail.error : list.error)} <button onClick={() => setRevision(r => r + 1)}>Retry</button></div>}
    {detail.data && detailId && <MeetingDetail key={`${detail.data.id}:${detail.data.version}:${revision}`} row={detail.data} amoCode={amoCode} members={people} canManage={canManage} onSaved={saved} />}
    {!creating && !detailId && list.data && <>
      <section className="qms-review__stats" aria-label="Management review totals">{[
        ["Meetings", list.data.summary.meetings, "meetings"], ["Awaiting approval", list.data.summary.awaiting_approval, "meetings"],
        ["Open actions", list.data.summary.open_actions, "open-actions"], ["Overdue actions", list.data.summary.overdue_actions, "open-actions"],
      ].map(([name, count, destination]) => <Link key={name} to={`${root}/${destination}`}><strong>{count}</strong><span>{name}</span></Link>)}</section>
      {view === "dashboard" && <section className="qms-review__section"><h2>Current assurance briefing</h2><p>Live source records; review and record the relevant conclusions in your meeting inputs.</p>
        {briefing.isPending && <p role="status">Loading source briefing…</p>}{briefing.isError && <p role="alert">Briefing unavailable. <button onClick={() => void briefing.refetch()}>Retry briefing</button></p>}
        {briefing.data && <><small>Generated {new Date(briefing.data.generated_at).toLocaleString()}</small><ul>{briefing.data.executive_summary.map(line => <li key={line}>{line}</li>)}</ul>
          <div className="qms-review__buttons">{briefing.data.decisions_required.map(item => <Link key={item.title} to={item.path}>{item.title} ({item.count})</Link>)}</div></>}
      </section>}
      <section className="qms-review__section"><div className="qms-review__heading"><h2>{actionsView ? "Follow-up actions" : "Review meetings"}</h2><label>Search {actionsView ? "actions" : "meetings"}<input type="search" value={query} onChange={e => { setQuery(e.target.value); setOffset(0); }} /></label></div>
        {!rows.length ? <p>No {actionsView ? "actions" : "meetings"} match this view.{!actionsView && canManage && <> <Link to={`${root}/new`}>Plan the first review</Link>.</>}</p> : <div className="qms-review__table"><table><thead><tr><th>Title</th><th>{actionsView ? "Due" : "Meeting date"}</th><th>{actionsView ? "Owner" : "Chair"}</th><th>Status</th><th>Open</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}><td>{row.title}</td><td>{dateLabel(row.due_date)}</td><td>{person(row.owner_user_id)}</td><td><span className="qms-review__status">{label(row.status)}</span></td><td><Link to={`${root}/${actionsView ? row.payload.review_id : row.id}/overview${actionsView ? `?action=${encodeURIComponent(row.id)}#action-${row.id}` : ""}`}>{actionsView ? "Open action & meeting" : "Open meeting"}</Link></td></tr>)}</tbody></table></div>}
        {list.data.total > 30 && <nav aria-label="Management review pages"><button disabled={!offset} onClick={() => setOffset(offset - 30)}>Previous</button><span>{offset + 1}–{Math.min(offset + 30, list.data.total)} of {list.data.total}</span><button disabled={offset + 30 >= list.data.total} onClick={() => setOffset(offset + 30)}>Next</button></nav>}
      </section>
    </>}
  </section></DepartmentLayout>;
}

function MeetingEditor({ row, members, disabled = false, onSave }: { row?: ReviewRecord; members: ReviewMember[]; disabled?: boolean; onSave: (body: MeetingBody) => Promise<void> }) {
  const { search } = useLocation();
  const initial = new URLSearchParams(search);
  const [body, setBody] = useState<MeetingBody>(() => ({ title: row?.title || initial.get("title")?.slice(0, 255) || "", review_date: row?.due_date?.slice(0, 10) || initial.get("date") || "", chair_user_id: row?.owner_user_id || getCachedUser()?.id || "", attendee_user_ids: row?.payload.attendee_user_ids || [], agenda: row?.payload.agenda || "", inputs: row?.payload.inputs || [], minutes: row?.payload.minutes || "", decisions: row?.payload.decisions || [] }));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = <K extends keyof MeetingBody>(key: K, value: MeetingBody[K]) => setBody(p => ({ ...p, [key]: value }));
  return <form className="qms-review__section qms-review__form" onSubmit={async e => { e.preventDefault(); setBusy(true); setError(""); try { await onSave(body); } catch (cause) { setError(failure(cause)); } finally { setBusy(false); } }}>
    <h2>{row ? "Meeting record" : "Plan a management review"}</h2><p>Save preparation and minutes here. Scheduling, approval and closeout are separate recorded decisions.</p>
    <fieldset disabled={busy || disabled}><div className="qms-review__fields">
      <label>Review title<input required minLength={3} maxLength={255} value={body.title} onChange={e => set("title", e.target.value)} /></label>
      <label>Meeting date<input required type="date" value={body.review_date} onChange={e => set("review_date", e.target.value)} /></label>
      <label>Chair<select aria-label="Chair" required value={body.chair_user_id} onChange={e => set("chair_user_id", e.target.value)}><option value="">Choose chair</option>{members.map(m => <option key={m.id} value={m.id}>{memberName(m)}</option>)}</select></label>
      <label>Attendees<select multiple value={body.attendee_user_ids} onChange={e => set("attendee_user_ids", Array.from(e.target.selectedOptions, o => o.value))}>{members.map(m => <option key={m.id} value={m.id}>{memberName(m)}</option>)}</select><small>Select all attendees using Ctrl / Command or Shift.</small></label>
    </div><label>Agenda<textarea rows={4} maxLength={24000} value={body.agenda} onChange={e => set("agenda", e.target.value)} placeholder="Previous actions, audit results, feedback, process performance, risks, resources and opportunities" /></label>
    <h3>Review inputs</h3><p>Retain the evidence considered and its source. Add the relevant performance, feedback, audit, risk and resource inputs.</p>
    {body.inputs.map((input, index) => <fieldset key={index} className="qms-review__item"><legend>Input {index + 1}</legend>
      <label>Input topic<input required minLength={2} maxLength={150} value={input.topic} onChange={e => set("inputs", body.inputs.map((v, i) => i === index ? { ...v, topic: e.target.value } : v))} /></label>
      <label>Input summary<textarea required minLength={2} maxLength={12000} value={input.summary} onChange={e => set("inputs", body.inputs.map((v, i) => i === index ? { ...v, summary: e.target.value } : v))} /></label>
      <label>Source reference<input maxLength={1000} value={input.source_reference} onChange={e => set("inputs", body.inputs.map((v, i) => i === index ? { ...v, source_reference: e.target.value } : v))} /></label>
      <button type="button" onClick={() => set("inputs", body.inputs.filter((_, i) => i !== index))}>Remove input {index + 1}</button>
    </fieldset>)}<button type="button" onClick={() => set("inputs", [...body.inputs, { topic: "", summary: "", source_reference: "" }])}>Add review input</button>
    <label>Minutes<textarea rows={7} maxLength={48000} value={body.minutes} onChange={e => set("minutes", e.target.value)} placeholder="Discussion, conclusions on QMS suitability and effectiveness, resource needs and agreed improvements" /></label>
    <h3>Decisions</h3>{body.decisions.map((decision, index) => <fieldset className="qms-review__item" key={decision.id}><legend>Decision {index + 1}</legend>
      <label>Decision title<input required minLength={3} maxLength={255} value={decision.title} onChange={e => set("decisions", body.decisions.map((v, i) => i === index ? { ...v, title: e.target.value } : v))} /></label>
      <label>Decision rationale<textarea required minLength={3} maxLength={12000} value={decision.rationale} onChange={e => set("decisions", body.decisions.map((v, i) => i === index ? { ...v, rationale: e.target.value } : v))} /></label>
      <button type="button" disabled={row?.actions?.some(a => a.payload.decision_id === decision.id)} onClick={() => set("decisions", body.decisions.filter((_, i) => i !== index))}>Remove decision {index + 1}</button>
    </fieldset>)}<button type="button" onClick={() => set("decisions", [...body.decisions, { id: crypto.randomUUID(), title: "", rationale: "" }])}>Add decision</button>
    <div className="qms-review__buttons"><button className="qms-review__primary" type="submit">{busy ? "Saving…" : row ? "Save meeting record" : "Create draft review"}</button></div></fieldset>
    {error && <p role="alert" className="qms-review__error">{error}</p>}
  </form>;
}

function TransitionButtons({ row, actions, onTransition }: { row: ReviewRecord; actions: Record<string, [string, string][]>; onTransition: (target: string, reason: string) => Promise<void> }) {
  const [reason, setReason] = useState(""); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  if (!actions[row.status]?.length) return null;
  return <div className="qms-review__transition"><label>Decision / transition reason<input value={reason} minLength={3} maxLength={4000} onChange={e => setReason(e.target.value)} placeholder="Record why this step is appropriate" /></label>
    <div className="qms-review__buttons">{actions[row.status].map(([target, title]) => <button key={target} disabled={busy || reason.trim().length < 3} onClick={async () => { setBusy(true); setError(""); try { await onTransition(target, reason.trim()); } catch (cause) { setError(failure(cause)); } finally { setBusy(false); } }}>{busy ? "Working…" : title}</button>)}</div>{error && <p role="alert">{error}</p>}
  </div>;
}

function MeetingDetail({ row, amoCode, members, canManage, onSaved }: { row: ReviewRecord; amoCode: string; members: ReviewMember[]; canManage: boolean; onSaved: (message: string) => void }) {
  const { hash } = useLocation();
  useEffect(() => { if (hash.startsWith("#action-")) document.getElementById(hash.slice(1))?.scrollIntoView({ block: "start" }); }, [hash, row.id]);
  const editable = canManage && ["DRAFT", "SCHEDULED", "IN_PROGRESS"].includes(row.status);
  const active = !["CLOSED", "CANCELLED"].includes(row.status);
  const p = row.payload;
  const person = (id: string) => { const member = members.find(value => value.id === id); return member ? memberName(member) : id; };
  function download() {
    const text = managementReviewRecordText(row, members);
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" })); const a = document.createElement("a"); a.href = url; a.download = `management-review-${row.id}.txt`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <>
    <section className="qms-review__section"><div className="qms-review__heading"><div><h2>{row.title}</h2><p>{dateLabel(row.due_date)} · <span className="qms-review__status">{label(row.status)}</span> · Version {row.version}</p></div><button onClick={download}>Download meeting record</button></div>
      <p className="qms-review__prose">Chair: {person(row.owner_user_id)}<br />Attendees: {(p.attendee_user_ids || []).map(person).join(", ") || "Not recorded"}</p>
      <p>Workflow: draft → scheduled → in progress → minutes approval → approved → closed after follow-up.</p>
      {canManage && <TransitionButtons row={row} actions={meetingTransitions} onTransition={async (status, reason) => { await reviewRequest(amoCode, `/meetings/${row.id}/transition`, { status, reason, expected_version: row.version }); onSaved(`Review is now ${label(status)}.`); }} />}
    </section>
    {editable ? <MeetingEditor row={row} members={members} disabled={!members.length} onSave={async body => { await reviewRequest(amoCode, `/meetings/${row.id}`, { ...body, expected_version: row.version }, "PUT"); onSaved("Meeting record saved."); }} /> : <section className="qms-review__section"><h2>Retained meeting record</h2><h3>Agenda</h3><p className="qms-review__prose">{p.agenda || "Not recorded"}</p><h3>Inputs considered</h3>{p.inputs?.map((v, i) => <article key={i}><h4>{v.topic}</h4><p className="qms-review__prose">{v.summary}</p><small>{v.source_reference}</small></article>)}<h3>Minutes</h3><p className="qms-review__prose">{p.minutes || "Not recorded"}</p><h3>Decisions</h3>{p.decisions?.map(d => <article key={d.id}><h4>{d.title}</h4><p className="qms-review__prose">{d.rationale}</p></article>)}{p.approval && <p>Approved {new Date(p.approval.at).toLocaleString()} · {p.approval.reason}</p>}</section>}
    <section className="qms-review__section"><h2>Decision follow-up</h2><p>Assign each action to a decision, an active owner and a due date. Completion evidence is required before verification.</p>
      {(row.actions || []).map(action => <ActionEditor key={`${action.id}:${action.version}`} action={action} meeting={row} members={members} canManage={canManage && active} amoCode={amoCode} onSaved={onSaved} />)}
      {!row.actions?.length && <p>No follow-up actions have been assigned.</p>}
      {canManage && active && Boolean(p.decisions?.length) && <ActionEditor meeting={row} members={members} canManage amoCode={amoCode} onSaved={onSaved} />}
      {canManage && active && !p.decisions?.length && <p>Save a meeting decision above before assigning follow-up.</p>}
    </section>
    <section className="qms-review__section"><h2>Review history</h2><ol>{p.history?.map((h, i) => <li key={i}>{new Date(h.at).toLocaleString()} · {label(h.event)} · {members.find(m => m.id === h.by) ? memberName(members.find(m => m.id === h.by)!) : h.by}{h.reason && <p className="qms-review__prose">{h.reason}</p>}</li>)}</ol></section>
  </>;
}

function ActionEditor({ action, meeting, members, canManage, amoCode, onSaved }: { action?: ReviewRecord; meeting: ReviewRecord; members: ReviewMember[]; canManage: boolean; amoCode: string; onSaved: (message: string) => void }) {
  const [body, setBody] = useState<ReviewActionBody & { completion_evidence: string }>(() => ({ title: action?.title || "", description: action?.description || "", owner_user_id: action?.owner_user_id || "", due_date: action?.due_date?.slice(0, 10) || "", decision_id: action?.payload.decision_id || meeting.payload.decisions?.[0]?.id || "", completion_evidence: action?.payload.completion_evidence || "" }));
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const editable = canManage && (!action || !["CLOSED", "CANCELLED"].includes(action.status));
  const set = (key: keyof typeof body, value: string) => setBody(p => ({ ...p, [key]: value }));
  return <article className="qms-review__item" id={action ? `action-${action.id}` : undefined}>
    <h3>{action ? action.title : "Assign follow-up action"}{action && <> · <span className="qms-review__status">{label(action.status)}</span></>}</h3>
    {editable ? <form className="qms-review__form" onSubmit={async e => { e.preventDefault(); setBusy(true); setError(""); try {
      if (action) await reviewRequest(amoCode, `/actions/${action.id}`, { ...body, expected_version: action.version }, "PUT");
      else { const { completion_evidence: _, ...create } = body; void _; await reviewRequest(amoCode, `/meetings/${meeting.id}/actions`, create); }
      onSaved(action ? "Action updated." : "Follow-up action assigned.");
    } catch (cause) { setError(failure(cause)); } finally { setBusy(false); } }}><fieldset disabled={busy || !members.length}>
      <div className="qms-review__fields"><label>Action title<input required minLength={3} maxLength={255} value={body.title} onChange={e => set("title", e.target.value)} /></label>
      <label>Action owner<select aria-label="Action owner" required value={body.owner_user_id} onChange={e => set("owner_user_id", e.target.value)}><option value="">Choose owner</option>{members.map(m => <option key={m.id} value={m.id}>{memberName(m)}</option>)}</select></label>
      <label>Action due date<input required type="date" value={body.due_date} onChange={e => set("due_date", e.target.value)} /></label>
      <label>Related decision<select required value={body.decision_id} onChange={e => set("decision_id", e.target.value)}>{meeting.payload.decisions?.map(d => <option key={d.id} value={d.id}>{d.title}</option>)}</select></label></div>
      <label>Action description<textarea maxLength={12000} value={body.description} onChange={e => set("description", e.target.value)} /></label>
      {action && <label>Completion evidence<textarea maxLength={12000} value={body.completion_evidence} onChange={e => set("completion_evidence", e.target.value)} placeholder="What was done, objective evidence references and results" /></label>}
      <button type="submit">{busy ? "Saving…" : action ? "Save action" : "Assign action"}</button>
    </fieldset>{error && <p role="alert">{error}</p>}</form> : <><p>{action?.description}</p><p>Owner: {members.find(m => m.id === action?.owner_user_id) ? memberName(members.find(m => m.id === action?.owner_user_id)!) : "Unavailable member"} · Due {dateLabel(action?.due_date)}</p><p className="qms-review__prose">{action?.payload.completion_evidence || "No completion evidence recorded."}</p></>}
    {action && canManage && <TransitionButtons row={action} actions={actionTransitions} onTransition={async (status, reason) => { await reviewRequest(amoCode, `/actions/${action.id}/transition`, { status, reason, expected_version: action.version }); onSaved(`Action is now ${label(status)}.`); }} />}
  </article>;
}
