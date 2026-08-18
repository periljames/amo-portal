import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, BadgeCheck, BookOpenCheck, RefreshCw, ShieldCheck, UserRound } from "lucide-react";

import Drawer from "../shared/Drawer";
import { getTrainingPerson360, type TrainingPerson360 } from "../../services/trainingPerson360";

type Props = {
  userId: string | null;
  isOpen: boolean;
  onClose: () => void;
};

const text = (value: unknown): string => {
  if (value == null || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.length ? value.map(text).join(", ") : "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
};

const dateText = (value: unknown): string => {
  if (typeof value !== "string" || !value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString();
};

const TrainingPerson360Drawer = ({ userId, isOpen, onClose }: Props) => {
  const [data, setData] = useState<TrainingPerson360 | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!userId || !isOpen) return;
    setLoading(true);
    setError(null);
    try {
      setData(await getTrainingPerson360(userId));
    } catch (reason) {
      setData(null);
      setError(reason instanceof Error ? reason.message : "Person 360 could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [isOpen, userId]);

  useEffect(() => { void load(); }, [load]);

  const blockers = useMemo(() => (
    data?.authorization_cases.flatMap((item) => item.readiness.items.filter((entry) => entry.blocking && !["CURRENT", "COMPLETE", "READY", "NOT_APPLICABLE"].includes(entry.status))) || []
  ), [data]);

  return (
    <Drawer
      title={data ? `${data.person.full_name} · Person 360` : "Training Person 360"}
      isOpen={isOpen}
      onClose={onClose}
      panelClassName="training-form-drawer training-person-360-drawer"
    >
      <div className="tos-stack">
        <div className="tos-actions">
          <button type="button" disabled={loading || !userId} onClick={() => void load()}><RefreshCw size={15} /> Refresh</button>
        </div>
        {loading ? <p>Loading canonical Training evidence…</p> : null}
        {error ? <div className="tos-banner tos-banner--error"><AlertTriangle size={16} />{error}</div> : null}
        {data ? <>
          <section className="tos-card">
            <div className="tos-section-heading"><div><p className="tos-kicker">Person</p><h3><UserRound size={18} /> {data.person.full_name}</h3></div><span className="tos-pill">{data.person.active ? "ACTIVE" : "INACTIVE"}</span></div>
            <div className="tos-form-grid tos-form-grid--compact">
              <div><small>Staff code</small><strong>{data.person.staff_code}</strong></div>
              <div><small>Department</small><strong>{data.person.department || "—"}</strong></div>
              <div><small>Position</small><strong>{data.person.position_title || "—"}</strong></div>
              <div><small>Licence</small><strong>{data.person.licence_number || "—"}</strong></div>
              <div><small>Licence expiry</small><strong>{dateText(data.person.licence_expires_on)}</strong></div>
            </div>
          </section>

          <section className="tos-card">
            <div className="tos-section-heading"><div><p className="tos-kicker">Compliance</p><h3><BookOpenCheck size={18} /> Current Training posture</h3></div></div>
            <div className="tos-readiness-grid">
              <article className="tos-readiness-item"><strong>{data.compliance.counts.current}</strong><small>Current</small></article>
              <article className="tos-readiness-item"><strong>{data.compliance.counts.due_soon}</strong><small>Due soon</small></article>
              <article className="tos-readiness-item"><strong>{data.compliance.counts.overdue}</strong><small>Overdue</small></article>
              <article className="tos-readiness-item"><strong>{data.compliance.counts.not_done}</strong><small>Not done</small></article>
            </div>
            <div className="tos-list">
              {data.compliance.requirements.map((item) => <div key={item.course_id}><div><strong>{item.course_name}</strong><small>Last completion {dateText(item.last_completion_date)} · Valid/due {dateText(item.extended_due_date || item.valid_until)}</small></div><span className="tos-pill">{item.status}</span></div>)}
            </div>
          </section>

          <section className="tos-card">
            <div className="tos-section-heading"><div><p className="tos-kicker">Authorization</p><h3><ShieldCheck size={18} /> Explainable readiness</h3></div><span className={`tos-pill ${blockers.length ? "tos-pill--critical" : "tos-pill--ok"}`}>{blockers.length ? `${blockers.length} blocker${blockers.length === 1 ? "" : "s"}` : "No current blockers"}</span></div>
            {data.authorization_cases.length ? data.authorization_cases.map((item) => <article key={item.id} className="tos-card">
              <div className="tos-section-heading"><strong>{item.requested_scope || "Authorization case"}</strong><span className="tos-pill">{item.readiness.overall_status || item.status}</span></div>
              <small>{item.readiness.next_required_action || "No next action recorded."}</small>
              <div className="tos-list">{item.readiness.items.map((entry) => <div key={entry.key}><div><strong>{entry.label}</strong><small>{entry.reason || entry.source || "Evidence evaluated"}</small></div><span className="tos-pill">{entry.status}</span></div>)}</div>
            </article>) : <p className="tos-muted">No authorization case is recorded for this person.</p>}
          </section>

          <details className="tos-disclosure" open><summary><span><BadgeCheck size={17} /><strong>Verified records &amp; certificates</strong></span><small>{data.records.length} records · {data.certificates.length} certificate issues</small></summary><div className="tos-disclosure__body"><div className="tos-list">
            {data.records.map((row) => <div key={text(row.id)}><div><strong>{text(row.course_name)}</strong><small>Completed {dateText(row.completion_date)} · Valid until {dateText(row.valid_until)}</small></div><span className="tos-pill">{text(row.verification_status)}</span></div>)}
            {data.certificates.map((row) => <div key={text(row.id)}><div><strong>{text(row.certificate_number)}</strong><small>Issued {dateText(row.issued_at)}</small></div><span className="tos-pill">{text(row.status)}</span></div>)}
          </div></div></details>

          <details className="tos-disclosure"><summary><span><ShieldCheck size={17} /><strong>Assessments &amp; governed evidence</strong></span><small>{data.assessments.length} assessments · {data.external_and_workflow_evidence.length} workflows</small></summary><div className="tos-disclosure__body"><div className="tos-list">
            {data.assessments.map((row) => <div key={text(row.id)}><div><strong>{text(row.template_name)}</strong><small>{text(row.assessment_type)} · {dateText(row.performed_at)} · Score {text(row.score)}</small></div><span className="tos-pill">{text(row.outcome || row.status)}</span></div>)}
            {data.external_and_workflow_evidence.map((row) => <div key={text(row.id)}><div><strong>{text(row.title)}</strong><small>{text(row.workflow_type)} · {text(row.course_name)}</small></div><span className="tos-pill">{text(row.status)}</span></div>)}
          </div><small className="tos-muted">Assessment responses and answer keys are intentionally excluded from Person 360.</small></div></details>

          <details className="tos-disclosure"><summary><span><ShieldCheck size={17} /><strong>Technical authority, competence &amp; experience</strong></span><small>{data.technical_training_authorizations.length + data.competence_reviews.length + data.experience_reviews.length} items</small></summary><div className="tos-disclosure__body"><div className="tos-list">
            {data.technical_training_authorizations.map((row) => <div key={text(row.id)}><div><strong>{text(row.privilege_type)}</strong><small>{text(row.aircraft)} {text(row.engine)} · Expiry {dateText(row.expiry_date)}</small></div><span className="tos-pill">{text(row.status)}</span></div>)}
            {data.competence_reviews.map((row) => <div key={text(row.id)}><div><strong>{text(row.review_type)}</strong><small>{dateText(row.period_start)} – {dateText(row.period_end)}</small></div><span className="tos-pill">{text(row.outcome || row.status)}</span></div>)}
            {data.experience_reviews.map((row) => <div key={text(row.id)}><div><strong>Experience review</strong><small>Reviewed {dateText(row.reviewed_on)} · Next {dateText(row.next_review_due)}</small></div><span className="tos-pill">{text(row.review_status)}</span></div>)}
          </div></div></details>
        </> : null}
      </div>
    </Drawer>
  );
};

export default TrainingPerson360Drawer;
