import React, { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle2, Clock3, RefreshCw, Save, ShieldCheck, XCircle } from "lucide-react";

import {
  activateAssessmentAttemptPolicy,
  getAssessmentAttemptPolicy,
  saveAssessmentAttemptPolicy,
} from "../../services/trainingAssessmentPolicy";
import type {
  AssessmentAttemptPolicy,
  AssessmentAttemptPolicyWrite,
} from "../../services/trainingAssessmentPolicy";
import type { AssessmentTemplate } from "../../types/trainingOperating";

type Props = {
  templates: AssessmentTemplate[];
  canManage: boolean;
  onChanged?: () => void | Promise<void>;
};

type Draft = {
  attempt_limit: string;
  time_limit_minutes: string;
  cooldown_hours: string;
  question_count: string;
  randomize_questions: boolean;
};

const blankDraft = (): Draft => ({
  attempt_limit: "",
  time_limit_minutes: "",
  cooldown_hours: "",
  question_count: "",
  randomize_questions: false,
});

const fromPolicy = (policy: AssessmentAttemptPolicy | null): Draft => policy ? ({
  attempt_limit: String(policy.attempt_limit),
  time_limit_minutes: policy.time_limit_minutes == null ? "" : String(policy.time_limit_minutes),
  cooldown_hours: String(policy.cooldown_hours),
  question_count: policy.question_count == null ? "" : String(policy.question_count),
  randomize_questions: policy.randomize_questions,
}) : blankDraft();

const positiveInteger = (value: string, label: string): number => {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) throw new Error(`${label} must be a positive whole number.`);
  return parsed;
};

const nonNegativeInteger = (value: string, label: string): number => {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 0) throw new Error(`${label} must be zero or a positive whole number.`);
  return parsed;
};

const TrainingAssessmentPolicyRegister: React.FC<Props> = ({ templates, canManage, onChanged }) => {
  const [policies, setPolicies] = useState<Record<string, AssessmentAttemptPolicy | null>>({});
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const templateIds = useMemo(() => templates.map((item) => item.id), [templates]);

  const load = useCallback(async () => {
    const entries = await Promise.all(templateIds.map(async (templateId) => {
      try {
        const policy = await getAssessmentAttemptPolicy(templateId);
        return [templateId, policy] as const;
      } catch {
        return [templateId, null] as const;
      }
    }));
    const nextPolicies = Object.fromEntries(entries);
    setPolicies(nextPolicies);
    setDrafts((current) => {
      const next = { ...current };
      for (const [templateId, policy] of entries) {
        if (!next[templateId]) next[templateId] = fromPolicy(policy);
      }
      return next;
    });
  }, [templateIds.join("|")]);

  useEffect(() => { void load(); }, [load]);

  const patch = (templateId: string, change: Partial<Draft>) => setDrafts((current) => ({
    ...current,
    [templateId]: { ...(current[templateId] || blankDraft()), ...change },
  }));

  const payloadFor = (templateId: string): AssessmentAttemptPolicyWrite => {
    const draft = drafts[templateId] || blankDraft();
    return {
      attempt_limit: positiveInteger(draft.attempt_limit, "Attempt limit"),
      time_limit_minutes: draft.time_limit_minutes.trim() ? positiveInteger(draft.time_limit_minutes, "Time limit") : null,
      cooldown_hours: nonNegativeInteger(draft.cooldown_hours, "Cooldown hours"),
      question_count: draft.question_count.trim() ? positiveInteger(draft.question_count, "Question count") : null,
      randomize_questions: draft.randomize_questions,
    };
  };

  const save = async (templateId: string) => {
    setBusyId(templateId); setError(null); setMessage(null);
    try {
      const policy = await saveAssessmentAttemptPolicy(templateId, payloadFor(templateId));
      setPolicies((current) => ({ ...current, [templateId]: policy }));
      setDrafts((current) => ({ ...current, [templateId]: fromPolicy(policy) }));
      setMessage("Assessment attempt policy saved as DRAFT. A different authorized reviewer must activate it.");
      await onChanged?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Assessment policy could not be saved.");
    } finally { setBusyId(null); }
  };

  const activate = async (templateId: string) => {
    setBusyId(templateId); setError(null); setMessage(null);
    try {
      const policy = await activateAssessmentAttemptPolicy(templateId);
      setPolicies((current) => ({ ...current, [templateId]: policy }));
      setDrafts((current) => ({ ...current, [templateId]: fromPolicy(policy) }));
      setMessage("Assessment attempt policy activated.");
      await onChanged?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Assessment policy could not be activated.");
    } finally { setBusyId(null); }
  };

  if (!templates.length) return <p className="tos-muted">Create the first controlled assessment template before defining attempt policy.</p>;

  return (
    <div className="tos-stack">
      {message ? <div className="tos-banner tos-banner--success"><CheckCircle2 size={16} />{message}<button onClick={() => setMessage(null)} aria-label="Dismiss">×</button></div> : null}
      {error ? <div className="tos-banner tos-banner--error"><XCircle size={16} />{error}<button onClick={() => setError(null)} aria-label="Dismiss">×</button></div> : null}
      {templates.map((template) => {
        const policy = policies[template.id] ?? null;
        const draft = drafts[template.id] || fromPolicy(policy);
        const busy = busyId === template.id;
        return (
          <article key={template.id} className="tos-card tos-assessment-policy-card">
            <div className="tos-section-heading">
              <div><strong>{template.code} · {template.name}</strong><small>{template.assessment_type} · template rev {template.revision_no}</small></div>
              <span className={`tos-pill ${policy?.status === "ACTIVE" ? "tos-pill--ok" : ""}`}>{policy?.status || "POLICY NOT SET"}</span>
            </div>
            <div className="tos-form-grid tos-form-grid--compact">
              <label>Attempt limit<input type="number" min="1" max="20" disabled={!canManage || busy} value={draft.attempt_limit} onChange={(event) => patch(template.id, { attempt_limit: event.target.value })} placeholder="Tenant value" /></label>
              <label>Time limit minutes<input type="number" min="1" max="1440" disabled={!canManage || busy} value={draft.time_limit_minutes} onChange={(event) => patch(template.id, { time_limit_minutes: event.target.value })} placeholder="Blank = tenant chose no countdown" /></label>
              <label>Retake cooldown hours<input type="number" min="0" max="720" disabled={!canManage || busy} value={draft.cooldown_hours} onChange={(event) => patch(template.id, { cooldown_hours: event.target.value })} placeholder="Tenant value" /></label>
              <label>Questions per attempt<input type="number" min="1" max="500" disabled={!canManage || busy} value={draft.question_count} onChange={(event) => patch(template.id, { question_count: event.target.value })} placeholder="Blank = all active questions" /></label>
              <label className="tos-check"><input type="checkbox" disabled={!canManage || busy} checked={draft.randomize_questions} onChange={(event) => patch(template.id, { randomize_questions: event.target.checked })} /><span>Randomize controlled question order</span></label>
            </div>
            <div className="tos-actions">
              <button disabled={!canManage || busy} onClick={() => void save(template.id)}><Save size={15} /> Save draft policy</button>
              <button className="primary-chip-btn" disabled={!canManage || busy || !policy || policy.status !== "DRAFT"} onClick={() => void activate(template.id)}><ShieldCheck size={15} /> Activate reviewed policy</button>
              <button disabled={busy} onClick={() => void load()}><RefreshCw size={15} /> Refresh</button>
            </div>
            {policy?.approved_at ? <small><Clock3 size={13} /> Approved {new Date(policy.approved_at).toLocaleString()}</small> : <small>Policy is not effective until independently activated.</small>}
          </article>
        );
      })}
    </div>
  );
};

export default TrainingAssessmentPolicyRegister;
