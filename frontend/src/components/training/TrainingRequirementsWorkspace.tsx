import React, { useMemo, useState } from "react";
import { BookOpenCheck, ChevronLeft, ChevronRight, FileUp, GitBranch, Network, Pencil, Plus, Search, ShieldCheck, UsersRound } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import Drawer from "../shared/Drawer";
import {
  createTrainingCourse, createTrainingRequirement, listTrainingCourseCatalogue, listTrainingCourses,
  listTrainingRequirements, updateTrainingCourse,
} from "../../services/training";
import { listTrainingPeopleReference, listTrainingReferenceResources, searchTrainingReference } from "../../services/trainingOperating";
import type { TrainingCourseRead } from "../../types/training";
import CurrencySelect from "./CurrencySelect";
import TrainingMatrixAdministration from "./TrainingMatrixAdministration";

type Props = { canManage: boolean; onOpenImport: () => void };

const CATEGORIES = ["HF", "FTS", "EWIS", "SMS", "TYPE", "INTERNAL_TECHNICAL", "QUALITY_SYSTEMS", "REGULATORY", "OTHER"];
const PAGE_SIZE = 20;
const newCourse = () => ({
  course_id: "", course_name: "", category: "OTHER", kind: "RECURRENT", delivery_method: "CLASSROOM",
  frequency_months: "12", planning_lead_days: "45", default_duration_days: "1", nominal_hours: "",
  regulatory_reference: "", default_provider: "", default_facility: "", default_instructor_ids: [] as string[],
  cost_currency: "USD", estimated_unit_cost: "0", default_capacity: "", group_code: "", licence_authority: "",
  prerequisite_course_id: "", assessment_required: false, pass_threshold: "80", attendance_required: true,
  ojt_signoff_required: false, evidence_required: false, certificate_policy: "ON_COMPLETION",
  external_completion_behavior: "REVIEW_REQUIRED", is_mandatory: true, mandatory_for_all: false,
  is_active: true,
});
const newRule = () => ({ course_pk: "", scope: "ALL", department_code: "", job_role: "", user_id: "", effective_from: new Date().toISOString().slice(0, 10), effective_to: "", manual_reference: "", planning_lead_days: "45", assessment_required: false, certificate_required: true, authorization_relevance: "", source_type: "MANUAL", source_id: "", blocking: false, required_by_date: "" });

const TrainingRequirementsWorkspace: React.FC<Props> = ({ canManage, onOpenImport }) => {
  const client = useQueryClient();
  const [courseOpen, setCourseOpen] = useState(false);
  const [editingCourseId, setEditingCourseId] = useState<string | null>(null);
  const [ruleOpen, setRuleOpen] = useState(false);
  const [course, setCourse] = useState(newCourse);
  const [rule, setRule] = useState(newRule);
  const [sourceSearch, setSourceSearch] = useState("");
  const [courseSearchInput, setCourseSearchInput] = useState("");
  const [courseSearch, setCourseSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("ALL");
  const [groupFilter, setGroupFilter] = useState("ALL");
  const [courseOffset, setCourseOffset] = useState(0);
  const [selectorSearch, setSelectorSearch] = useState("");
  const [personSearch, setPersonSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const catalogue = useQuery({
    queryKey: ["training", "course-catalogue-page", courseSearch, categoryFilter, groupFilter, courseOffset],
    queryFn: () => listTrainingCourseCatalogue({
      include_inactive: true, search: courseSearch || undefined,
      category: categoryFilter === "ALL" ? undefined : categoryFilter,
      group_code: groupFilter === "ALL" ? undefined : groupFilter,
      limit: PAGE_SIZE, offset: courseOffset,
    }),
  });
  const selectableCourses = useQuery({ queryKey: ["training", "course-selector", selectorSearch], queryFn: () => listTrainingCourses({ include_inactive: false, search: selectorSearch || undefined, limit: 100 }) });
  const requirements = useQuery({ queryKey: ["training", "requirements"], queryFn: () => listTrainingRequirements({ include_inactive: true, limit: 500 }) });
  const resources = useQuery({ queryKey: ["training", "reference-resources"], queryFn: () => listTrainingReferenceResources(false) });
  const people = useQuery({ queryKey: ["training", "people-selector", personSearch], queryFn: () => listTrainingPeopleReference(personSearch, 100, 0), enabled: ruleOpen && rule.scope === "USER" });
  const sourceResults = useQuery({ queryKey: ["training", "canonical-source", rule.source_type, sourceSearch], queryFn: () => searchTrainingReference(rule.source_type, sourceSearch), enabled: ["DMS", "QMS"].includes(rule.source_type) });
  const courseById = useMemo(() => new Map((selectableCourses.data || []).map((item) => [item.id, item])), [selectableCourses.data]);
  const providers = (resources.data || []).filter((item) => item.resource_type === "PROVIDER");
  const facilities = (resources.data || []).filter((item) => item.resource_type === "LOCATION");
  const instructors = (resources.data || []).filter((item) => item.resource_type === "INSTRUCTOR");

  const openNewCourse = () => { setEditingCourseId(null); setCourse(newCourse()); setCourseOpen(true); };
  const openEditCourse = (item: TrainingCourseRead) => {
    setEditingCourseId(item.id);
    setCourse({
      ...newCourse(), ...item,
      category: String(item.category || "OTHER"), kind: String(item.kind || "RECURRENT"), delivery_method: String(item.delivery_method || "CLASSROOM"),
      frequency_months: item.frequency_months == null ? "" : String(item.frequency_months), planning_lead_days: String(item.planning_lead_days ?? 45),
      default_duration_days: String(item.default_duration_days ?? 1), nominal_hours: item.nominal_hours == null ? "" : String(item.nominal_hours),
      pass_threshold: String(item.pass_threshold ?? 80), estimated_unit_cost: String(item.estimated_unit_cost ?? 0), default_capacity: item.default_capacity == null ? "" : String(item.default_capacity),
      default_provider: item.default_provider || "", default_facility: item.default_facility || "", default_instructor_ids: item.default_instructor_ids || [],
      group_code: item.group_code || "", licence_authority: item.licence_authority || "", prerequisite_course_id: item.prerequisite_course_id || "",
      regulatory_reference: item.regulatory_reference || "", cost_currency: item.cost_currency || "USD", assessment_required: Boolean(item.assessment_required),
      attendance_required: item.attendance_required !== false, ojt_signoff_required: Boolean(item.ojt_signoff_required), evidence_required: Boolean(item.evidence_required),
      certificate_policy: String(item.certificate_policy || "ON_COMPLETION"), external_completion_behavior: String(item.external_completion_behavior || "REVIEW_REQUIRED"),
      is_mandatory: Boolean(item.is_mandatory), mandatory_for_all: Boolean(item.mandatory_for_all),
    });
    setCourseOpen(true);
  };

  const saveCourse = async () => {
    setBusy(true); setError(null);
    try {
      const payload = {
        ...course, frequency_months: course.frequency_months ? Number(course.frequency_months) : null,
        planning_lead_days: Number(course.planning_lead_days), default_duration_days: Number(course.default_duration_days),
        nominal_hours: course.nominal_hours ? Number(course.nominal_hours) : null, pass_threshold: Number(course.pass_threshold),
        estimated_unit_cost: Number(course.estimated_unit_cost || 0), default_capacity: course.default_capacity ? Number(course.default_capacity) : null,
        prerequisite_course_id: course.prerequisite_course_id || null, regulatory_reference: course.regulatory_reference || null,
        default_provider: course.default_provider || null, default_facility: course.default_facility || null,
        group_code: course.group_code || null, licence_authority: course.licence_authority || null, is_active: course.is_active,
      };
      if (editingCourseId) await updateTrainingCourse(editingCourseId, payload); else await createTrainingCourse(payload);
      setCourse(newCourse()); setEditingCourseId(null); setCourseOpen(false); await client.invalidateQueries({ queryKey: ["training"] });
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Course could not be saved."); } finally { setBusy(false); }
  };

  const saveRule = async () => {
    setBusy(true); setError(null);
    try {
      await createTrainingRequirement({ ...rule, course_pk: rule.course_pk, scope: rule.scope as "ALL" | "DEPARTMENT" | "JOB_ROLE" | "USER", department_code: rule.scope === "DEPARTMENT" ? rule.department_code : null, job_role: rule.scope === "JOB_ROLE" ? rule.job_role : null, user_id: rule.scope === "USER" ? rule.user_id : null, effective_to: rule.effective_to || null, planning_lead_days: Number(rule.planning_lead_days), required_by_date: rule.required_by_date || null, source_id: rule.source_id || null, manual_reference: rule.manual_reference || null, authorization_relevance: rule.authorization_relevance || null, is_active: true, is_mandatory: true });
      setRule(newRule()); setRuleOpen(false); await client.invalidateQueries({ queryKey: ["training"] });
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Requirement could not be saved."); } finally { setBusy(false); }
  };

  return <div className="tos-stack training-route-workspace">
    <section className="tos-card tos-route-commandbar"><div><p className="tos-kicker">Requirement authority</p><h2>Courses, applicability and controlled sources</h2><p>Maintain one effective graph from course policy through role/person scope to QMS or DMS provenance.</p></div><button disabled={!canManage} onClick={onOpenImport}><FileUp size={16} /> Import</button><button disabled={!canManage} onClick={openNewCourse}><Plus size={16} /> Course</button><button disabled={!canManage || !selectableCourses.data?.length} onClick={() => setRuleOpen(true)}><Plus size={16} /> Requirement</button></section>
    {error ? <div className="tos-banner tos-banner--error">{error}<button onClick={() => setError(null)}>×</button></div> : null}
    <section className="tos-card tos-process-rail" aria-label="Requirement lifecycle"><span><BookOpenCheck size={17} /> Course policy</span><i>→</i><span><GitBranch size={17} /> Prerequisites</span><i>→</i><span><UsersRound size={17} /> Scope</span><i>→</i><span><ShieldCheck size={17} /> Review</span><i>→</i><span><Network size={17} /> Plan impact</span></section>

    <section className="tos-card tos-register-card">
      <div className="tos-card__heading"><div><h3>Course catalogue</h3><small>{catalogue.data?.total ?? "Unknown"} tenant-owned policies</small></div></div>
      <div className="tos-catalogue-toolbar"><form onSubmit={(event) => { event.preventDefault(); setCourseSearch(courseSearchInput.trim()); setCourseOffset(0); }}><Search size={16} /><input value={courseSearchInput} onChange={(event) => setCourseSearchInput(event.target.value)} placeholder="Search course, title or provider" /></form><div className="tos-pill-row">{["ALL", ...Object.keys(catalogue.data?.category_counts || {})].map((item) => <button key={item} className={categoryFilter === item ? "is-active" : ""} onClick={() => { setCategoryFilter(item); setCourseOffset(0); }}>{item.replaceAll("_", " ")} {item === "ALL" ? catalogue.data?.total ?? 0 : catalogue.data?.category_counts[item] ?? 0}</button>)}</div>{Object.keys(catalogue.data?.group_counts || {}).length ? <div className="tos-pill-row"><button className={groupFilter === "ALL" ? "is-active" : ""} onClick={() => { setGroupFilter("ALL"); setCourseOffset(0); }}>All groups</button>{Object.entries(catalogue.data?.group_counts || {}).map(([group, count]) => <button key={group} className={groupFilter === group ? "is-active" : ""} onClick={() => { setGroupFilter(group); setCourseOffset(0); }}>{group} {count}</button>)}</div> : null}</div>
      {catalogue.isError ? <div className="tos-empty"><strong>Catalogue unavailable</strong><span>No zero count is being inferred.</span></div> : <div className="tos-table-wrap"><table className="tos-table"><thead><tr><th>Course</th><th>Delivery controls</th><th>Cost / capacity</th><th>Recurrence</th><th>Completion gates</th><th>State</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{(catalogue.data?.items || []).map((item) => <tr key={item.id}><td><strong>{item.course_id}</strong><small>{item.course_name}{item.group_code ? ` · ${item.group_code}` : ""}</small></td><td>{item.default_provider || "Provider not set"}<small>{item.default_facility || "Facility not set"} · {item.default_instructor_ids?.length || 0} instructor(s)</small></td><td>{item.cost_currency || "USD"} {Number(item.estimated_unit_cost || 0).toLocaleString()}<small>{item.default_capacity ? `${item.default_capacity} seats` : "Capacity not set"}</small></td><td>{item.frequency_months ? `${item.frequency_months} months` : "One-off"}<small>{item.planning_lead_days || 45} day lead{item.licence_authority ? ` · renews ${item.licence_authority.replaceAll("_", " ")} licence` : ""}</small></td><td>{[item.attendance_required !== false && "Attendance", item.assessment_required && "Assessment", item.ojt_signoff_required && "OJT", item.evidence_required && "Evidence"].filter(Boolean).join(" · ") || "Policy not set"}</td><td><span className={`tos-pill ${item.is_active === false ? "tos-pill--warning" : "tos-pill--ok"}`}>{item.is_active === false ? "RETIRED" : "ACTIVE"}</span></td><td><button className="tos-icon-button" title="Edit course" aria-label={`Edit ${item.course_name}`} disabled={!canManage} onClick={() => openEditCourse(item)}><Pencil size={16} /></button></td></tr>)}</tbody></table></div>}
      {catalogue.data ? <div className="tos-pagination"><span>{catalogue.data.total ? `${courseOffset + 1}–${Math.min(courseOffset + PAGE_SIZE, catalogue.data.total)} of ${catalogue.data.total}` : "0 courses"}</span><button className="tos-icon-button" disabled={courseOffset === 0 || catalogue.isFetching} onClick={() => setCourseOffset(Math.max(0, courseOffset - PAGE_SIZE))}><ChevronLeft size={18} /></button><button className="tos-icon-button" disabled={!catalogue.data.has_more || catalogue.isFetching} onClick={() => setCourseOffset(courseOffset + PAGE_SIZE)}><ChevronRight size={18} /></button></div> : null}
    </section>

    <details className="tos-disclosure" open><summary><span><Network size={18} /><strong>Requirement revisions</strong></span><small>{requirements.data?.length ?? "Unknown"} effective and historical rules</small></summary><div className="tos-disclosure__body"><div className="tos-list">{(requirements.data || []).map((item) => <div key={item.id}><div><strong>{courseById.get(item.course_id)?.course_id || item.course_id} · {item.scope}</strong><small>{item.department_code || item.job_role || item.user_id || "All active personnel"} · {item.manual_reference || "No manual reference"}{item.source_type ? ` · ${item.source_type}:${item.source_id || "unresolved"}` : ""}</small></div><span className={`tos-pill ${item.blocking ? "tos-pill--warning" : "tos-pill--ok"}`}>{item.blocking ? "BLOCKING" : item.is_active === false ? "RETIRED" : "EFFECTIVE"}</span></div>)}</div></div></details>
    <details className="tos-disclosure"><summary><span><UsersRound size={18} /><strong>Role groups and matrix</strong></span><small>Canonical user assignments and course rules</small></summary><div className="tos-disclosure__body"><TrainingMatrixAdministration canManage={canManage} /></div></details>

    <Drawer title={editingCourseId ? "Edit course policy" : "Create course policy"} isOpen={courseOpen} onClose={() => setCourseOpen(false)} panelClassName="training-form-drawer"><div className="tos-drawer-form"><div className="tos-form-grid"><label>Course code<input value={course.course_id} disabled={Boolean(editingCourseId)} onChange={(e) => setCourse({ ...course, course_id: e.target.value.toUpperCase() })} /></label><label>Course title<input value={course.course_name} onChange={(e) => setCourse({ ...course, course_name: e.target.value })} /></label><label>Category<select value={course.category} onChange={(e) => setCourse({ ...course, category: e.target.value })}>{CATEGORIES.map((item) => <option key={item}>{item}</option>)}</select></label><label>Tenant group<input value={course.group_code} onChange={(e) => setCourse({ ...course, group_code: e.target.value.toUpperCase() })} placeholder="TECHNICAL / CORPORATE" /></label><label>Kind<select value={course.kind} onChange={(e) => setCourse({ ...course, kind: e.target.value })}>{["INITIAL", "CONTINUATION", "RECURRENT", "REFRESHER", "OTHER"].map((item) => <option key={item}>{item}</option>)}</select></label><label>Delivery<select value={course.delivery_method} onChange={(e) => setCourse({ ...course, delivery_method: e.target.value })}>{["CLASSROOM", "ONLINE", "OJT", "MIXED", "OTHER"].map((item) => <option key={item}>{item}</option>)}</select></label><label>Provider<select value={course.default_provider} onChange={(e) => setCourse({ ...course, default_provider: e.target.value })}><option value="">Select provider</option>{course.default_provider && !providers.some((item) => item.name === course.default_provider) ? <option value={course.default_provider}>{course.default_provider} · existing value</option> : null}{providers.map((item) => <option key={item.id} value={item.name}>{item.code} · {item.name}</option>)}</select></label><label>Facility / location<select value={course.default_facility} onChange={(e) => setCourse({ ...course, default_facility: e.target.value })}><option value="">Select facility</option>{course.default_facility && !facilities.some((item) => item.name === course.default_facility) ? <option value={course.default_facility}>{course.default_facility} · existing value</option> : null}{facilities.map((item) => <option key={item.id} value={item.name}>{item.code} · {item.name}</option>)}</select></label><label className="tos-span-2">Instructor(s)<select multiple value={course.default_instructor_ids} onChange={(event) => setCourse({ ...course, default_instructor_ids: Array.from(event.currentTarget.selectedOptions, (option) => option.value) })}>{course.default_instructor_ids.filter((id) => !instructors.some((item) => item.id === id)).map((id) => <option key={id} value={id}>{id} · existing reference</option>)}{instructors.map((item) => <option key={item.id} value={item.id}>{item.code} · {item.name}</option>)}</select><small>Use Ctrl/Cmd to select more than one.</small></label><label>Cost currency<CurrencySelect value={course.cost_currency} onChange={(currency) => setCourse({ ...course, cost_currency: currency })} /></label><label>Estimated cost / trainee<input type="number" min="0" step="0.01" value={course.estimated_unit_cost} onChange={(e) => setCourse({ ...course, estimated_unit_cost: e.target.value })} /></label><label>Default capacity<input type="number" min="1" value={course.default_capacity} onChange={(e) => setCourse({ ...course, default_capacity: e.target.value })} /></label><label>Recurrence months<input type="number" min="0" value={course.frequency_months} onChange={(e) => setCourse({ ...course, frequency_months: e.target.value })} /></label><label>Planning lead days<input type="number" min="1" value={course.planning_lead_days} onChange={(e) => setCourse({ ...course, planning_lead_days: e.target.value })} /></label><label>Duration days<input type="number" min="0" value={course.default_duration_days} onChange={(e) => setCourse({ ...course, default_duration_days: e.target.value })} /></label><label>Nominal hours<input type="number" min="0" value={course.nominal_hours} onChange={(e) => setCourse({ ...course, nominal_hours: e.target.value })} /></label><label>Licence renewed by this course<select value={course.licence_authority} onChange={(e) => setCourse({ ...course, licence_authority: e.target.value })}><option value="">Not a licence renewal</option><option value="KCAA">Kenya AMEL (KCAA)</option><option value="ETHIOPIAN_CAA">Ethiopia AMEL</option><option value="GHANA_CAA">Ghana AMEL</option></select></label><label>Prerequisite<input value={selectorSearch} onChange={(event) => setSelectorSearch(event.target.value)} placeholder="Search available courses" /><select value={course.prerequisite_course_id} onChange={(e) => setCourse({ ...course, prerequisite_course_id: e.target.value })}><option value="">None</option>{(selectableCourses.data || []).filter((item) => item.id !== editingCourseId).map((item) => <option key={item.id} value={item.course_id}>{item.course_id} · {item.course_name}</option>)}</select></label><label className="tos-span-2">Regulatory / manual reference<input value={course.regulatory_reference} onChange={(e) => setCourse({ ...course, regulatory_reference: e.target.value })} /></label></div><div className="tos-check-grid"><label><input type="checkbox" checked={course.is_active} onChange={(e) => setCourse({ ...course, is_active: e.target.checked })} /> Active course</label><label><input type="checkbox" checked={course.attendance_required} onChange={(e) => setCourse({ ...course, attendance_required: e.target.checked })} /> Attendance gate</label><label><input type="checkbox" checked={course.assessment_required} onChange={(e) => setCourse({ ...course, assessment_required: e.target.checked })} /> Assessment gate</label><label><input type="checkbox" checked={course.ojt_signoff_required} onChange={(e) => setCourse({ ...course, ojt_signoff_required: e.target.checked })} /> OJT sign-off</label><label><input type="checkbox" checked={course.evidence_required} onChange={(e) => setCourse({ ...course, evidence_required: e.target.checked })} /> Evidence required</label><label><input type="checkbox" checked={course.certificate_policy === "ON_COMPLETION"} onChange={(e) => setCourse({ ...course, certificate_policy: e.target.checked ? "ON_COMPLETION" : "NONE" })} /> Certificate on completion</label></div><div className="tos-actions"><button onClick={() => setCourseOpen(false)}>Cancel</button><button className="primary-chip-btn" disabled={busy || !course.course_id || !course.course_name} onClick={() => void saveCourse()}>Save course</button></div></div></Drawer>

    <Drawer title="Create requirement revision" isOpen={ruleOpen} onClose={() => setRuleOpen(false)} panelClassName="training-form-drawer"><div className="tos-drawer-form"><label>Search course<input value={selectorSearch} onChange={(event) => setSelectorSearch(event.target.value)} /></label><label>Course<select value={rule.course_pk} onChange={(e) => setRule({ ...rule, course_pk: e.target.value })}><option value="">Select course</option>{(selectableCourses.data || []).map((item) => <option key={item.id} value={item.id}>{item.course_id} · {item.course_name}</option>)}</select></label><label>Applies to<select value={rule.scope} onChange={(e) => setRule({ ...rule, scope: e.target.value, user_id: "" })}><option>ALL</option><option>DEPARTMENT</option><option>JOB_ROLE</option><option>USER</option></select></label>{rule.scope === "DEPARTMENT" ? <label>Department code<input value={rule.department_code} onChange={(e) => setRule({ ...rule, department_code: e.target.value.toUpperCase() })} /></label> : null}{rule.scope === "JOB_ROLE" ? <label>Position / job role<input value={rule.job_role} onChange={(e) => setRule({ ...rule, job_role: e.target.value })} /></label> : null}{rule.scope === "USER" ? <><label>Find portal user<input value={personSearch} onChange={(event) => setPersonSearch(event.target.value)} placeholder="Name, staff code or role" /></label><label>Canonical portal user<select value={rule.user_id} onChange={(e) => setRule({ ...rule, user_id: e.target.value })}><option value="">Select existing user</option>{(people.data || []).map((person) => <option key={person.id} value={person.id}>{person.full_name} · {person.staff_code || person.id}</option>)}</select><small>This links the requirement to User Management; no training-only profile is created.</small></label></> : null}<div className="tos-form-grid"><label>Effective from<input type="date" value={rule.effective_from} onChange={(e) => setRule({ ...rule, effective_from: e.target.value })} /></label><label>Effective to<input type="date" value={rule.effective_to} onChange={(e) => setRule({ ...rule, effective_to: e.target.value })} /></label><label>Planning lead days<input type="number" min="1" value={rule.planning_lead_days} onChange={(e) => setRule({ ...rule, planning_lead_days: e.target.value })} /></label><label>Controlled source<select value={rule.source_type} onChange={(e) => setRule({ ...rule, source_type: e.target.value, source_id: "" })}><option>MANUAL</option><option>DMS</option><option>QMS</option></select></label></div>{["DMS", "QMS"].includes(rule.source_type) ? <label>Search controlled source<input value={sourceSearch} onChange={(e) => setSourceSearch(e.target.value)} /><select value={rule.source_id} onChange={(e) => setRule({ ...rule, source_id: e.target.value })}><option value="">Select matching source</option>{(sourceResults.data || []).map((item) => <option key={item.id} value={item.id}>{item.code} · {item.label}</option>)}</select></label> : null}<label>Manual reference<input value={rule.manual_reference} onChange={(e) => setRule({ ...rule, manual_reference: e.target.value })} /></label><label>Authorization relevance<textarea value={rule.authorization_relevance} onChange={(e) => setRule({ ...rule, authorization_relevance: e.target.value })} /></label><label><input type="checkbox" checked={rule.blocking} onChange={(e) => setRule({ ...rule, blocking: e.target.checked })} /> Block completion/publication while the controlled source gate is open</label><div className="tos-actions"><button onClick={() => setRuleOpen(false)}>Cancel</button><button className="primary-chip-btn" disabled={busy || !rule.course_pk || (rule.scope !== "ALL" && !rule.department_code && !rule.job_role && !rule.user_id)} onClick={() => void saveRule()}>Save requirement</button></div></div></Drawer>
  </div>;
};

export default TrainingRequirementsWorkspace;
