import React, { useCallback, useEffect, useState } from "react";

import {
  createCompetenceReview, createEffectivenessEvaluation, createExperienceLog, createExperienceReview,
  createRemedialAction, listEffectivenessEvaluations, listRemedialActions,
  type TrainingPersonReference,
} from "../../services/trainingOperating";
import type { TrainingCourseRead } from "../../types/training";
import type { EffectivenessEvaluation, RemedialAction } from "../../types/trainingOperating";

type Props = {
  people: TrainingPersonReference[];
  courses: TrainingCourseRead[];
  busy: boolean;
  can: (capability: string) => boolean;
  execute: (operation: () => Promise<unknown>, success: string) => Promise<void>;
};

const today = () => new Date().toISOString().slice(0, 10);
const startOfYear = () => `${new Date().getFullYear()}-01-01`;

const TrainingGovernanceForms: React.FC<Props> = ({ people, courses, busy, can, execute }) => {
  const [experience, setExperience] = useState({ candidate_user_id: "", activity_date: today(), activity: "", aircraft_component_task: "", duration_hours: "", supervisor_user_id: "", reference: "" });
  const [experienceReview, setExperienceReview] = useState({ candidate_user_id: "", reviewed_on: today(), review_status: "SATISFACTORY", evidence_summary: "" });
  const [effectiveness, setEffectiveness] = useState({ course_id: "", user_id: "", level: "1", evaluation_period_start: startOfYear(), evaluation_period_end: today(), rating: "", conclusion: "", causation_claimed: false, baseline: "", comparison: "", confounders: "", method: "" });
  const [competence, setCompetence] = useState({ candidate_user_id: "", period_start: startOfYear(), period_end: today(), course_id: "", outcome: "COMPETENT", strengths: "", gaps: "", actions: "", reassessment_due: "" });
  const [remedial, setRemedial] = useState({ candidate_user_id: "", course_id: "", gap: "", required_activity: "", owner_user_id: "", due_date: today(), supervised_experience_required: false, reassessment_required: true });
  const [evaluations, setEvaluations] = useState<EffectivenessEvaluation[]>([]);
  const [actions, setActions] = useState<RemedialAction[]>([]);

  const loadRegisters = useCallback(async () => {
    const [evaluationRows, actionRows] = await Promise.all([listEffectivenessEvaluations(), listRemedialActions()]);
    setEvaluations(evaluationRows);
    setActions(actionRows);
  }, []);

  useEffect(() => { void loadRegisters().catch(() => undefined); }, [loadRegisters]);
  const personOptions = <>{people.map((person) => <option key={person.id} value={person.id}>{person.staff_code} · {person.full_name}</option>)}</>;
  const courseOptions = <>{courses.map((course) => <option key={course.id} value={course.id}>{course.course_id} · {course.course_name}</option>)}</>;

  return <div className="tos-stack tos-span-2">
    <section className="tos-card"><div className="tos-card__heading"><div><h2>Experience evidence</h2><p>Capture supervised work or OJT activity, then record the independent experience review used by competence and authorization decisions.</p></div></div><div className="tos-form-grid">
      <label>Person<select value={experience.candidate_user_id} onChange={(event) => setExperience({ ...experience, candidate_user_id: event.target.value })}><option value="">Select person</option>{personOptions}</select></label>
      <label>Activity date<input type="date" value={experience.activity_date} onChange={(event) => setExperience({ ...experience, activity_date: event.target.value })} /></label>
      <label className="tos-span-2">Activity<textarea value={experience.activity} onChange={(event) => setExperience({ ...experience, activity: event.target.value })} placeholder="Describe the task performed and level of participation." /></label>
      <label>Aircraft / component / task<input value={experience.aircraft_component_task} onChange={(event) => setExperience({ ...experience, aircraft_component_task: event.target.value })} /></label>
      <label>Duration hours<input type="number" min="0" step="0.25" value={experience.duration_hours} onChange={(event) => setExperience({ ...experience, duration_hours: event.target.value })} /></label>
      <label>Supervisor<select value={experience.supervisor_user_id} onChange={(event) => setExperience({ ...experience, supervisor_user_id: event.target.value })}><option value="">Not assigned</option>{personOptions}</select></label>
      <label>Evidence reference<input value={experience.reference} onChange={(event) => setExperience({ ...experience, reference: event.target.value })} placeholder="Work order, tech log, OJT sheet" /></label>
    </div><button disabled={busy || !experience.candidate_user_id || experience.activity.trim().length < 3 || !can("training.assessment.perform")} onClick={() => execute(() => createExperienceLog({ ...experience, supervisor_user_id: experience.supervisor_user_id || null, duration_hours: experience.duration_hours ? Number(experience.duration_hours) : null }), "Experience entry recorded.")}>Record experience</button>
    <div className="tos-form-grid">
      <label>Person to review<select value={experienceReview.candidate_user_id} onChange={(event) => setExperienceReview({ ...experienceReview, candidate_user_id: event.target.value })}><option value="">Select person</option>{personOptions}</select></label>
      <label>Review date<input type="date" value={experienceReview.reviewed_on} onChange={(event) => setExperienceReview({ ...experienceReview, reviewed_on: event.target.value })} /></label>
      <label>Decision<select value={experienceReview.review_status} onChange={(event) => setExperienceReview({ ...experienceReview, review_status: event.target.value })}><option>SATISFACTORY</option><option>GAPS_IDENTIFIED</option><option>REJECTED</option></select></label>
      <label>Evidence summary<textarea value={experienceReview.evidence_summary} onChange={(event) => setExperienceReview({ ...experienceReview, evidence_summary: event.target.value })} /></label>
    </div><button disabled={busy || !experienceReview.candidate_user_id || !can("training.assessment.review")} onClick={() => execute(() => createExperienceReview(experienceReview), "Experience review recorded.")}>Record experience review</button></section>

    <section className="tos-card"><div className="tos-card__heading"><div><h2>Training effectiveness</h2><p>Record Kirkpatrick level 1–4 evidence. A level-4 causation claim requires baseline, comparison, confounders and method evidence.</p></div></div><div className="tos-form-grid">
      <label>Course<select value={effectiveness.course_id} onChange={(event) => setEffectiveness({ ...effectiveness, course_id: event.target.value })}><option value="">Select course</option>{courseOptions}</select></label>
      <label>Person (optional)<select value={effectiveness.user_id} onChange={(event) => setEffectiveness({ ...effectiveness, user_id: event.target.value })}><option value="">Whole cohort</option>{personOptions}</select></label>
      <label>Evaluation level<select value={effectiveness.level} onChange={(event) => setEffectiveness({ ...effectiveness, level: event.target.value })}><option value="1">1 · Reaction</option><option value="2">2 · Learning</option><option value="3">3 · Behaviour</option><option value="4">4 · Results</option></select></label>
      <label>Rating<input type="number" step="0.1" value={effectiveness.rating} onChange={(event) => setEffectiveness({ ...effectiveness, rating: event.target.value })} /></label>
      <label>Period start<input type="date" value={effectiveness.evaluation_period_start} onChange={(event) => setEffectiveness({ ...effectiveness, evaluation_period_start: event.target.value })} /></label>
      <label>Period end<input type="date" value={effectiveness.evaluation_period_end} onChange={(event) => setEffectiveness({ ...effectiveness, evaluation_period_end: event.target.value })} /></label>
      <label className="tos-span-2">Conclusion<textarea value={effectiveness.conclusion} onChange={(event) => setEffectiveness({ ...effectiveness, conclusion: event.target.value })} /></label>
      {effectiveness.level === "4" ? <><label>Baseline<input value={effectiveness.baseline} onChange={(event) => setEffectiveness({ ...effectiveness, baseline: event.target.value })} /></label><label>Comparison<input value={effectiveness.comparison} onChange={(event) => setEffectiveness({ ...effectiveness, comparison: event.target.value })} /></label><label>Confounders<input value={effectiveness.confounders} onChange={(event) => setEffectiveness({ ...effectiveness, confounders: event.target.value })} /></label><label>Method<input value={effectiveness.method} onChange={(event) => setEffectiveness({ ...effectiveness, method: event.target.value })} /></label><label className="tos-span-2"><span><input type="checkbox" checked={effectiveness.causation_claimed} onChange={(event) => setEffectiveness({ ...effectiveness, causation_claimed: event.target.checked })} /> Claim causation between training and measured result</span></label></> : null}
    </div><button disabled={busy || !effectiveness.course_id || !can("training.assessment.perform")} onClick={() => execute(async () => { await createEffectivenessEvaluation({ course_id: effectiveness.course_id, user_id: effectiveness.user_id || null, level: Number(effectiveness.level), evaluation_period_start: effectiveness.evaluation_period_start || null, evaluation_period_end: effectiveness.evaluation_period_end || null, rating: effectiveness.rating ? Number(effectiveness.rating) : null, conclusion: effectiveness.conclusion || null, causation_claimed: effectiveness.causation_claimed, evidence: effectiveness.level === "4" ? { baseline: effectiveness.baseline, comparison: effectiveness.comparison, confounders: effectiveness.confounders, method: effectiveness.method } : {} }); await loadRegisters(); }, "Effectiveness evaluation recorded.")}>Record evaluation</button><div className="tos-list">{evaluations.slice(0, 8).map((item) => <div key={item.id}><div><strong>Level {item.level} · {courses.find((course) => course.id === item.course_id)?.course_name || item.course_id}</strong><small>{item.conclusion || "No conclusion"}</small></div><span>{item.status}</span></div>)}</div></section>

    <section className="tos-card"><div className="tos-card__heading"><div><h2>Continued competence & remedial action</h2><p>Record the periodic decision, gaps and required follow-up without hiding them inside free-text notes.</p></div></div><div className="tos-form-grid">
      <label>Person<select value={competence.candidate_user_id} onChange={(event) => setCompetence({ ...competence, candidate_user_id: event.target.value })}><option value="">Select person</option>{personOptions}</select></label>
      <label>Related course<select value={competence.course_id} onChange={(event) => setCompetence({ ...competence, course_id: event.target.value })}><option value="">Whole competence scope</option>{courseOptions}</select></label>
      <label>Period start<input type="date" value={competence.period_start} onChange={(event) => setCompetence({ ...competence, period_start: event.target.value })} /></label><label>Period end<input type="date" value={competence.period_end} onChange={(event) => setCompetence({ ...competence, period_end: event.target.value })} /></label>
      <label>Outcome<select value={competence.outcome} onChange={(event) => setCompetence({ ...competence, outcome: event.target.value })}><option>COMPETENT</option><option>TRAINING_REQUIRED</option><option>SUPERVISED_EXPERIENCE_REQUIRED</option><option>REASSESSMENT_REQUIRED</option><option>RESTRICT</option><option>ESCALATE</option></select></label><label>Reassessment due<input type="date" value={competence.reassessment_due} onChange={(event) => setCompetence({ ...competence, reassessment_due: event.target.value })} /></label>
      <label>Strengths<textarea value={competence.strengths} onChange={(event) => setCompetence({ ...competence, strengths: event.target.value })} /></label><label>Gaps<textarea value={competence.gaps} onChange={(event) => setCompetence({ ...competence, gaps: event.target.value })} /></label><label className="tos-span-2">Actions<textarea value={competence.actions} onChange={(event) => setCompetence({ ...competence, actions: event.target.value })} /></label>
    </div><button disabled={busy || !competence.candidate_user_id || !can("training.assessment.perform")} onClick={() => execute(() => createCompetenceReview({ ...competence, course_id: competence.course_id || null, reassessment_due: competence.reassessment_due || null, criteria: [], evidence: {} }), "Competence review recorded.")}>Record competence review</button>
    <div className="tos-form-grid"><label>Person<select value={remedial.candidate_user_id} onChange={(event) => setRemedial({ ...remedial, candidate_user_id: event.target.value })}><option value="">Select person</option>{personOptions}</select></label><label>Course<select value={remedial.course_id} onChange={(event) => setRemedial({ ...remedial, course_id: event.target.value })}><option value="">No single course</option>{courseOptions}</select></label><label>Gap<textarea value={remedial.gap} onChange={(event) => setRemedial({ ...remedial, gap: event.target.value })} /></label><label>Required activity<textarea value={remedial.required_activity} onChange={(event) => setRemedial({ ...remedial, required_activity: event.target.value })} /></label><label>Owner<select value={remedial.owner_user_id} onChange={(event) => setRemedial({ ...remedial, owner_user_id: event.target.value })}><option value="">Unassigned</option>{personOptions}</select></label><label>Due date<input type="date" value={remedial.due_date} onChange={(event) => setRemedial({ ...remedial, due_date: event.target.value })} /></label><label><span><input type="checkbox" checked={remedial.supervised_experience_required} onChange={(event) => setRemedial({ ...remedial, supervised_experience_required: event.target.checked })} /> Supervised experience required</span></label><label><span><input type="checkbox" checked={remedial.reassessment_required} onChange={(event) => setRemedial({ ...remedial, reassessment_required: event.target.checked })} /> Reassessment required</span></label></div><button disabled={busy || !remedial.candidate_user_id || remedial.gap.trim().length < 3 || remedial.required_activity.trim().length < 3 || !can("training.assessment.create")} onClick={() => execute(async () => { await createRemedialAction({ ...remedial, course_id: remedial.course_id || null, owner_user_id: remedial.owner_user_id || null }); await loadRegisters(); }, "Remedial action created.")}>Create remedial action</button><div className="tos-list">{actions.slice(0, 8).map((item) => <div key={item.id}><div><strong>{people.find((person) => person.id === item.candidate_user_id)?.full_name || item.candidate_user_id}</strong><small>{item.gap} · Due {item.due_date}</small></div><span>{item.status}</span></div>)}</div></section>
  </div>;
};

export default TrainingGovernanceForms;
