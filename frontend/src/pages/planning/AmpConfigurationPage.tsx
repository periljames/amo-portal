import React, { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getCachedUser, getContext } from "../../services/auth";
import {
  addAmpTask,
  createAmpDraftFromOem,
  createTenantProgramme,
  getAmpComparison,
  listAircraftTypeRevisions,
  listAircraftTypes,
  listTenantProgrammeRevisions,
  listTenantProgrammes,
  publishAmpRevision,
  resolveBaseline,
  updateAmpTask,
  validateAmpRevision,
  type AircraftTypeRevision,
  type AircraftTypeTemplate,
  type AmpComparisonPage,
  type AmpComparisonTask,
  type AmpValidation,
  type BaselineResolution,
  type TenantProgramme,
  type TenantProgrammeRevision,
} from "../../services/tenantAmp";
import { canEditFeature } from "../../utils/roleAccess";
import "../../styles/amp-configuration.css";

type MpdLimit = { counter: string; value: string | number; custom_counter?: string };
type MpdGroup = { phase: string; mode?: string; limits?: MpdLimit[]; reference?: string };
type MpdInterval = { schema?: string; groups?: MpdGroup[]; raw?: string };

const EMPTY_PAGE: AmpComparisonPage = { total: 0, offset: 0, limit: 100, items: [], counts: {} };

function intervalText(value: Record<string, unknown> | null | undefined): string {
  if (!value) return "—";
  const interval = value as MpdInterval;
  if (interval.schema === "MPD_INTERVAL_V1" && Array.isArray(interval.groups)) {
    return interval.groups.map((group) => {
      if (group.mode === "OPPORTUNITY") return `${group.phase}: Opportunity${group.reference ? ` — ${group.reference}` : ""}`;
      const limits = (group.limits || []).map((limit) => `${String(limit.value)} ${limit.counter === "CUSTOM" ? limit.custom_counter || "CUSTOM" : limit.counter}`);
      return `${group.phase}: ${limits.join(group.mode === "WHICHEVER_FIRST" ? " OR " : " + ")}`;
    }).join(" · ");
  }
  const entries = Object.entries(value).filter(([, item]) => item != null);
  return entries.map(([key, item]) => `${String(item)} ${key}`).join(" · ") || "—";
}

function isOpportunity(value: Record<string, unknown> | null | undefined): boolean {
  const interval = value as MpdInterval | undefined;
  return Boolean(interval?.groups?.some((group) => group.mode === "OPPORTUNITY"));
}

function decisionLabel(row: AmpComparisonTask): string {
  if (row.comparison_state === "MORE_RESTRICTIVE") return "More restrictive";
  if (row.comparison_state === "OPERATOR_ADDED") return "AMP added";
  if (row.comparison_state === "LEGACY_UNMAPPED") return "Needs mapping";
  return "Same as OEM";
}

function tone(row: AmpComparisonTask): string {
  if (row.comparison_state === "MORE_RESTRICTIVE") return "amp-chip amp-chip--good";
  if (row.comparison_state === "OPERATOR_ADDED") return "amp-chip amp-chip--info";
  if (row.comparison_state === "LEGACY_UNMAPPED") return "amp-chip amp-chip--danger";
  return "amp-chip";
}

function cloneIntervalWithValues(source: Record<string, unknown>, values: Record<string, string>): Record<string, unknown> {
  const copy = JSON.parse(JSON.stringify(source)) as MpdInterval;
  (copy.groups || []).forEach((group, groupIndex) => {
    (group.limits || []).forEach((limit, limitIndex) => {
      const key = `${groupIndex}:${limitIndex}`;
      if (values[key] != null && values[key].trim()) limit.value = values[key].trim();
    });
  });
  return copy as Record<string, unknown>;
}

const AmpConfigurationPage: React.FC = () => {
  const { amoCode } = useParams();
  const user = getCachedUser();
  const context = getContext();
  const canEdit = canEditFeature(user, "planning.amp", context.department);

  const [programmes, setProgrammes] = useState<TenantProgramme[]>([]);
  const [types, setTypes] = useState<AircraftTypeTemplate[]>([]);
  const [typeRevisions, setTypeRevisions] = useState<AircraftTypeRevision[]>([]);
  const [programmeRevisions, setProgrammeRevisions] = useState<TenantProgrammeRevision[]>([]);
  const [selectedProgrammeId, setSelectedProgrammeId] = useState("");
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [selectedTypeRevisionId, setSelectedTypeRevisionId] = useState("");
  const [selectedRevisionId, setSelectedRevisionId] = useState("");
  const [baseline, setBaseline] = useState<BaselineResolution | null>(null);
  const [comparison, setComparison] = useState<AmpComparisonPage>(EMPTY_PAGE);
  const [validation, setValidation] = useState<AmpValidation | null>(null);
  const [decisionFilter, setDecisionFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const [pageOffset, setPageOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [newProgrammeCode, setNewProgrammeCode] = useState("");
  const [newProgrammeTitle, setNewProgrammeTitle] = useState("");
  const [newProgrammeAuthority, setNewProgrammeAuthority] = useState("KCAA");
  const [draftRevisionCode, setDraftRevisionCode] = useState("");
  const [draftSummary, setDraftSummary] = useState("");
  const [confirmDerivedSeries, setConfirmDerivedSeries] = useState(false);
  const [approvalReference, setApprovalReference] = useState("");

  const [editing, setEditing] = useState<AmpComparisonTask | null>(null);
  const [editValues, setEditValues] = useState<Record<string, string>>({});
  const [editJustification, setEditJustification] = useState("");

  const [showAddTask, setShowAddTask] = useState(false);
  const [addTask, setAddTask] = useState({
    task_code: "",
    title: "",
    ata_chapter: "",
    counter: "FH",
    value: "",
    source_reference: "Tenant AMP",
    justification: "",
  });

  const selectedProgramme = programmes.find((item) => item.id === selectedProgrammeId) || null;
  const selectedRevision = programmeRevisions.find((item) => item.id === selectedRevisionId) || null;
  const publishedTypeRevisions = typeRevisions.filter((item) => item.status === "PUBLISHED");

  const loadSetup = useCallback(async () => {
    try {
      const [programmeRows, typeRows] = await Promise.all([listTenantProgrammes(), listAircraftTypes()]);
      setProgrammes(programmeRows);
      setTypes(typeRows);
      setSelectedProgrammeId((current) => current || programmeRows[0]?.id || "");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "AMP configuration data could not be loaded.");
    }
  }, []);

  useEffect(() => { void loadSetup(); }, [loadSetup]);

  useEffect(() => {
    if (!selectedTemplateId) {
      setTypeRevisions([]);
      setSelectedTypeRevisionId("");
      setBaseline(null);
      return;
    }
    void listAircraftTypeRevisions(selectedTemplateId).then((rows) => {
      setTypeRevisions(rows);
      const published = rows.find((item) => item.status === "PUBLISHED");
      if (published) setSelectedTypeRevisionId((current) => current || published.id);
    }).catch((requestError) => setError(requestError instanceof Error ? requestError.message : "Aircraft type revisions could not be loaded."));
  }, [selectedTemplateId]);

  useEffect(() => {
    if (!selectedProgrammeId) {
      setProgrammeRevisions([]);
      setSelectedRevisionId("");
      return;
    }
    void listTenantProgrammeRevisions(selectedProgrammeId).then((rows) => {
      setProgrammeRevisions(rows);
      setSelectedRevisionId((current) => current && rows.some((row) => row.id === current) ? current : rows[0]?.id || "");
    }).catch((requestError) => setError(requestError instanceof Error ? requestError.message : "AMP revisions could not be loaded."));
  }, [selectedProgrammeId]);

  useEffect(() => {
    if (!selectedTypeRevisionId) {
      setBaseline(null);
      return;
    }
    setConfirmDerivedSeries(false);
    void resolveBaseline(selectedTypeRevisionId).then(setBaseline).catch((requestError) => {
      setBaseline(null);
      setError(requestError instanceof Error ? requestError.message : "OEM baseline could not be resolved.");
    });
  }, [selectedTypeRevisionId]);

  const loadComparison = useCallback(async () => {
    if (!selectedRevisionId) {
      setComparison(EMPTY_PAGE);
      return;
    }
    try {
      const page = await getAmpComparison(selectedRevisionId, {
        search,
        decision: decisionFilter,
        offset: pageOffset,
        limit: 100,
      });
      setComparison(page);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "AMP comparison could not be loaded.");
    }
  }, [decisionFilter, pageOffset, search, selectedRevisionId]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void loadComparison(); }, search ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [loadComparison, search]);

  useEffect(() => {
    setPageOffset(0);
    setValidation(null);
  }, [selectedRevisionId, decisionFilter]);

  async function refreshProgrammeRevisions(selectRevisionId?: string) {
    if (!selectedProgrammeId) return;
    const rows = await listTenantProgrammeRevisions(selectedProgrammeId);
    setProgrammeRevisions(rows);
    if (selectRevisionId) setSelectedRevisionId(selectRevisionId);
  }

  async function handleCreateProgramme() {
    if (!newProgrammeCode.trim() || !newProgrammeTitle.trim()) return;
    setLoading(true); setError(null); setNotice(null);
    try {
      const created = await createTenantProgramme({
        code: newProgrammeCode.trim(),
        title: newProgrammeTitle.trim(),
        authority: newProgrammeAuthority.trim() || null,
      });
      const rows = await listTenantProgrammes();
      setProgrammes(rows);
      setSelectedProgrammeId(created.id);
      setNewProgrammeCode(""); setNewProgrammeTitle("");
      setNotice(`Programme ${created.code} created. Select an aircraft type to inherit its OEM baseline.`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Programme could not be created.");
    } finally { setLoading(false); }
  }

  async function handleCreateDraft() {
    if (!selectedProgrammeId || !selectedTypeRevisionId || !draftRevisionCode.trim()) return;
    setLoading(true); setError(null); setNotice(null);
    try {
      const candidate = baseline?.candidates.length === 1 ? baseline.candidates[0] : null;
      const created = await createAmpDraftFromOem(selectedProgrammeId, {
        revision_code: draftRevisionCode.trim(),
        aircraft_type_revision_id: selectedTypeRevisionId,
        base_content_pack_revision_id: candidate?.revision_id || null,
        change_summary: draftSummary.trim() || null,
        confirm_derived_series: confirmDerivedSeries,
      });
      await refreshProgrammeRevisions(created.id);
      setDraftRevisionCode(""); setDraftSummary("");
      setNotice(`Draft ${created.revision_code} created from the controlled OEM baseline. All OEM requirements currently inherit unchanged.`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "AMP draft could not be created.");
    } finally { setLoading(false); }
  }

  function openTighten(row: AmpComparisonTask) {
    const interval = row.amp_intervals_json as MpdInterval;
    const values: Record<string, string> = {};
    (interval.groups || []).forEach((group, groupIndex) => (group.limits || []).forEach((limit, limitIndex) => {
      values[`${groupIndex}:${limitIndex}`] = String(limit.value);
    }));
    setEditValues(values);
    setEditJustification(row.justification || "");
    setEditing(row);
    setError(null);
  }

  async function saveTighten() {
    if (!editing || !selectedRevisionId || !editing.oem_intervals_json) return;
    setLoading(true); setError(null); setNotice(null);
    try {
      const proposed = cloneIntervalWithValues(editing.oem_intervals_json, editValues);
      await updateAmpTask(selectedRevisionId, editing.id, {
        decision: "TIGHTEN",
        intervals_json: proposed,
        justification: editJustification,
      });
      setEditing(null);
      await Promise.all([loadComparison(), refreshProgrammeRevisions(selectedRevisionId)]);
      setValidation(null);
      setNotice(`${editing.task_code} now uses a tenant interval that is equal to or more restrictive than OEM.`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "AMP interval could not be saved.");
    } finally { setLoading(false); }
  }

  async function restoreOem(row: AmpComparisonTask) {
    if (!selectedRevisionId) return;
    setLoading(true); setError(null);
    try {
      await updateAmpTask(selectedRevisionId, row.id, { decision: "INHERIT" });
      await Promise.all([loadComparison(), refreshProgrammeRevisions(selectedRevisionId)]);
      setValidation(null);
      setNotice(`${row.task_code} restored to the OEM interval.`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "OEM interval could not be restored.");
    } finally { setLoading(false); }
  }

  async function handleAddTask() {
    if (!selectedRevisionId || !addTask.task_code.trim() || !addTask.title.trim() || !addTask.value.trim() || !addTask.justification.trim()) return;
    setLoading(true); setError(null);
    try {
      const counter = addTask.counter;
      await addAmpTask(selectedRevisionId, {
        task_code: addTask.task_code.trim().toUpperCase(),
        title: addTask.title.trim(),
        ata_chapter: addTask.ata_chapter.trim() || null,
        source_reference: addTask.source_reference.trim(),
        justification: addTask.justification.trim(),
        intervals_json: {
          schema: "MPD_INTERVAL_V1",
          groups: [{
            phase: "INTERVAL",
            mode: "SINGLE",
            limits: [{ counter, value: addTask.value.trim() }],
          }],
        },
        effectivity_expression_json: {},
      });
      setShowAddTask(false);
      setAddTask({ task_code: "", title: "", ata_chapter: "", counter: "FH", value: "", source_reference: "Tenant AMP", justification: "" });
      await Promise.all([loadComparison(), refreshProgrammeRevisions(selectedRevisionId)]);
      setValidation(null);
      setNotice("Operator-added AMP requirement created. It remains separate from the immutable OEM baseline.");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "AMP task could not be added.");
    } finally { setLoading(false); }
  }

  async function runValidation() {
    if (!selectedRevisionId) return;
    setLoading(true); setError(null); setNotice(null);
    try {
      const result = await validateAmpRevision(selectedRevisionId);
      setValidation(result);
      await refreshProgrammeRevisions(selectedRevisionId);
      setNotice(result.status === "PASS" ? "AMP passes OEM guardrail validation." : "Validation completed. Resolve the listed issues before publication.");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "AMP validation failed.");
    } finally { setLoading(false); }
  }

  async function publishRevision() {
    if (!selectedRevisionId || !selectedRevision?.content_hash || !approvalReference.trim()) return;
    setLoading(true); setError(null); setNotice(null);
    try {
      await publishAmpRevision(selectedRevisionId, selectedRevision.content_hash, approvalReference.trim());
      await refreshProgrammeRevisions(selectedRevisionId);
      setNotice(`AMP revision ${selectedRevision.revision_code} published against its exact OEM baseline and approval reference.`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "AMP revision could not be published.");
    } finally { setLoading(false); }
  }

  const baselineCandidate = baseline?.candidates.length === 1 ? baseline.candidates[0] : null;
  const totalPages = Math.max(1, Math.ceil(comparison.total / comparison.limit));
  const currentPage = Math.floor(comparison.offset / comparison.limit) + 1;
  const counts = comparison.counts;

  return (
    <DepartmentLayout amoCode={amoCode || "UNKNOWN"} activeDepartment="planning">
      <div className="page amp-config">
        <header className="amp-config__header">
          <div>
            <p className="amp-config__eyebrow">Maintenance Planning · Controlled Programme</p>
            <h1>AMP Configuration</h1>
            <p>Configure the tenant-approved maintenance programme alongside the immutable OEM/MPD baseline. Equal or more restrictive limits are permitted; relaxation of an OEM limit is blocked by the backend.</p>
          </div>
          <div className="amp-config__header-actions">
            <Link className="btn btn-secondary" to={`/maintenance/${amoCode}/planning/task-library`}>OEM baseline</Link>
            <Link className="btn btn-secondary" to={`/maintenance/${amoCode}/planning/dashboard`}>Planning dashboard</Link>
          </div>
        </header>

        {error ? <div className="alert alert--danger amp-config__alert">{error}</div> : null}
        {notice ? <div className="alert alert--success amp-config__alert">{notice}</div> : null}

        <section className="amp-config__setup-grid">
          <article className="card amp-config__card">
            <div className="amp-config__card-heading"><div><span>1</span><h2>Tenant programme</h2></div><small>Tenant-owned, revision controlled</small></div>
            <label>Programme<select value={selectedProgrammeId} onChange={(event) => setSelectedProgrammeId(event.target.value)}><option value="">Select programme</option>{programmes.map((item) => <option key={item.id} value={item.id}>{item.code} — {item.title}</option>)}</select></label>
            {canEdit ? <details className="amp-config__details"><summary>Create programme</summary><div className="amp-config__form-grid"><label>Code<input value={newProgrammeCode} onChange={(event) => setNewProgrammeCode(event.target.value)} placeholder="DHC8-AMP" /></label><label>Title<input value={newProgrammeTitle} onChange={(event) => setNewProgrammeTitle(event.target.value)} placeholder="Dash 8 Approved Maintenance Programme" /></label><label>Authority<input value={newProgrammeAuthority} onChange={(event) => setNewProgrammeAuthority(event.target.value)} /></label></div><button className="btn btn-primary" type="button" onClick={() => void handleCreateProgramme()} disabled={loading}>Create programme</button></details> : null}
          </article>

          <article className="card amp-config__card">
            <div className="amp-config__card-heading"><div><span>2</span><h2>Aircraft type & series</h2></div><small>Controlled catalogue identity</small></div>
            <label>Aircraft type<select value={selectedTemplateId} onChange={(event) => { setSelectedTemplateId(event.target.value); setSelectedTypeRevisionId(""); }}><option value="">Select type</option>{types.map((item) => <option key={item.id} value={item.id}>{item.code} — {item.model}{item.series ? ` · Series ${item.series}` : ""}</option>)}</select></label>
            <label>Published type revision<select value={selectedTypeRevisionId} onChange={(event) => setSelectedTypeRevisionId(event.target.value)} disabled={!selectedTemplateId}><option value="">Select revision</option>{publishedTypeRevisions.map((item) => <option key={item.id} value={item.id}>{item.revision_code} — {item.title}</option>)}</select></label>
          </article>

          <article className="card amp-config__card amp-config__card--baseline">
            <div className="amp-config__card-heading"><div><span>3</span><h2>OEM baseline resolver</h2></div><small>Series-aware, fail closed</small></div>
            {!baseline ? <p className="text-muted">Select a published aircraft type revision to resolve the applicable OEM baseline.</p> : <>
              <dl className="amp-config__facts"><div><dt>Detected series</dt><dd>{baseline.series ? `Series ${baseline.series}` : "Unresolved"}</dd></div><div><dt>Confidence</dt><dd>{baseline.series_confidence}</dd></div><div><dt>Resolver state</dt><dd><span className={`amp-chip ${baseline.state === "RESOLVED" ? "amp-chip--good" : "amp-chip--warning"}`}>{baseline.state.replace(/_/g, " ")}</span></dd></div></dl>
              <p className="text-muted">{baseline.series_reason}</p>
              {baselineCandidate ? <div className="amp-config__baseline-box"><strong>{baselineCandidate.pack_code}</strong><span>OEM baseline Rev {baselineCandidate.revision_code} · {baselineCandidate.family} Series {baselineCandidate.series}</span></div> : <div className="alert alert--warning">{baseline.candidates.length ? `${baseline.candidates.length} OEM baseline candidates were found. Resolve the catalogue identity before creating the AMP.` : "No published OEM baseline matches this aircraft type/series."}</div>}
              {baseline.state === "CONFIRM_DERIVED_SERIES" ? <label className="amp-config__check"><input type="checkbox" checked={confirmDerivedSeries} onChange={(event) => setConfirmDerivedSeries(event.target.checked)} />Confirm the derived Series {baseline.series} identity for this draft. Future catalogue data should store the series explicitly.</label> : null}
            </>}
          </article>
        </section>

        {selectedProgramme ? <section className="card amp-config__revision-strip">
          <div><strong>{selectedProgramme.code}</strong><span>{selectedProgramme.title}</span></div>
          <label>AMP revision<select value={selectedRevisionId} onChange={(event) => setSelectedRevisionId(event.target.value)}><option value="">No revision selected</option>{programmeRevisions.map((item) => <option key={item.id} value={item.id}>Rev {item.revision_code} · {item.status}</option>)}</select></label>
          {canEdit && selectedTypeRevisionId && baselineCandidate ? <details><summary>Create draft from OEM</summary><div className="amp-config__draft-form"><label>Revision code<input value={draftRevisionCode} onChange={(event) => setDraftRevisionCode(event.target.value)} placeholder="01" /></label><label>Change summary<input value={draftSummary} onChange={(event) => setDraftSummary(event.target.value)} placeholder="Initial tenant AMP configuration" /></label><button className="btn btn-primary" onClick={() => void handleCreateDraft()} disabled={loading || (baseline?.state === "CONFIRM_DERIVED_SERIES" && !confirmDerivedSeries)}>Create OEM-backed draft</button></div></details> : null}
        </section> : null}

        {selectedRevision ? <>
          <section className="amp-config__metrics">
            <article><span>OEM baseline</span><strong>{selectedRevision.source_reference}</strong><small>Rev {selectedRevision.source_revision}</small></article>
            <article><span>AMP revision</span><strong>Rev {selectedRevision.revision_code}</strong><small>{selectedRevision.status}</small></article>
            <article><span>Same as OEM</span><strong>{counts.INHERIT || 0}</strong><small>Inherited requirements</small></article>
            <article><span>More restrictive</span><strong>{counts.TIGHTEN || 0}</strong><small>Tenant reductions only</small></article>
            <article><span>AMP added</span><strong>{counts.ADD || 0}</strong><small>Operator requirements</small></article>
          </section>

          <section className="card amp-config__workspace">
            <div className="amp-config__toolbar">
              <div className="amp-config__filters">{["ALL", "INHERIT", "TIGHTEN", "ADD"].map((filter) => <button key={filter} className={decisionFilter === filter ? "is-active" : ""} onClick={() => setDecisionFilter(filter)}>{filter === "ALL" ? "All" : filter === "INHERIT" ? "Same as OEM" : filter === "TIGHTEN" ? "More restrictive" : "AMP added"}<span>{counts[filter] || 0}</span></button>)}</div>
              <div className="amp-config__toolbar-right"><input aria-label="Search AMP tasks" value={search} onChange={(event) => { setSearch(event.target.value); setPageOffset(0); }} placeholder="Search task, ATA, description…" />{canEdit && selectedRevision.status === "DRAFT" ? <button className="btn btn-secondary" onClick={() => setShowAddTask(true)}>Add AMP task</button> : null}<button className="btn btn-primary" onClick={() => void runValidation()} disabled={loading}>Validate AMP</button></div>
            </div>

            <div className="amp-config__table-wrap"><table className="amp-config__table"><thead><tr><th>Requirement</th><th>OEM / MPD</th><th>Tenant AMP</th><th>Decision</th><th>Source / effectivity</th><th></th></tr></thead><tbody>{comparison.items.map((row) => <tr key={row.id} className={row.comparison_state === "MORE_RESTRICTIVE" ? "is-tightened" : row.comparison_state === "LEGACY_UNMAPPED" ? "is-blocked" : ""}><td><strong>{row.task_code}</strong><span>{row.title}</span><small>ATA {row.ata_chapter || "—"}{row.programme_section ? ` · ${row.programme_section}` : ""}{row.is_mandatory ? " · Mandatory source requirement" : ""}</small></td><td><strong>{intervalText(row.oem_intervals_json)}</strong>{row.oem_raw_interval_text ? <small>OEM text: {row.oem_raw_interval_text}</small> : null}</td><td><strong>{intervalText(row.amp_intervals_json)}</strong>{row.justification ? <small>Basis: {row.justification}</small> : null}</td><td><span className={tone(row)}>{decisionLabel(row)}</span></td><td><strong>{row.source_reference}</strong><small>{row.source_revision ? `Rev ${row.source_revision}` : "Tenant source"}{row.raw_effectivity_text ? ` · ${row.raw_effectivity_text}` : ""}</small></td><td>{canEdit && selectedRevision.status === "DRAFT" && row.source_content_task_id ? <div className="amp-config__row-actions">{!isOpportunity(row.oem_intervals_json) ? <button className="btn btn-link" onClick={() => openTighten(row)}>Configure</button> : null}{row.decision === "TIGHTEN" ? <button className="btn btn-link" onClick={() => void restoreOem(row)}>Use OEM</button> : null}</div> : null}</td></tr>)}</tbody></table></div>
            {!comparison.items.length ? <div className="amp-config__empty">No requirements match the current filter.</div> : null}
            <div className="amp-config__pager"><span>{comparison.total ? `${comparison.offset + 1}–${Math.min(comparison.offset + comparison.limit, comparison.total)} of ${comparison.total}` : "0 requirements"}</span><div><button disabled={pageOffset === 0} onClick={() => setPageOffset(Math.max(0, pageOffset - 100))}>Previous</button><span>Page {currentPage} of {totalPages}</span><button disabled={pageOffset + comparison.limit >= comparison.total} onClick={() => setPageOffset(pageOffset + 100)}>Next</button></div></div>
          </section>

          {validation ? <section className={`card amp-config__validation amp-config__validation--${validation.status.toLowerCase()}`}><div className="amp-config__validation-head"><div><span>Engineering validation</span><h2>{validation.status === "PASS" ? "OEM guardrails satisfied" : `${validation.blocking_count} blocking issue(s)`}</h2></div><div><strong>{validation.summary.oem_task_count ?? 0}</strong><span>OEM requirements checked</span></div><div><strong>{validation.summary.tightened_count ?? 0}</strong><span>More restrictive</span></div><div><strong>{validation.summary.operator_added_count ?? 0}</strong><span>AMP added</span></div></div>{validation.issues.length ? <div className="amp-config__issue-list">{validation.issues.map((issue, index) => <div key={`${issue.code}-${index}`} className={`is-${issue.severity.toLowerCase()}`}><strong>{issue.severity} · {issue.code}</strong><span>{issue.task_code ? `${issue.task_code}: ` : ""}{issue.message}</span></div>)}</div> : <p>No blocking or warning conditions were found.</p>}{selectedRevision.status === "DRAFT" && validation.status === "PASS" && canEdit ? <div className="amp-config__publish"><label>Authority / approval reference<input value={approvalReference} onChange={(event) => setApprovalReference(event.target.value)} placeholder="KCAA approval / AMP approval reference" /></label><button className="btn btn-primary" disabled={!approvalReference.trim() || !selectedRevision.content_hash || loading} onClick={() => void publishRevision()}>Publish controlled AMP revision</button></div> : null}</section> : null}
        </> : <section className="card amp-config__empty amp-config__empty--large"><h2>Select or create an AMP revision</h2><p>The workspace will compare each tenant requirement directly with its controlled OEM source.</p></section>}

        {editing ? <div className="amp-modal" role="dialog" aria-modal="true" aria-label={`Configure ${editing.task_code}`}><div className="amp-modal__panel"><header><div><span>OEM → AMP controlled adjustment</span><h2>{editing.task_code}</h2><p>{editing.title}</p></div><button onClick={() => setEditing(null)} aria-label="Close">×</button></header><div className="amp-modal__source"><div><span>OEM limit</span><strong>{intervalText(editing.oem_intervals_json)}</strong></div><div><span>Current AMP</span><strong>{intervalText(editing.amp_intervals_json)}</strong></div></div><div className="amp-modal__limits">{((editing.oem_intervals_json as MpdInterval)?.groups || []).map((group, groupIndex) => <fieldset key={`${group.phase}-${groupIndex}`}><legend>{group.phase} · {group.mode || "SINGLE"}</legend>{(group.limits || []).map((limit, limitIndex) => <label key={`${limit.counter}-${limitIndex}`}>{limit.counter === "CUSTOM" ? limit.custom_counter || "Custom counter" : limit.counter}<input type="number" step="any" min="0" value={editValues[`${groupIndex}:${limitIndex}`] || ""} onChange={(event) => setEditValues((current) => ({ ...current, [`${groupIndex}:${limitIndex}`]: event.target.value }))} /><small>OEM maximum: {String(limit.value)}. AMP may be equal or lower, never higher.</small></label>)}</fieldset>)}</div><label>Controlled basis / justification<textarea rows={3} value={editJustification} onChange={(event) => setEditJustification(event.target.value)} placeholder="Reason for adopting a more restrictive interval…" /></label><div className="amp-modal__actions"><button className="btn btn-secondary" onClick={() => setEditing(null)}>Cancel</button><button className="btn btn-primary" onClick={() => void saveTighten()} disabled={loading || !editJustification.trim()}>Save more restrictive AMP limit</button></div></div></div> : null}

        {showAddTask ? <div className="amp-modal" role="dialog" aria-modal="true" aria-label="Add AMP task"><div className="amp-modal__panel"><header><div><span>Operator-added requirement</span><h2>Add AMP task</h2><p>This creates a tenant requirement. It does not alter or replace an OEM task.</p></div><button onClick={() => setShowAddTask(false)} aria-label="Close">×</button></header><div className="amp-config__form-grid amp-config__form-grid--add"><label>Task code<input value={addTask.task_code} onChange={(event) => setAddTask((current) => ({ ...current, task_code: event.target.value }))} /></label><label>ATA<input value={addTask.ata_chapter} onChange={(event) => setAddTask((current) => ({ ...current, ata_chapter: event.target.value }))} /></label><label className="is-wide">Title<input value={addTask.title} onChange={(event) => setAddTask((current) => ({ ...current, title: event.target.value }))} /></label><label>Counter<select value={addTask.counter} onChange={(event) => setAddTask((current) => ({ ...current, counter: event.target.value }))}>{["FH", "FC", "EH", "APUH", "LANDINGS", "DY", "MO", "YR", "STARTS"].map((counter) => <option key={counter}>{counter}</option>)}</select></label><label>Interval<input type="number" min="0" step="any" value={addTask.value} onChange={(event) => setAddTask((current) => ({ ...current, value: event.target.value }))} /></label><label className="is-wide">Controlled source / AMP reference<input value={addTask.source_reference} onChange={(event) => setAddTask((current) => ({ ...current, source_reference: event.target.value }))} /></label><label className="is-wide">Justification<textarea rows={3} value={addTask.justification} onChange={(event) => setAddTask((current) => ({ ...current, justification: event.target.value }))} /></label></div><div className="amp-modal__actions"><button className="btn btn-secondary" onClick={() => setShowAddTask(false)}>Cancel</button><button className="btn btn-primary" onClick={() => void handleAddTask()} disabled={loading}>Add controlled AMP requirement</button></div></div></div> : null}
      </div>
    </DepartmentLayout>
  );
};

export default AmpConfigurationPage;
