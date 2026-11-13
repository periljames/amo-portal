import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  assignManualRevisionTraining,
  listManualImpactCatalog,
  readManualTrainingImpact,
  type ManualTrainingImpactCourse,
  type ManualTrainingImpactPerson,
  type ManualTrainingImpactResponse,
} from "../../services/qmsManualTrainingImpact";
import { DocumentControlSection } from "./DocumentControlShell";

const errorText = (error: unknown): string =>
  error instanceof Error ? error.message : "The training-impact request could not be verified.";

export default function DocumentRevisionTrainingImpactPanel({
  amoCode, manualId, revisionId, canControl,
}: {
  amoCode: string;
  manualId: string;
  revisionId: string;
  canControl: boolean;
}) {
  const [impact, setImpact] = useState<ManualTrainingImpactResponse | null>(null);
  const [courses, setCourses] = useState<ManualTrainingImpactCourse[]>([]);
  const [people, setPeople] = useState<ManualTrainingImpactPerson[]>([]);
  const [courseId, setCourseId] = useState("");
  const [targetIds, setTargetIds] = useState<string[]>([]);
  const [requiredBy, setRequiredBy] = useState("");
  const [basis, setBasis] = useState("");
  const [mandatory, setMandatory] = useState(true);
  const [blocking, setBlocking] = useState(false);
  const [error, setError] = useState("");
  const [catalogError, setCatalogError] = useState("");
  const [saved, setSaved] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    if (!amoCode || !manualId || !revisionId) return;
    const response = await readManualTrainingImpact(amoCode, manualId, revisionId);
    setImpact(response);
  }, [amoCode, manualId, revisionId]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    readManualTrainingImpact(amoCode, manualId, revisionId)
      .then((result) => { if (active) setImpact(result); })
      .catch((failure: unknown) => { if (active) setError(errorText(failure)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [amoCode, manualId, revisionId]);

  useEffect(() => {
    if (!canControl || !impact?.revision.published_current || !impact.revision.immutable_locked) return;
    let active = true;
    setCatalogError("");
    listManualImpactCatalog(amoCode)
      .then((value) => {
        if (!active) return;
        setCourses(value.courses);
        setPeople(value.people);
      })
      .catch((failure: unknown) => { if (active) setCatalogError(errorText(failure)); });
    return () => { active = false; };
  }, [amoCode, canControl, impact?.revision.published_current, impact?.revision.immutable_locked]);

  const canAssign = canControl && Boolean(impact?.revision.published_current &&
    impact.revision.immutable_locked && impact.revision.immutable_source_sha256);
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canAssign || busy || targetIds.length === 0 || !courseId || basis.trim().length < 12) return;
    setBusy(true);
    setSaved("");
    setError("");
    void assignManualRevisionTraining(amoCode, manualId, revisionId, {
      course_id: courseId,
      target_user_ids: targetIds,
      required_by_date: requiredBy,
      mandatory,
      blocking,
      decision_basis: basis.trim(),
    }).then(async (response) => {
      await refresh();
      setSaved(response.message);
      setTargetIds([]);
      setBasis("");
    }).catch((failure: unknown) => setError(errorText(failure)))
      .finally(() => setBusy(false));
  };

  return <DocumentControlSection title="Training and revision acknowledgement impact"
    description="Training owns course requirements and completion. Document Control owns controlled distribution and read-and-understand evidence. Linking does not constitute approval or publication.">
    {loading ? <p role="status">Loading source-linked training and acknowledgement status…</p> : null}
    {error ? <div role="alert" className="dc-callout dc-callout--warning">
      <strong>Training impact could not be verified.</strong> {error}
      <button type="button" className="dc-button" disabled={busy} onClick={() => void refresh().catch((failure: unknown) => setError(errorText(failure)))}>Retry</button>
    </div> : null}
    {saved ? <p role="status" className="dc-callout">{saved}</p> : null}
    {impact ? <>
      <div className="dc-callout">
        <strong>Exact revision:</strong> {impact.manual.code} · Rev {impact.revision.number} · {impact.revision.status}
        <p>Source checksum: <code>{impact.revision.immutable_source_sha256 || "Unverified"}</code></p>
        <p>Current published/immutable: {impact.revision.published_current && impact.revision.immutable_locked ? "Yes" : "No"}</p>
        {!canAssign ? <p>Assignment is unavailable for this revision or your access level. Drafts, superseded issues and unverified sources cannot create training impact.</p> : null}
      </div>
      <p role="status"><strong>Revision acknowledgement (DMS):</strong> {impact.acknowledgement.acknowledged_count} of {impact.acknowledgement.assigned_count} assigned people acknowledged; {impact.acknowledgement.pending_count} pending. A course completion never substitutes for this acknowledgement.</p>
      <div className="dc-table-wrap">
        <table className="dc-table">
          <thead><tr><th scope="col">Employee</th><th scope="col">Training course</th><th scope="col">Due</th><th scope="col">Requirement</th><th scope="col">Training evidence state</th></tr></thead>
          <tbody>{impact.requirements.map((item) =>
            <tr key={item.id}>
              <td>{people.find((person) => person.id === item.user_id)?.name || item.user_id}</td>
              <td>{courses.find((course) => course.id === item.course_id)?.title || item.course_id}</td>
              <td>{item.required_by_date || "Not specified"}</td>
              <td>{item.is_active ? "Active" : "Inactive"} · {item.is_mandatory ? "Mandatory" : "Optional"}{item.blocking ? " · Blocking" : ""}</td>
              <td>{item.course_completion?.course_record_state.replaceAll("_", " ") || "Not verified"}</td>
            </tr>)}
          </tbody>
        </table>
        {impact.requirements.length === 0 ? <p>No training requirement has been linked to this exact published revision.</p> : null}
      </div>
      {canAssign ? <form className="dc-form" onSubmit={submit}>
        <h3>Assign required training for this controlled revision</h3>
        {catalogError ? <p role="alert">Training catalog: {catalogError}</p> : null}
        <label><span>Course</span><select required value={courseId} onChange={(event) => setCourseId(event.target.value)}>
          <option value="">Select a Training-owned course</option>
          {courses.map((course) => <option key={course.id} value={course.id}>{course.code} · {course.title}</option>)}
        </select></label>
        <label><span>Required by</span><input type="date" required value={requiredBy} onChange={(event) => setRequiredBy(event.target.value)} /></label>
        <fieldset className="wide">
          <legend>Target employees (up to 50)</legend>
          {people.length ? <div className="dc-form__target-list" style={{ maxHeight: "12rem", overflowY: "auto" }}>
            {people.map((person) => <label key={person.id}>
              <input type="checkbox" checked={targetIds.includes(person.id)}
                disabled={!targetIds.includes(person.id) && targetIds.length >= 50}
                onChange={(event) => setTargetIds((current) => event.target.checked ? [...current, person.id] : current.filter((id) => id !== person.id))} />
              <span>{person.name}</span>
            </label>)}
          </div> : <p>No selectable tenant employees were returned.</p>}
        </fieldset>
        <label className="wide"><span>Document change and training-impact decision basis</span>
          <textarea required minLength={12} value={basis} onChange={(event) => setBasis(event.target.value)} />
        </label>
        <label><span><input type="checkbox" checked={mandatory} onChange={(event) => setMandatory(event.target.checked)} /> Mandatory training</span></label>
        <label><span><input type="checkbox" checked={blocking} onChange={(event) => setBlocking(event.target.checked)} /> Blocking competency requirement</span></label>
        <p className="wide">Training approvals, course verification, assignment eligibility and regulatory acknowledgements remain governed by their original modules. Existing Training requirements cannot silently become blocking here.</p>
        <div className="dc-form__actions">
          <button type="submit" className="dc-button dc-button--primary"
            disabled={busy || Boolean(catalogError) || !courseId || !requiredBy || targetIds.length === 0 || basis.trim().length < 12}>
            {busy ? "Linking training requirements…" : "Assign training impact"}
          </button>
        </div>
      </form> : null}
    </> : null}
  </DocumentControlSection>;
}
