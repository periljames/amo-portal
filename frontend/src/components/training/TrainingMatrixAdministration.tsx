import React, { useCallback, useEffect, useState } from "react";

import { listTrainingCourses } from "../../services/training";
import { listTrainingPeopleReference } from "../../services/trainingOperating";
import {
  deactivateTrainingPersonRole,
  deactivateTrainingRoleGroup,
  deactivateTrainingRoleRule,
  listTrainingPersonRoles,
  listTrainingRoleGroups,
  listTrainingRoleRules,
  saveTrainingPersonRole,
  saveTrainingRoleGroup,
  saveTrainingRoleRule,
} from "../../services/trainingWorkbookImport";
import type { TrainingCourseRead } from "../../types/training";
import type { TrainingPersonReference } from "../../services/trainingOperating";
import type { TrainingCourseRoleRuleRead, TrainingPersonRoleRead, TrainingRoleGroupRead } from "../../types/trainingWorkbookImport";

interface Props {
  canManage: boolean;
}

const TrainingMatrixAdministration: React.FC<Props> = ({ canManage }) => {
  const [groups, setGroups] = useState<TrainingRoleGroupRead[]>([]);
  const [assignments, setAssignments] = useState<TrainingPersonRoleRead[]>([]);
  const [rules, setRules] = useState<TrainingCourseRoleRuleRead[]>([]);
  const [people, setPeople] = useState<TrainingPersonReference[]>([]);
  const [courses, setCourses] = useState<TrainingCourseRead[]>([]);
  const [groupForm, setGroupForm] = useState({ code: "", description: "" });
  const [assignmentForm, setAssignmentForm] = useState({ user_id: "", role_group_id: "", department: "", position: "", notes: "" });
  const [ruleForm, setRuleForm] = useState({ course_id: "", role_group_id: "", requirement_type: "GENERAL", notes: "", is_required: true });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [groupRows, assignmentRows, ruleRows, personRows, courseRows] = await Promise.all([
        listTrainingRoleGroups(), listTrainingPersonRoles(), listTrainingRoleRules(), listTrainingPeopleReference(), listTrainingCourses(),
      ]);
      setGroups(groupRows); setAssignments(assignmentRows); setRules(ruleRows); setPeople(personRows); setCourses(courseRows);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Training matrix sources could not be loaded.");
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const mutate = async (operation: () => Promise<unknown>) => {
    setBusy(true); setError(null);
    try { await operation(); await load(); }
    catch (caught) { setError(caught instanceof Error ? caught.message : "The matrix change could not be saved."); }
    finally { setBusy(false); }
  };

  return (
    <div className="tos-stack">
      {error ? <div className="tos-banner tos-banner--error">{error}</div> : null}
      <section className="tos-card">
        <div className="tos-card__heading"><div><h2>Role groups</h2><p>Maintain the applicability groups imported from tblRoleGroups without editing Excel.</p></div></div>
        <div className="tos-actionbar"><label>Code<input value={groupForm.code} onChange={(event) => setGroupForm({ ...groupForm, code: event.target.value.toUpperCase() })} placeholder="e.g. AVIONICS" /></label><label>Description<input value={groupForm.description} onChange={(event) => setGroupForm({ ...groupForm, description: event.target.value })} /></label><button disabled={busy || !canManage || !groupForm.code.trim()} onClick={() => void mutate(async () => { await saveTrainingRoleGroup(groupForm); setGroupForm({ code: "", description: "" }); })}>Add / reactivate group</button></div>
        <div className="tos-list">{groups.map((group) => <div key={group.id}><div><strong>{group.code}</strong><small>{group.description || "No description"}</small></div><button disabled={busy || !canManage} onClick={() => void mutate(() => deactivateTrainingRoleGroup(group.id))}>Deactivate</button></div>)}</div>
      </section>

      <section className="tos-card">
        <div className="tos-card__heading"><div><h2>Personnel role assignments</h2><p>Maintain tblPersonRoles directly; the expiry plan uses these assignments when resolving required courses.</p></div></div>
        <div className="tos-form-grid"><label>Person<select value={assignmentForm.user_id} onChange={(event) => setAssignmentForm({ ...assignmentForm, user_id: event.target.value })}><option value="">Select person</option>{people.map((person) => <option key={person.id} value={person.id}>{person.full_name} · {person.staff_code || person.id}</option>)}</select></label><label>Role group<select value={assignmentForm.role_group_id} onChange={(event) => setAssignmentForm({ ...assignmentForm, role_group_id: event.target.value })}><option value="">Select group</option>{groups.map((group) => <option key={group.id} value={group.id}>{group.code}</option>)}</select></label><label>Department<input value={assignmentForm.department} onChange={(event) => setAssignmentForm({ ...assignmentForm, department: event.target.value })} /></label><label>Position<input value={assignmentForm.position} onChange={(event) => setAssignmentForm({ ...assignmentForm, position: event.target.value })} /></label><label>Notes<input value={assignmentForm.notes} onChange={(event) => setAssignmentForm({ ...assignmentForm, notes: event.target.value })} /></label></div>
        <button disabled={busy || !canManage || !assignmentForm.user_id || !assignmentForm.role_group_id} onClick={() => void mutate(async () => { await saveTrainingPersonRole(assignmentForm); setAssignmentForm({ user_id: "", role_group_id: "", department: "", position: "", notes: "" }); })}>Assign role group</button>
        <div className="tos-table-wrap"><table className="tos-table"><thead><tr><th>Person</th><th>Group</th><th>Department / position</th><th>Notes</th><th>Action</th></tr></thead><tbody>{assignments.map((assignment) => <tr key={assignment.id}><td>{assignment.person_name || assignment.person_id}<small>{assignment.staff_code || assignment.person_id}</small></td><td>{assignment.role_group_code}</td><td>{assignment.department || "—"}<small>{assignment.position || ""}</small></td><td>{assignment.notes || "—"}</td><td><button disabled={busy || !canManage} onClick={() => void mutate(() => deactivateTrainingPersonRole(assignment.id))}>Deactivate</button></td></tr>)}</tbody></table></div>
      </section>

      <section className="tos-card">
        <div className="tos-card__heading"><div><h2>Course requirement matrix</h2><p>Maintain tblCourseMatrix directly. Required rules feed never-completed obligations into the autonomous plan.</p></div></div>
        <div className="tos-form-grid"><label>Course<select value={ruleForm.course_id} onChange={(event) => setRuleForm({ ...ruleForm, course_id: event.target.value })}><option value="">Select course</option>{courses.map((course) => <option key={course.id} value={course.id}>{course.course_id} · {course.course_name}</option>)}</select></label><label>Role group<select value={ruleForm.role_group_id} onChange={(event) => setRuleForm({ ...ruleForm, role_group_id: event.target.value })}><option value="">Select group</option>{groups.map((group) => <option key={group.id} value={group.id}>{group.code}</option>)}</select></label><label>Requirement type<input value={ruleForm.requirement_type} onChange={(event) => setRuleForm({ ...ruleForm, requirement_type: event.target.value.toUpperCase() })} /></label><label>Notes<input value={ruleForm.notes} onChange={(event) => setRuleForm({ ...ruleForm, notes: event.target.value })} /></label><label><input type="checkbox" checked={ruleForm.is_required} onChange={(event) => setRuleForm({ ...ruleForm, is_required: event.target.checked })} /> Required</label></div>
        <button disabled={busy || !canManage || !ruleForm.course_id || !ruleForm.role_group_id} onClick={() => void mutate(async () => { await saveTrainingRoleRule(ruleForm); setRuleForm({ course_id: "", role_group_id: "", requirement_type: "GENERAL", notes: "", is_required: true }); })}>Add / reactivate matrix rule</button>
        <div className="tos-table-wrap"><table className="tos-table"><thead><tr><th>Course</th><th>Group</th><th>Type</th><th>Required</th><th>Notes</th><th>Action</th></tr></thead><tbody>{rules.map((rule) => <tr key={rule.id}><td>{rule.course_code}<small>{rule.course_name}</small></td><td>{rule.role_group_code}</td><td>{rule.requirement_type}</td><td>{rule.is_required ? "Yes" : "No"}</td><td>{rule.notes || "—"}</td><td><button disabled={busy || !canManage} onClick={() => void mutate(() => deactivateTrainingRoleRule(rule.id))}>Deactivate</button></td></tr>)}</tbody></table></div>
      </section>
    </div>
  );
};

export default TrainingMatrixAdministration;
