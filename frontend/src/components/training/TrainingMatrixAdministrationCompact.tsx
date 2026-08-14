import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  BookOpenCheck, ChevronLeft, ChevronRight, Plus, Search, ShieldCheck, UserRoundCog,
} from "lucide-react";

import Drawer from "../shared/Drawer";
import { listTrainingCourses } from "../../services/training";
import { listTrainingPeopleReference } from "../../services/trainingOperating";
import {
  deactivateTrainingPersonRole, deactivateTrainingRoleGroup, deactivateTrainingRoleRule,
  listTrainingPersonRoles, listTrainingRoleGroups, listTrainingRoleRules,
  saveTrainingPersonRole, saveTrainingRoleGroup, saveTrainingRoleRule,
} from "../../services/trainingWorkbookImport";
import type { TrainingCourseRead } from "../../types/training";
import type { TrainingPersonReference } from "../../services/trainingOperating";
import type {
  TrainingCourseRoleRuleRead, TrainingPersonRoleRead, TrainingRoleGroupRead,
} from "../../types/trainingWorkbookImport";

interface Props { canManage: boolean }
type MatrixView = "GROUPS" | "PEOPLE" | "RULES";

const PAGE_SIZE = 10;

const TrainingMatrixAdministrationCompact: React.FC<Props> = ({ canManage }) => {
  const [view, setView] = useState<MatrixView>("GROUPS");
  const [groups, setGroups] = useState<TrainingRoleGroupRead[]>([]);
  const [assignments, setAssignments] = useState<TrainingPersonRoleRead[]>([]);
  const [rules, setRules] = useState<TrainingCourseRoleRuleRead[]>([]);
  const [people, setPeople] = useState<TrainingPersonReference[]>([]);
  const [courses, setCourses] = useState<TrainingCourseRead[]>([]);
  const [groupForm, setGroupForm] = useState({ code: "", description: "" });
  const [assignmentForm, setAssignmentForm] = useState({ user_id: "", role_group_id: "", department: "", position: "", notes: "" });
  const [ruleForm, setRuleForm] = useState({ course_id: "", role_group_id: "", requirement_type: "GENERAL", notes: "", is_required: true });
  const [formOpen, setFormOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [groupRows, assignmentRows, ruleRows, personRows, courseRows] = await Promise.all([
        listTrainingRoleGroups(), listTrainingPersonRoles(), listTrainingRoleRules(),
        listTrainingPeopleReference("", 200, 0), listTrainingCourses({ limit: 200 }),
      ]);
      setGroups(groupRows); setAssignments(assignmentRows); setRules(ruleRows);
      setPeople(personRows); setCourses(courseRows);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Training matrix sources could not be loaded.");
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const mutate = async (operation: () => Promise<unknown>, closeForm = false) => {
    setBusy(true); setError(null);
    try {
      await operation();
      if (closeForm) setFormOpen(false);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The matrix change could not be saved.");
    } finally { setBusy(false); }
  };

  const filteredGroups = useMemo(() => groups.filter((item) => `${item.code} ${item.description || ""}`.toLowerCase().includes(search.toLowerCase())), [groups, search]);
  const filteredAssignments = useMemo(() => assignments.filter((item) => `${item.person_name || ""} ${item.staff_code || ""} ${item.role_group_code} ${item.department || ""} ${item.position || ""}`.toLowerCase().includes(search.toLowerCase())), [assignments, search]);
  const filteredRules = useMemo(() => rules.filter((item) => `${item.course_code} ${item.course_name} ${item.role_group_code} ${item.requirement_type}`.toLowerCase().includes(search.toLowerCase())), [rules, search]);
  const activeRows = view === "GROUPS" ? filteredGroups : view === "PEOPLE" ? filteredAssignments : filteredRules;
  const pageRows = activeRows.slice(offset, offset + PAGE_SIZE);
  const hasMore = offset + pageRows.length < activeRows.length;

  const changeView = (next: MatrixView) => { setView(next); setSearch(""); setOffset(0); setFormOpen(false); };
  const title = view === "GROUPS" ? "Role groups" : view === "PEOPLE" ? "Personnel assignments" : "Course matrix rules";
  const help = view === "GROUPS" ? "Define reusable applicability groups." : view === "PEOPLE" ? "Connect canonical users to role groups." : "Map courses to groups for autonomous planning.";

  return <div className="tos-stack">
    {error ? <div className="tos-banner tos-banner--error">{error}<button onClick={() => setError(null)}>×</button></div> : null}
    <nav className="tos-matrix-subnav" aria-label="Applicability matrix sections">
      <button className={view === "GROUPS" ? "is-active" : ""} onClick={() => changeView("GROUPS")}><ShieldCheck size={17} /><span><strong>Role groups</strong><small>{groups.length}</small></span></button>
      <button className={view === "PEOPLE" ? "is-active" : ""} onClick={() => changeView("PEOPLE")}><UserRoundCog size={17} /><span><strong>People</strong><small>{assignments.length}</small></span></button>
      <button className={view === "RULES" ? "is-active" : ""} onClick={() => changeView("RULES")}><BookOpenCheck size={17} /><span><strong>Course rules</strong><small>{rules.length}</small></span></button>
    </nav>

    <section className="tos-card tos-register-card">
      <div className="tos-card__heading"><div><h3>{title}</h3><small>{help}</small></div><button disabled={!canManage} onClick={() => setFormOpen(true)}><Plus size={16} /> {view === "GROUPS" ? "Group" : view === "PEOPLE" ? "Assignment" : "Rule"}</button></div>
      <div className="tos-compact-filter"><Search size={16} /><input value={search} onChange={(event) => { setSearch(event.target.value); setOffset(0); }} placeholder={`Search ${title.toLowerCase()}`} /></div>

      {view === "GROUPS" ? <div className="tos-table-wrap tos-bounded-register"><table className="tos-table tos-table--responsive"><thead><tr><th>Code</th><th>Description</th><th>Action</th></tr></thead><tbody>{(pageRows as TrainingRoleGroupRead[]).map((group) => <tr key={group.id}><td data-label="Code"><strong>{group.code}</strong></td><td data-label="Description">{group.description || "No description"}</td><td data-label="Action"><button disabled={busy || !canManage} onClick={() => void mutate(() => deactivateTrainingRoleGroup(group.id))}>Deactivate</button></td></tr>)}</tbody></table></div> : null}
      {view === "PEOPLE" ? <div className="tos-table-wrap tos-bounded-register"><table className="tos-table tos-table--responsive"><thead><tr><th>Person</th><th>Group</th><th>Department / position</th><th>Notes</th><th>Action</th></tr></thead><tbody>{(pageRows as TrainingPersonRoleRead[]).map((assignment) => <tr key={assignment.id}><td data-label="Person">{assignment.person_name || assignment.person_id}<small>{assignment.staff_code || assignment.person_id}</small></td><td data-label="Group">{assignment.role_group_code}</td><td data-label="Department / position">{assignment.department || "—"}<small>{assignment.position || ""}</small></td><td data-label="Notes">{assignment.notes || "—"}</td><td data-label="Action"><button disabled={busy || !canManage} onClick={() => void mutate(() => deactivateTrainingPersonRole(assignment.id))}>Deactivate</button></td></tr>)}</tbody></table></div> : null}
      {view === "RULES" ? <div className="tos-table-wrap tos-bounded-register"><table className="tos-table tos-table--responsive"><thead><tr><th>Course</th><th>Group</th><th>Type</th><th>Required</th><th>Notes</th><th>Action</th></tr></thead><tbody>{(pageRows as TrainingCourseRoleRuleRead[]).map((ruleItem) => <tr key={ruleItem.id}><td data-label="Course">{ruleItem.course_code}<small>{ruleItem.course_name}</small></td><td data-label="Group">{ruleItem.role_group_code}</td><td data-label="Type">{ruleItem.requirement_type}</td><td data-label="Required">{ruleItem.is_required ? "Yes" : "No"}</td><td data-label="Notes">{ruleItem.notes || "—"}</td><td data-label="Action"><button disabled={busy || !canManage} onClick={() => void mutate(() => deactivateTrainingRoleRule(ruleItem.id))}>Deactivate</button></td></tr>)}</tbody></table></div> : null}

      {!pageRows.length ? <div className="tos-empty"><strong>No matching records</strong><span>Adjust the search or add a new item.</span></div> : null}
      <div className="tos-pagination"><span>{activeRows.length ? `${offset + 1}–${Math.min(offset + PAGE_SIZE, activeRows.length)} of ${activeRows.length}` : "0 records"}</span><div><button className="tos-icon-button" aria-label="Previous matrix page" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}><ChevronLeft size={18} /></button><button className="tos-icon-button" aria-label="Next matrix page" disabled={!hasMore} onClick={() => setOffset(offset + PAGE_SIZE)}><ChevronRight size={18} /></button></div></div>
    </section>

    <Drawer title={view === "GROUPS" ? "Add or reactivate role group" : view === "PEOPLE" ? "Assign a person to a role group" : "Add or reactivate course rule"} isOpen={formOpen} onClose={() => setFormOpen(false)} panelClassName="training-form-drawer"><div className="tos-drawer-form">
      {view === "GROUPS" ? <><label>Code<input value={groupForm.code} onChange={(event) => setGroupForm({ ...groupForm, code: event.target.value.toUpperCase() })} placeholder="e.g. AVIONICS" /></label><label>Description<textarea value={groupForm.description} onChange={(event) => setGroupForm({ ...groupForm, description: event.target.value })} /></label></> : null}
      {view === "PEOPLE" ? <><label>Canonical portal user<select value={assignmentForm.user_id} onChange={(event) => setAssignmentForm({ ...assignmentForm, user_id: event.target.value })}><option value="">Select person</option>{people.map((person) => <option key={person.id} value={person.id}>{person.full_name} · {person.staff_code || person.id}</option>)}</select></label><label>Role group<select value={assignmentForm.role_group_id} onChange={(event) => setAssignmentForm({ ...assignmentForm, role_group_id: event.target.value })}><option value="">Select group</option>{groups.map((group) => <option key={group.id} value={group.id}>{group.code}</option>)}</select></label><div className="tos-form-grid"><label>Department<input value={assignmentForm.department} onChange={(event) => setAssignmentForm({ ...assignmentForm, department: event.target.value })} /></label><label>Position<input value={assignmentForm.position} onChange={(event) => setAssignmentForm({ ...assignmentForm, position: event.target.value })} /></label></div><label>Notes<textarea value={assignmentForm.notes} onChange={(event) => setAssignmentForm({ ...assignmentForm, notes: event.target.value })} /></label></> : null}
      {view === "RULES" ? <><label>Course<select value={ruleForm.course_id} onChange={(event) => setRuleForm({ ...ruleForm, course_id: event.target.value })}><option value="">Select course</option>{courses.map((course) => <option key={course.id} value={course.id}>{course.course_id} · {course.course_name}</option>)}</select></label><label>Role group<select value={ruleForm.role_group_id} onChange={(event) => setRuleForm({ ...ruleForm, role_group_id: event.target.value })}><option value="">Select group</option>{groups.map((group) => <option key={group.id} value={group.id}>{group.code}</option>)}</select></label><label>Requirement type<input value={ruleForm.requirement_type} onChange={(event) => setRuleForm({ ...ruleForm, requirement_type: event.target.value.toUpperCase() })} /></label><label>Notes<textarea value={ruleForm.notes} onChange={(event) => setRuleForm({ ...ruleForm, notes: event.target.value })} /></label><label><input type="checkbox" checked={ruleForm.is_required} onChange={(event) => setRuleForm({ ...ruleForm, is_required: event.target.checked })} /> Required</label></> : null}
      <div className="tos-actions"><button onClick={() => setFormOpen(false)}>Cancel</button>{view === "GROUPS" ? <button className="primary-chip-btn" disabled={busy || !groupForm.code.trim()} onClick={() => void mutate(async () => { await saveTrainingRoleGroup(groupForm); setGroupForm({ code: "", description: "" }); }, true)}>Save group</button> : null}{view === "PEOPLE" ? <button className="primary-chip-btn" disabled={busy || !assignmentForm.user_id || !assignmentForm.role_group_id} onClick={() => void mutate(async () => { await saveTrainingPersonRole(assignmentForm); setAssignmentForm({ user_id: "", role_group_id: "", department: "", position: "", notes: "" }); }, true)}>Save assignment</button> : null}{view === "RULES" ? <button className="primary-chip-btn" disabled={busy || !ruleForm.course_id || !ruleForm.role_group_id} onClick={() => void mutate(async () => { await saveTrainingRoleRule(ruleForm); setRuleForm({ course_id: "", role_group_id: "", requirement_type: "GENERAL", notes: "", is_required: true }); }, true)}>Save rule</button> : null}</div>
    </div></Drawer>
  </div>;
};

export default TrainingMatrixAdministrationCompact;
