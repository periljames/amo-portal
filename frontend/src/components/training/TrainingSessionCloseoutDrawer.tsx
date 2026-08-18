import { useCallback, useEffect, useMemo, useState } from "react";
import { BadgeCheck, CheckCircle2, RefreshCw, ShieldCheck, XCircle } from "lucide-react";

import Drawer from "../shared/Drawer";
import { listTrainingPeopleReference } from "../../services/trainingOperating";
import {
  finalizeTrainingSessionCloseout,
  getTrainingSessionCloseout,
  refreshTrainingSessionCloseout,
  verifyTrainingSessionCloseout,
  type TrainingSessionCloseout,
} from "../../services/trainingSessionCloseout";

type Props = {
  eventId: string | null;
  eventTitle?: string | null;
  isOpen: boolean;
  canManage: boolean;
  onClose: () => void;
  onChanged?: () => void | Promise<void>;
};

const numberValue = (value: unknown): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
};

const TrainingSessionCloseoutDrawer = ({ eventId, eventTitle, isOpen, canManage, onClose, onChanged }: Props) => {
  const [closeout, setCloseout] = useState<TrainingSessionCloseout | null>(null);
  const [people, setPeople] = useState<Map<string, string>>(new Map());
  const [note, setNote] = useState("");
  const [issueCertificates, setIssueCertificates] = useState(true);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!eventId || !isOpen) return;
    setLoading(true); setError(null);
    try {
      const [closeoutData, peopleData] = await Promise.all([
        getTrainingSessionCloseout(eventId),
        listTrainingPeopleReference(),
      ]);
      setCloseout(closeoutData);
      setPeople(new Map(peopleData.map((person) => [person.id, `${person.staff_code} · ${person.full_name}`])));
    } catch (reason) {
      setCloseout(null);
      setError(reason instanceof Error ? reason.message : "Session close-out could not be loaded.");
    } finally { setLoading(false); }
  }, [eventId, isOpen]);

  useEffect(() => { void load(); }, [load]);

  const blocked = useMemo(() => closeout?.learners.filter((item) => !item.completed) || [], [closeout]);
  const ready = useMemo(() => closeout?.learners.filter((item) => item.completed) || [], [closeout]);

  const run = async (operation: () => Promise<TrainingSessionCloseout>, success: string) => {
    setBusy(true); setError(null); setMessage(null);
    try {
      const updated = await operation();
      setCloseout(updated);
      setMessage(success);
      await onChanged?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The close-out action could not be completed.");
    } finally { setBusy(false); }
  };

  return (
    <Drawer title={`Session close-out${eventTitle ? ` · ${eventTitle}` : ""}`} isOpen={isOpen} onClose={onClose} panelClassName="training-form-drawer training-session-closeout-drawer">
      <div className="tos-stack">
        {message ? <div className="tos-banner tos-banner--success"><CheckCircle2 size={16} />{message}<button type="button" onClick={() => setMessage(null)}>×</button></div> : null}
        {error ? <div className="tos-banner tos-banner--error"><XCircle size={16} />{error}<button type="button" onClick={() => setError(null)}>×</button></div> : null}
        <section className="tos-card">
          <div className="tos-section-heading">
            <div><p className="tos-kicker">Governed evidence gate</p><h3>Completion → verification → certificate</h3></div>
            <span className="tos-pill">{closeout?.status || (loading ? "LOADING" : "UNKNOWN")}</span>
          </div>
          <p>Refresh evaluates persisted module attendance, practical tasks and canonical assessment outcomes. Finalization creates pending completion records only for learners who satisfy those gates. Independent verification then verifies records and issues eligible certificates.</p>
          <div className="tos-readiness-grid">
            <article className="tos-readiness-item"><strong>{numberValue(closeout?.summary.participant_count)}</strong><small>Participants</small></article>
            <article className="tos-readiness-item"><strong>{ready.length}</strong><small>Completion ready</small></article>
            <article className="tos-readiness-item"><strong>{blocked.length}</strong><small>Blocked / exception</small></article>
            <article className="tos-readiness-item"><strong>{numberValue(closeout?.summary.certificate_eligible_count)}</strong><small>Certificate eligible</small></article>
          </div>
          <div className="tos-actions">
            <button type="button" disabled={!eventId || busy || loading} onClick={() => void load()}><RefreshCw size={15} /> Reload</button>
            <button type="button" disabled={!eventId || !canManage || busy || Boolean(closeout?.closed_at)} onClick={() => eventId && void run(() => refreshTrainingSessionCloseout(eventId), "Close-out evidence refreshed.")}><RefreshCw size={15} /> Re-evaluate evidence</button>
          </div>
        </section>

        <section className="tos-card">
          <div className="tos-section-heading"><h3>Learner decisions</h3><small>{closeout?.learners.length || 0} retained decisions</small></div>
          <div className="tos-list">
            {(closeout?.learners || []).map((learner) => <div key={learner.id}>
              <div><strong>{people.get(learner.user_id) || learner.user_id}</strong><small>{learner.blockers.length ? learner.blockers.join(" · ") : "Persisted completion evidence satisfies the governed gates."}</small></div>
              <span className={`tos-pill ${learner.completed ? "tos-pill--ok" : "tos-pill--critical"}`}>{learner.status}</span>
            </div>)}
            {closeout && !closeout.learners.length ? <p className="tos-muted">No eligible roster members are present in this governed session.</p> : null}
          </div>
        </section>

        <section className="tos-card">
          <div className="tos-section-heading"><h3>Controlled close-out</h3><ShieldCheck size={18} /></div>
          <label>Close-out / verification note<textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="Optional evidence or decision note" /></label>
          <label className="tos-check"><input type="checkbox" checked={issueCertificates} onChange={(event) => setIssueCertificates(event.target.checked)} /><span>Issue certificates for independently verified, certificate-eligible records</span></label>
          <div className="tos-actions">
            <button type="button" className="primary-chip-btn" disabled={!eventId || !canManage || busy || Boolean(closeout?.closed_at)} onClick={() => eventId && void run(() => finalizeTrainingSessionCloseout(eventId, note), "Session finalized. Completion records are pending independent verification.")}><CheckCircle2 size={15} /> Finalize session</button>
            <button type="button" disabled={!eventId || !canManage || busy || !closeout?.closed_at || closeout.status === "VERIFIED"} onClick={() => eventId && void run(() => verifyTrainingSessionCloseout(eventId, note, issueCertificates), "Independent completion verification recorded.")}><BadgeCheck size={15} /> Verify records{issueCertificates ? " & issue certificates" : ""}</button>
          </div>
          {closeout?.closed_by_user_id ? <small>Finalized by user {closeout.closed_by_user_id} on {closeout.closed_at ? new Date(closeout.closed_at).toLocaleString() : "—"}. The backend rejects verification by the same user.</small> : null}
          {closeout?.issued_certificates?.length ? <div className="tos-list">{closeout.issued_certificates.map((issue) => <div key={issue.certificate_issue_id}><div><strong>{issue.certificate_number}</strong><small>Record {issue.record_id}</small></div><span className="tos-pill tos-pill--ok">ISSUED</span></div>)}</div> : null}
        </section>
      </div>
    </Drawer>
  );
};

export default TrainingSessionCloseoutDrawer;
