import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useSearchParams, useParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getCachedUser } from "../../services/auth";
import {
  addReviewItem, completeReviewAction, createReviewMeeting,
  listReviewMeetings, listReviewParticipants, listReviewSources,
  readReviewMeeting, transitionReview, verifyReviewAction,
  type ReviewDetail, type ReviewMeeting, type ReviewParticipant,
  type ReviewSource, type ReviewSourceType,
} from "../../services/qmsManagementReview";
import "./qms-management-review.css";

type Action = () => Promise<unknown>;
const sourceTypes: ReviewSourceType[] = ["AUDIT", "CAR", "RISK", "SUPPLIER", "EQUIPMENT", "TRAINING"];

function toMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The operation could not be completed. Refresh and retry.";
}
function lines(value: string): string[] {
  return value.split("\n").map((line) => line.trim()).filter(Boolean);
}
function groupTitle(name: string): string {
  return name.replaceAll("_", " ").replace(/\b\w/g, (match) => match.toUpperCase());
}
function ReviewRecordGroup({ title, items }: { title: string; items: ReviewDetail[keyof Omit<ReviewDetail, "meeting">] }) {
  return <section className="qms-review__records" aria-label={title}>
    <h3>{title} <small>({items.length})</small></h3>
    {items.length === 0 ? <p>Not recorded.</p> : <div className="qms-review__record-list">
      {items.map((item) => <article key={item.id}>
        <strong>{item.title}</strong><span>{item.status}</span>
        <p>{item.description}</p>
        {item.owner_user_id ? <small>Owner ID: {item.owner_user_id}</small> : null}
        {item.due_date ? <small>Due {item.due_date}</small> : null}
        {item.payload.source_type ? <small>Source: {item.payload.source_type} · {item.payload.source_id}</small> : null}
      </article>)}
    </div>}
  </section>;
}

export default function QmsManagementReviewWorkflowPage() {
  const { amoCode = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const meetingId = searchParams.get("meeting") || "";
  const userId = getCachedUser()?.id || "";
  const [page, setPage] = useState(0);
  const [meetings, setMeetings] = useState<ReviewMeeting[]>([]);
  const [total, setTotal] = useState(0);
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [participants, setParticipants] = useState<ReviewParticipant[]>([]);
  const [sources, setSources] = useState<ReviewSource[]>([]);
  const [sourceType, setSourceType] = useState<ReviewSourceType>("AUDIT");
  const [selectedSource, setSelectedSource] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [newPurpose, setNewPurpose] = useState("");
  const [newDate, setNewDate] = useState("");
  const [newAgenda, setNewAgenda] = useState("");
  const [attendees, setAttendees] = useState<string[]>([]);
  const [inputTitle, setInputTitle] = useState("");
  const [inputSummary, setInputSummary] = useState("");
  const [minutes, setMinutes] = useState("");
  const [decisionTitle, setDecisionTitle] = useState("");
  const [decisionRationale, setDecisionRationale] = useState("");
  const [actionRequired, setActionRequired] = useState(false);
  const [actionTitle, setActionTitle] = useState("");
  const [actionDescription, setActionDescription] = useState("");
  const [actionOwner, setActionOwner] = useState("");
  const [actionDue, setActionDue] = useState("");
  const [decisionId, setDecisionId] = useState("");
  const [rationale, setRationale] = useState("");
  const [evidence, setEvidence] = useState("");
  const [implementation, setImplementation] = useState("");
  const [verification, setVerification] = useState("");

  const refresh = useCallback(async () => {
    if (!amoCode) return;
    const [list, people, selected] = await Promise.all([
      listReviewMeetings(amoCode, page * 25),
      listReviewParticipants(amoCode),
      meetingId ? readReviewMeeting(amoCode, meetingId) : Promise.resolve(null),
    ]);
    setMeetings(list.items);
    setTotal(list.total);
    setParticipants(people.items);
    setDetail(selected);
  }, [amoCode, meetingId, page]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    refresh().catch((error: unknown) => {
      if (active) setError(toMessage(error));
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [refresh]);

  useEffect(() => {
    let active = true;
    setSelectedSource("");
    setSources([]);
    if (!amoCode) return;
    listReviewSources(amoCode, sourceType)
      .then((result) => { if (active) setSources(result.items); })
      .catch((error: unknown) => { if (active) setError(toMessage(error)); });
    return () => { active = false; };
  }, [amoCode, sourceType]);

  const run = async (action: Action, result = "The governed record has been updated.") => {
    if (busy) return;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await action();
      await refresh();
      setSuccess(result);
    } catch (error) {
      setError(toMessage(error));
    } finally {
      setBusy(false);
    }
  };

  const selectMeeting = (id: string) => {
    setError("");
    setSuccess("");
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous);
      if (id) next.set("meeting", id);
      else next.delete("meeting");
      return next;
    });
  };
  const create = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void run(async () => {
      const result = await createReviewMeeting(amoCode, {
        title: newTitle.trim(), purpose: newPurpose.trim(),
        meeting_date: newDate, agenda: lines(newAgenda), attendees,
      });
      selectMeeting(result.meeting.id);
      setNewTitle(""); setNewPurpose(""); setNewDate(""); setNewAgenda(""); setAttendees([]);
    }, "Meeting draft created. Source-backed inputs, minutes and decisions are required before submission.");
  };
  const add = (kind: "inputs" | "minutes" | "decisions" | "actions", body: Record<string, unknown>) => {
    if (!detail) return;
    const version = detail.meeting.payload.version;
    void run(() => addReviewItem(amoCode, detail.meeting.id, kind, {
      expected_version: version, ...body,
    }), groupTitle(kind) + " recorded.");
  };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!detail) return;
    void run(() => transitionReview(
      amoCode, detail.meeting.id, "submit", detail.meeting.payload.version, rationale.trim(),
    ), "Submitted for independent approval.");
  };
  const reviewTransition = (name: "approve" | "close") => {
    if (!detail) return;
    void run(() => transitionReview(
      amoCode, detail.meeting.id, name, detail.meeting.payload.version, rationale.trim(),
    ), name === "approve" ? "Approved by the responsible reviewer." : "Review closed with verified actions.");
  };
  const meeting = detail?.meeting;
  const editable = meeting?.status === "DRAFT";
  const approved = meeting?.status === "APPROVED";
  const pending = meeting?.status === "PENDING_APPROVAL";
  const selectableDecisions = (detail?.decisions || []).filter((item) => item.payload.action_required);
  const canApprove = pending && meeting?.created_by !== userId;
  const allVerified = detail?.actions.every((action) => action.status === "VERIFIED") ?? false;

  return <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
    <main className="qms-review">
      <header className="qms-review__header">
        <div><p>QUALITY GOVERNANCE</p><h1>Management Review</h1>
          <span>Source-backed inputs, accountable decisions and independently verified actions.</span>
        </div>
        {meetingId ? <button type="button" onClick={() => selectMeeting("")}>Back to meetings</button> : null}
      </header>
      {error ? <div role="alert" className="qms-review__error"><strong>Action could not be completed.</strong> {error} <button type="button" disabled={busy} onClick={() => void run(async () => {}, "Refreshed from server.")}>Refresh</button></div> : null}
      {success ? <p role="status" className="qms-review__success">{success}</p> : null}
      {loading ? <p role="status">Loading current management review records…</p> : null}
      <div className="qms-review__grid">
        <section className="qms-review__panel">
          <h2>Meetings <small>{total}</small></h2>
          <div className="qms-review__meeting-list">
            {meetings.map((item) => <button key={item.id} type="button"
              aria-current={meetingId === item.id ? "true" : undefined}
              onClick={() => selectMeeting(item.id)} className={meetingId === item.id ? "selected" : ""}>
              <strong>{item.title}</strong><small>{item.payload.meeting_date || "Date not entered"} · {item.status}</small>
            </button>)}
            {!meetings.length && !loading ? <p>No accessible management review meetings.</p> : null}
          </div>
          <div className="qms-review__pager">
            <button type="button" disabled={page === 0 || busy} onClick={() => setPage((value) => Math.max(0, value - 1))}>Previous</button>
            <span>{total ? page * 25 + 1 : 0}–{Math.min((page + 1) * 25, total)} of {total}</span>
            <button type="button" disabled={page * 25 + 25 >= total || busy} onClick={() => setPage((value) => value + 1)}>Next</button>
          </div>
          <form className="qms-review__form" onSubmit={create}>
            <h3>Schedule a meeting</h3>
            <label>Meeting title<input required minLength={4} maxLength={255} value={newTitle} onChange={(e) => setNewTitle(e.target.value)} /></label>
            <label>Date<input required type="date" value={newDate} onChange={(e) => setNewDate(e.target.value)} /></label>
            <label>Purpose<textarea required minLength={8} value={newPurpose} onChange={(e) => setNewPurpose(e.target.value)} /></label>
            <label>Agenda (one item per line)<textarea required value={newAgenda} onChange={(e) => setNewAgenda(e.target.value)} /></label>
            <fieldset><legend>Invited participants (at least one)</legend>
              <div className="qms-review__participant-list">{participants.map((person) =>
                <label key={person.id}><input type="checkbox" checked={attendees.includes(person.id)}
                  onChange={(e) => setAttendees((values) => e.target.checked ? [...values, person.id] : values.filter((value) => value !== person.id))} />
                  {person.name} <small>{person.position}</small></label>
              )}</div>
            </fieldset>
            <button type="submit" disabled={busy || attendees.length === 0 || lines(newAgenda).length === 0}>Create governed draft</button>
          </form>
        </section>
        <section className="qms-review__detail" aria-label="Management review details">
          {!detail ? <div className="qms-review__panel"><h2>Select a meeting</h2><p>Open an existing meeting or schedule a new draft to record agenda, inputs, decisions and evidence.</p></div> : <>
            <div className="qms-review__panel">
              <div className="qms-review__detail-heading"><div><h2>{meeting?.title}</h2>
                <p>{meeting?.payload.meeting_date} · {meeting?.status} · Version {meeting?.payload.version}</p></div>
              </div>
              <p>{meeting?.description}</p>
              <h3>Approved agenda</h3><ol>{meeting?.payload.agenda.map((item, index) => <li key={index}>{item}</li>)}</ol>
              <p>Participants: {meeting?.payload.attendees.map((id) => participants.find((person) => person.id === id)?.name || id).join(", ")}</p>
            </div>
            <div className="qms-review__record-grid">
              <ReviewRecordGroup title="Source-backed inputs" items={detail.inputs} />
              <ReviewRecordGroup title="Minutes" items={detail.minutes} />
              <ReviewRecordGroup title="Decisions" items={detail.decisions} />
              <ReviewRecordGroup title="Assigned actions" items={detail.actions} />
              <ReviewRecordGroup title="Approval evidence" items={detail.approvals} />
            </div>
            {editable ? <div className="qms-review__panel qms-review__forms">
              <form className="qms-review__form" onSubmit={(event) => { event.preventDefault(); add("inputs", {
                title: inputTitle.trim(), summary: inputSummary.trim(), source_type: sourceType, source_id: selectedSource,
              }); }}>
                <h3>Add source-backed input</h3>
                <label>Source category<select value={sourceType} onChange={(event) => setSourceType(event.target.value as ReviewSourceType)}>
                  {sourceTypes.map((kind) => <option key={kind} value={kind}>{kind}</option>)}
                </select></label>
                <label>Verified source record<select required value={selectedSource} onChange={(event) => setSelectedSource(event.target.value)}>
                  <option value="">Choose an accessible source</option>
                  {sources.map((source) => <option key={source.id} value={source.id}>{source.label}</option>)}
                </select></label>
                <label>Input title<input minLength={4} required value={inputTitle} onChange={(event) => setInputTitle(event.target.value)} /></label>
                <label>Analysis and source relevance<textarea minLength={8} required value={inputSummary} onChange={(event) => setInputSummary(event.target.value)} /></label>
                <button type="submit" disabled={busy || !selectedSource}>Record source input</button>
              </form>
              <form className="qms-review__form" onSubmit={(event) => { event.preventDefault(); add("minutes", { description: minutes.trim() }); }}>
                <h3>Record minutes</h3>
                <label>Discussion and conclusions<textarea minLength={12} required value={minutes} onChange={(event) => setMinutes(event.target.value)} /></label>
                <button type="submit" disabled={busy}>Retain minutes</button>
              </form>
              <form className="qms-review__form" onSubmit={(event) => { event.preventDefault(); add("decisions", {
                title: decisionTitle.trim(), rationale: decisionRationale.trim(), action_required: actionRequired,
              }); }}>
                <h3>Record decision</h3>
                <label>Decision<input minLength={4} required value={decisionTitle} onChange={(event) => setDecisionTitle(event.target.value)} /></label>
                <label>Reasoned basis<textarea minLength={8} required value={decisionRationale} onChange={(event) => setDecisionRationale(event.target.value)} /></label>
                <label className="qms-review__check"><input type="checkbox" checked={actionRequired} onChange={(event) => setActionRequired(event.target.checked)} /> Requires an accountable action</label>
                <button type="submit" disabled={busy}>Record decision</button>
              </form>
              <form className="qms-review__form" onSubmit={(event) => { event.preventDefault(); add("actions", {
                title: actionTitle.trim(), description: actionDescription.trim(),
                owner_user_id: actionOwner, due_date: actionDue, decision_id: decisionId,
              }); }}>
                <h3>Assign follow-up action</h3>
                <label>Decision requiring action<select required value={decisionId} onChange={(event) => setDecisionId(event.target.value)}>
                  <option value="">Choose decision</option>
                  {selectableDecisions.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
                </select></label>
                <label>Action title<input minLength={4} required value={actionTitle} onChange={(event) => setActionTitle(event.target.value)} /></label>
                <label>Instructions<textarea minLength={8} required value={actionDescription} onChange={(event) => setActionDescription(event.target.value)} /></label>
                <label>Accountable owner<select required value={actionOwner} onChange={(event) => setActionOwner(event.target.value)}>
                  <option value="">Choose owner</option>
                  {participants.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}
                </select></label>
                <label>Due date<input type="date" required value={actionDue} onChange={(event) => setActionDue(event.target.value)} /></label>
                <button type="submit" disabled={busy || !decisionId || !actionOwner}>Assign action</button>
              </form>
            </div> : null}
            {approved ? <div className="qms-review__panel">
              <h3>Implementation and independent verification</h3>
              <label>Implementation statement<textarea value={implementation} onChange={(event) => setImplementation(event.target.value)} /></label>
              <label>Evidence record IDs (one per line)<textarea value={evidence} onChange={(event) => setEvidence(event.target.value)} /></label>
              <label>Verification decision / reason<textarea value={verification} onChange={(event) => setVerification(event.target.value)} /></label>
              {detail.actions.map((item) => <div className="qms-review__action" key={item.id}>
                <strong>{item.title}</strong><span>{item.status} · Owner {participants.find((person) => person.id === item.owner_user_id)?.name || item.owner_user_id}</span>
                {item.owner_user_id === userId && ["ASSIGNED", "REWORK"].includes(item.status)
                  ? <button type="button" disabled={busy || implementation.trim().length < 8 || lines(evidence).length === 0}
                    onClick={() => void run(() => completeReviewAction(amoCode, meetingId, item.id, lines(evidence), implementation.trim()))}>Submit implementation evidence</button> : null}
                {item.owner_user_id !== userId && item.status === "AWAITING_VERIFICATION" ? <>
                  <button type="button" disabled={busy || verification.trim().length < 8}
                    onClick={() => void run(() => verifyReviewAction(amoCode, meetingId, item.id, true, verification.trim()))}>Verify as effective</button>
                  <button type="button" disabled={busy || verification.trim().length < 8}
                    onClick={() => void run(() => verifyReviewAction(amoCode, meetingId, item.id, false, verification.trim()))}>Reject for rework</button>
                </> : null}
              </div>)}
            </div> : null}
            {editable || pending || approved ? <form className="qms-review__panel qms-review__form" onSubmit={submit}>
              <h3>Governed decision</h3>
              <label>Reason / approval notes<textarea minLength={8} required value={rationale} onChange={(event) => setRationale(event.target.value)} /></label>
              {editable ? <button type="submit" disabled={busy || rationale.trim().length < 8 || !detail.inputs.length || !detail.minutes.length || !detail.decisions.length}>Submit for approval</button> : null}
              {canApprove ? <button type="button" disabled={busy || rationale.trim().length < 8} onClick={() => reviewTransition("approve")}>Approve independently</button> : null}
              {pending && !canApprove ? <p>An independent authorised reviewer must approve this meeting.</p> : null}
              {approved ? <button type="button" disabled={busy || !allVerified || rationale.trim().length < 8} onClick={() => reviewTransition("close")}>Close with verified action evidence</button> : null}
            </form> : null}
          </>}
        </section>
      </div>
    </main>
  </DepartmentLayout>;
}
