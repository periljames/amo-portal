import { useMemo, useState, type FormEvent } from "react";
import { CalendarClock, CheckCircle2, Plus } from "lucide-react";

import {
  completeDocumentReview,
  createDocumentReview,
  type DocumentDetailResponse,
  type PersonSummary,
} from "../../services/documentControl";
import { DocumentControlEmpty } from "./DocumentControlShell";


type DetailWithPeople = DocumentDetailResponse & { active_users?: PersonSummary[] };

function statementsFrom(value: string): string[] {
  return value.split(/[\n;]+/).map((item) => item.trim()).filter(Boolean);
}

function personLabel(person: PersonSummary): string {
  return `${person.name || person.email} · ${person.role}${person.department ? ` · ${person.department}` : ""}`;
}

export default function DocumentControlReviewActions({
  detail,
  tenant,
  onChanged,
}: {
  detail: DocumentDetailResponse;
  tenant: string;
  onChanged: () => void;
}) {
  const activeUsers = useMemo(
    () => ((detail as DetailWithPeople).active_users || []).filter((person) => person.active),
    [detail],
  );
  const userById = useMemo(() => new Map(activeUsers.map((person) => [person.id, person])), [activeUsers]);
  const openReviews = useMemo(() => detail.reviews.filter((review) => review.status !== "COMPLETED"), [detail.reviews]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [ownerId, setOwnerId] = useState("");
  const [selectedId, setSelectedId] = useState(openReviews[0]?.id || "");
  const [outcome, setOutcome] = useState("CONTINUE");
  const [findingText, setFindingText] = useState("");
  const [actionText, setActionText] = useState("");

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await action();
      onChanged();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The periodic review action failed.");
    } finally {
      setBusy(false);
    }
  };

  const create = (event: FormEvent) => {
    event.preventDefault();
    if (!dueAt || !ownerId || !detail.document.current_published_revision_id) return;
    void run(() => createDocumentReview(tenant, {
      manual_id: detail.document.id,
      revision_id: detail.document.current_published_revision_id,
      owner_user_id: ownerId,
      due_at: new Date(dueAt).toISOString(),
    }));
  };

  const complete = () => {
    if (!selectedId) return;
    const findings = statementsFrom(findingText).map((value) => ({ finding: value }));
    const actions = statementsFrom(actionText).map((value) => ({ action: value }));
    if (outcome !== "CONTINUE" && (!findings.length || !actions.length)) {
      setError("A non-continuation outcome requires at least one finding and one resulting action.");
      return;
    }
    void run(() => completeDocumentReview(tenant, selectedId, { outcome, findings, actions }));
  };

  const directoryError = activeUsers.length ? "" : "No active tenant user is available to own this periodic review.";
  const publishedError = detail.document.current_published_revision_id ? "" : "A current published revision is required before scheduling a periodic review.";

  return <div className="dc-grid">
    <form className="dc-form" onSubmit={create}>
      <div className="dc-callout"><CalendarClock size={17} /><div><strong>Schedule accountable periodic review</strong><div>Assign the review to a named active tenant user. The server binds it to the current effective revision and prevents duplicate open reviews.</div></div></div>
      <label><span>Review due</span><input type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} required /></label>
      <label><span>Review owner</span><select value={ownerId} onChange={(event) => setOwnerId(event.target.value)} required><option value="">Select active tenant user</option>{activeUsers.map((person) => <option key={person.id} value={person.id}>{personLabel(person)}</option>)}</select></label>
      {error || directoryError || publishedError ? <div className="dc-form__error">{error || directoryError || publishedError}</div> : null}
      <div className="dc-form__actions"><button type="submit" className="dc-button" disabled={busy || !dueAt || !ownerId || Boolean(directoryError) || Boolean(publishedError)}><Plus size={14} /> Schedule review</button></div>
    </form>

    {openReviews.length ? <div className="dc-form">
      <label className="wide"><span>Review to complete</span><select value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>{openReviews.map((row) => { const owner = row.owner_user_id ? userById.get(row.owner_user_id) : undefined; return <option key={row.id} value={row.id}>{row.due_at} · {owner ? personLabel(owner) : "Owner unavailable"} · {row.status}</option>; })}</select></label>
      <label><span>Outcome</span><select value={outcome} onChange={(event) => setOutcome(event.target.value)}><option>CONTINUE</option><option>CHANGE_REQUIRED</option><option>WITHDRAW</option><option>SUPERSEDE</option></select></label>
      <label className="wide"><span>Findings</span><textarea value={findingText} onChange={(event) => setFindingText(event.target.value)} placeholder="Required for change, withdrawal or supersession; one finding per line" /></label>
      <label className="wide"><span>Resulting actions</span><textarea value={actionText} onChange={(event) => setActionText(event.target.value)} placeholder="Required for change, withdrawal or supersession; one action per line" /></label>
      <div className="dc-callout"><CheckCircle2 size={16} /><div><strong>Completion creates follow-up automatically.</strong><div>When the outcome is not CONTINUE, the backend creates the linked Document Control change request from the retained findings and actions.</div></div></div>
      {error ? <div className="dc-form__error">{error}</div> : null}
      <div className="dc-form__actions"><button type="button" className="dc-button dc-button--primary" disabled={busy || !selectedId} onClick={complete}><CheckCircle2 size={14} /> Complete periodic review</button></div>
    </div> : <DocumentControlEmpty title="No open review" message="Schedule the next periodic applicability review and assign a named owner." />}
  </div>;
}
