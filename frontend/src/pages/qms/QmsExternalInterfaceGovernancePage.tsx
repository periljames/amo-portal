import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getCachedUser } from "../../services/auth";
import {
  addExternalCommitment, approveExternalResponse, closeExternalRecord, completeExternalCommitment,
  createExternalRecord, draftExternalResponse, listExternalOwners, listExternalRecords,
  readExternalRecord, submitExternalResponse, verifyExternalCommitment,
  type ExternalDetail, type ExternalKind, type ExternalRecord,
} from "../../services/qmsExternal";
import "./qms-management-review.css";

const kinds: ExternalKind[] = ["REGULATOR", "CUSTOMER", "AUTHORITY"];
function records(value: string) {
  return value.split("\n").map((item) => item.trim()).filter(Boolean);
}
function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "The controlled external action failed.";
}
export default function QmsExternalInterfaceGovernancePage() {
  const { amoCode = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const kind: ExternalKind = kinds.includes(params.get("kind") as ExternalKind)
    ? params.get("kind") as ExternalKind : "REGULATOR";
  const recordId = params.get("id") || "";
  const userId = getCachedUser()?.id || "";
  const [list, setList] = useState<ExternalRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [detail, setDetail] = useState<ExternalDetail | null>(null);
  const [people, setPeople] = useState<Array<{ id: string; name: string }>>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [reference, setReference] = useState("");
  const [receivedOn, setReceivedOn] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [owner, setOwner] = useState("");
  const [responseTitle, setResponseTitle] = useState("");
  const [responseText, setResponseText] = useState("");
  const [evidence, setEvidence] = useState("");
  const [approvalReason, setApprovalReason] = useState("");
  const [submitDate, setSubmitDate] = useState("");
  const [submitMethod, setSubmitMethod] = useState("");
  const [submissionRef, setSubmissionRef] = useState("");
  const [commitmentTitle, setCommitmentTitle] = useState("");
  const [commitmentDetails, setCommitmentDetails] = useState("");
  const [commitmentOwner, setCommitmentOwner] = useState("");
  const [commitmentDue, setCommitmentDue] = useState("");
  const [implementation, setImplementation] = useState("");
  const [verification, setVerification] = useState("");
  const [closeReason, setCloseReason] = useState("");

  const refresh = useCallback(async () => {
    if (!amoCode) return;
    const [rows, participants, selected] = await Promise.all([
      listExternalRecords(amoCode, kind, offset),
      listExternalOwners(amoCode),
      recordId ? readExternalRecord(amoCode, kind, recordId) : Promise.resolve(null),
    ]);
    setList(rows.items); setTotal(rows.total); setPeople(participants.items); setDetail(selected);
  }, [amoCode, kind, offset, recordId]);
  useEffect(() => {
    let active = true;
    setLoading(true); setError("");
    refresh().catch((failure) => { if (active) setError(errorMessage(failure)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [refresh]);
  const act = async (fn: () => Promise<unknown>, notice: string) => {
    if (busy) return;
    setBusy(true); setError(""); setSuccess("");
    try {
      await fn(); await refresh(); setSuccess(notice);
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(false); }
  };
  const choose = (nextKind: ExternalKind, id = "") => {
    setOffset(0);
    setParams((previous) => {
      const next = new URLSearchParams(previous);
      next.set("kind", nextKind);
      if (id) next.set("id", id); else next.delete("id");
      return next;
    });
  };
  const create = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void act(async () => {
      const result = await createExternalRecord(amoCode, {
        kind, title: title.trim(), description: description.trim(),
        source_reference: reference.trim(), received_on: receivedOn,
        response_due: dueDate, owner_user_id: owner,
      });
      choose(kind, result.record.id);
      setTitle(""); setDescription(""); setReference("");
    }, "External issue received with an accountable owner and due date.");
  };
  const row = detail?.record;
  const version = row?.payload.version || 0;
  const draftResponses = detail?.responses.filter((item) => item.status === "DRAFT") || [];
  const currentDraft = draftResponses.find((item) => item.id === row?.payload.last_response_id);
  const approvedResponse = detail?.responses.find((item) => item.id === row?.payload.approved_response_id);
  const openCommitments = (detail?.commitments || []).filter((item) => item.status !== "CLOSED");
  const hasSubmittedProof = Boolean(detail?.responses.some((item) => item.status === "SUBMITTED"));

  return <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
    <main className="qms-review">
      <header className="qms-review__header"><div><p>CONTROLLED EXTERNAL COMMUNICATION</p>
        <h1>Regulator and Customer Interface</h1><span>Receipt, approved response, submission evidence and governed commitments.</span>
      </div></header>
      {error ? <div className="qms-review__error" role="alert">{error} <button type="button" disabled={busy} onClick={() => void refresh()}>Reload</button></div> : null}
      {success ? <p className="qms-review__success" role="status">{success}</p> : null}
      <div className="qms-review__grid"><div>
        <section className="qms-review__panel"><h2>External records</h2>
          <div className="qms-review__pager">{kinds.map((nextKind) =>
            <button key={nextKind} type="button" aria-pressed={kind === nextKind} onClick={() => choose(nextKind)}>{nextKind}</button>)}</div>
          {loading ? <p role="status">Loading tenant records…</p> : null}
          <div className="qms-review__meeting-list">{list.map((item) => <button key={item.id} type="button"
            className={item.id === recordId ? "selected" : ""} aria-current={item.id === recordId ? "true" : undefined}
            onClick={() => choose(kind, item.id)}><strong>{item.title}</strong>
              <small>{item.status} · Due {item.due_date || "Not recorded"}</small></button>)}</div>
          <div className="qms-review__pager">
            <button type="button" disabled={offset === 0 || busy} onClick={() => setOffset(Math.max(0, offset - 25))}>Previous</button>
            <span>{total ? offset + 1 : 0}–{Math.min(total, offset + 25)} of {total}</span>
            <button type="button" disabled={offset + 25 >= total || busy} onClick={() => setOffset(offset + 25)}>Next</button>
          </div>
        </section>
        <form className="qms-review__panel qms-review__form" onSubmit={create}>
          <h3>Record incoming {kind.toLowerCase()} item</h3>
          <label>Title<input required minLength={4} value={title} onChange={(e) => setTitle(e.target.value)} /></label>
          <label>Received description<textarea minLength={12} required value={description} onChange={(e) => setDescription(e.target.value)} /></label>
          <label>Sender reference<input required minLength={2} value={reference} onChange={(e) => setReference(e.target.value)} /></label>
          <label>Date received<input type="date" required value={receivedOn} onChange={(e) => setReceivedOn(e.target.value)} /></label>
          <label>Response due<input type="date" required value={dueDate} onChange={(e) => setDueDate(e.target.value)} /></label>
          <label>Accountable owner<select required value={owner} onChange={(e) => setOwner(e.target.value)}>
            <option value="">Choose person</option>
            {people.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}
          </select></label>
          <button type="submit" disabled={busy || !owner}>Register governed item</button>
        </form>
      </div>
      {!row ? <section className="qms-review__panel">Select an external issue to review its correspondence and commitments.</section> :
      <section aria-label="Governed external issue">
        <div className="qms-review__panel"><h2>{row.title}</h2>
          <p>{row.description}</p><p>Reference: {row.payload.source_reference} · Received {row.payload.received_on}</p>
          <p><strong>{row.status}</strong> · Version {version} · Owner {people.find((person) => person.id === row.owner_user_id)?.name || row.owner_user_id}</p>
        </div>
        <div className="qms-review__record-grid">
          <section className="qms-review__records"><h3>Response versions ({detail?.responses.length})</h3>
            {detail?.responses.map((item) => <article key={item.id}><strong>{item.title} · {item.status}</strong>
              <p>{item.description}</p><small>Author {item.created_by}</small>
              {item.payload.submission_evidence_ids ? <small>Submission evidence: {item.payload.submission_evidence_ids.join(", ")}</small> : null}
            </article>)}</section>
          <section className="qms-review__records"><h3>Commitments ({detail?.commitments.length})</h3>
            {detail?.commitments.map((item) => <article key={item.id}><strong>{item.title} · {item.status}</strong>
              <p>{item.description}</p><small>Due {item.due_date || "Unspecified"}</small>
            </article>)}</section>
        </div>
        {["RECEIVED", "RESPONSE_DRAFT"].includes(row.status) ? <form className="qms-review__panel qms-review__form" onSubmit={(event) => {
          event.preventDefault(); void act(() => draftExternalResponse(amoCode, kind, row.id, {
            expected_version: version, title: responseTitle.trim(),
            response_text: responseText.trim(), supporting_evidence_ids: records(evidence),
          }), "Draft response retained. Independent approval is still required.");
        }}>
          <h3>Prepare controlled response</h3>
          <label>Response title<input minLength={4} required value={responseTitle} onChange={(e) => setResponseTitle(e.target.value)} /></label>
          <label>Response text<textarea minLength={30} required value={responseText} onChange={(e) => setResponseText(e.target.value)} /></label>
          <label>Supporting evidence IDs (optional)<textarea value={evidence} onChange={(e) => setEvidence(e.target.value)} /></label>
          <button type="submit" disabled={busy}>Save response for approval</button>
        </form> : null}
        {row.status === "RESPONSE_DRAFT" && currentDraft ? <form className="qms-review__panel qms-review__form" onSubmit={(event) => {
          event.preventDefault(); void act(() => approveExternalResponse(amoCode, kind, row.id, {
            expected_version: version, response_id: currentDraft.id, rationale: approvalReason.trim(),
          }), "Independently approved response. No message has been sent by this portal.");
        }}>
          <h3>Independent correspondence approval</h3>
          <p>Draft {currentDraft.title} · Prepared by {currentDraft.created_by}</p>
          <label>Approval rationale<textarea required minLength={12} value={approvalReason} onChange={(e) => setApprovalReason(e.target.value)} /></label>
          <button type="submit" disabled={busy || currentDraft.created_by === userId}>Approve draft</button>
          {currentDraft.created_by === userId ? <p>An independent authorised reviewer must approve this response.</p> : null}
        </form> : null}
        {row.status === "RESPONSE_APPROVED" && approvedResponse ? <form className="qms-review__panel qms-review__form" onSubmit={(event) => {
          event.preventDefault(); void act(() => submitExternalResponse(amoCode, kind, row.id, {
            expected_version: version, response_id: approvedResponse.id,
            submitted_on: submitDate, method: submitMethod.trim(),
            external_reference: submissionRef.trim(), submission_evidence_ids: records(evidence),
          }), "Externally submitted correspondence recorded with retained proof.");
        }}>
          <h3>Record verified external submission</h3>
          <p>Only after the approved response has actually been sent to the authority/customer.</p>
          <label>Submission date<input type="date" required value={submitDate} onChange={(e) => setSubmitDate(e.target.value)} /></label>
          <label>Transmission channel<input minLength={3} required value={submitMethod} onChange={(e) => setSubmitMethod(e.target.value)} /></label>
          <label>Authority/customer receipt reference<input required minLength={2} value={submissionRef} onChange={(e) => setSubmissionRef(e.target.value)} /></label>
          <label>Retained submission evidence IDs (one per line)<textarea required value={evidence} onChange={(e) => setEvidence(e.target.value)} /></label>
          <button type="submit" disabled={busy || records(evidence).length === 0}>Record submitted response</button>
        </form> : null}
        {row.status === "RESPONSE_SUBMITTED" ? <>
          <form className="qms-review__panel qms-review__form" onSubmit={(event) => {
            event.preventDefault(); void act(() => addExternalCommitment(amoCode, kind, row.id, {
              expected_version: version, title: commitmentTitle.trim(), description: commitmentDetails.trim(),
              owner_user_id: commitmentOwner, due_date: commitmentDue,
            }), "Accountable external commitment recorded.");
          }}>
            <h3>Register response commitment</h3>
            <label>Commitment title<input minLength={4} required value={commitmentTitle} onChange={(e) => setCommitmentTitle(e.target.value)} /></label>
            <label>Required action<textarea minLength={12} required value={commitmentDetails} onChange={(e) => setCommitmentDetails(e.target.value)} /></label>
            <label>Accountable owner<select required value={commitmentOwner} onChange={(e) => setCommitmentOwner(e.target.value)}>
              <option value="">Choose person</option>{people.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}
            </select></label>
            <label>Due date<input type="date" required value={commitmentDue} onChange={(e) => setCommitmentDue(e.target.value)} /></label>
            <button type="submit" disabled={busy || !commitmentOwner}>Assign commitment</button>
          </form>
          <div className="qms-review__panel"><h3>Commitment completion and verification</h3>
            <label>Completion statement<textarea minLength={12} value={implementation} onChange={(e) => setImplementation(e.target.value)} /></label>
            <label>Retained evidence IDs<textarea value={evidence} onChange={(e) => setEvidence(e.target.value)} /></label>
            <label>Independent verification reason<textarea minLength={12} value={verification} onChange={(e) => setVerification(e.target.value)} /></label>
            {detail?.commitments.map((item) => <div className="qms-review__action" key={item.id}>
              <strong>{item.title} · {item.status}</strong>
              {item.owner_user_id === userId && ["OPEN", "REWORK"].includes(item.status) ? <button type="button"
                disabled={busy || implementation.trim().length < 12 || !records(evidence).length}
                onClick={() => void act(() => completeExternalCommitment(amoCode, kind, row.id, item.id, {
                  implementation_statement: implementation.trim(), evidence_record_ids: records(evidence),
                }), "Implementation evidence submitted for independent verification.")}>Submit completion evidence</button> : null}
              {item.owner_user_id !== userId && item.status === "AWAITING_VERIFICATION" ? <>
                <button type="button" disabled={busy || verification.trim().length < 12} onClick={() => void act(() =>
                  verifyExternalCommitment(amoCode, kind, row.id, item.id, { accepted: true, reason: verification.trim() }),
                  "Commitment verified closed.")}>Verify commitment</button>
                <button type="button" disabled={busy || verification.trim().length < 12} onClick={() => void act(() =>
                  verifyExternalCommitment(amoCode, kind, row.id, item.id, { accepted: false, reason: verification.trim() }),
                  "Commitment rejected for rework.")}>Reject and rework</button>
              </> : null}
            </div>)}
          </div>
          <form className="qms-review__panel qms-review__form" onSubmit={(event) => { event.preventDefault();
            void act(() => closeExternalRecord(amoCode, kind, row.id, {
              expected_version: version, reason: closeReason.trim(),
            }), "External issue closed with submitted response and verified commitments.");
          }}>
            <h3>Final independent closure</h3>
            <label>Closure rationale<textarea required minLength={12} value={closeReason} onChange={(e) => setCloseReason(e.target.value)} /></label>
            <button type="submit" disabled={busy || !hasSubmittedProof || openCommitments.length > 0 || row.created_by === userId}>Close controlled external issue</button>
            {row.created_by === userId ? <p>Another authorised reviewer must close the issue.</p> : null}
          </form>
        </> : null}
      </section>}
      </div>
    </main>
  </DepartmentLayout>;
}
