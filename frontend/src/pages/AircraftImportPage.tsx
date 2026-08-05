import React, { FormEvent, useEffect, useMemo, useState } from "react";
import {
  inductionApi,
  type Catalogue,
  type InductionJob,
  type InductionRow,
  type InductionWorkspace,
  type MappingProfile,
  type TenantProgram,
  type TenantProgramRevision,
} from "../services/aircraftInduction";
import "./AircraftInductionPage.css";

type Tab = "inductions" | "catalogue" | "programmes" | "mappings";

const DATASETS = [
  "AIRCRAFT_MASTER", "CONFIGURATION", "COMPONENTS", "LLP_STATUS", "UTILISATION",
  "AMP_STATUS", "AD_STATUS", "SB_STATUS", "MODIFICATIONS", "REPAIRS", "DEFERRALS",
  "MAINTENANCE_HISTORY", "DOCUMENT_INDEX",
];
const STEPS = ["IDENTIFY", "MAP", "VALIDATE", "EFFECTIVITY", "REVIEW", "ACTIVATE"];

function Field({ label, full, children }: { label: string; full?: boolean; children: React.ReactNode }) {
  return <div className={`induction-field${full ? " full" : ""}`}><label>{label}</label>{children}</div>;
}

function StatusBadge({ value }: { value?: string | null }) {
  const text = (value || "UNKNOWN").toUpperCase();
  const cls = /ACTIVE|APPROVED|PUBLISHED|VALIDATED|RESOLVED|PASS|VALID/.test(text)
    ? "pass"
    : /FAILED|INVALID|REJECTED|BLOCKED/.test(text) ? "fail" : "warn";
  return <span className={`induction-badge ${cls}`}>{text.replaceAll("_", " ")}</span>;
}

function ErrorNotice({ error }: { error: any }) {
  if (!error) return null;
  const details = error?.detail?.blockers || error?.detail?.errors || error?.detail?.row_ids;
  return <div className="induction-notice error"><strong>{error.message || "Request failed"}</strong>{Array.isArray(details) && <ul>{details.slice(0, 12).map((item: any, index: number) => <li key={index}>{String(item)}</li>)}</ul>}</div>;
}

export default function AircraftImportPage() {
  const [tab, setTab] = useState<Tab>("inductions");
  const [catalogue, setCatalogue] = useState<Catalogue>({ families: [], types: [], variants: [], templates: [], revisions: [] });
  const [programs, setPrograms] = useState<TenantProgram[]>([]);
  const [profiles, setProfiles] = useState<MappingProfile[]>([]);
  const [jobs, setJobs] = useState<InductionJob[]>([]);
  const [selectedJobId, setSelectedJobId] = useState("");
  const [workspace, setWorkspace] = useState<InductionWorkspace | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<any>(null);
  const [message, setMessage] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [sourceSystem, setSourceSystem] = useState("GENERIC_EXCEL");
  const [forcedDataset, setForcedDataset] = useState("");
  const [activationNote, setActivationNote] = useState("");
  const [openingHours, setOpeningHours] = useState("");
  const [openingCycles, setOpeningCycles] = useState("");

  const [jobDraft, setJobDraft] = useState({ induction_ref: "", serial_number: "", registration: "", variant_id: "", template_revision_id: "", program_id: "", program_revision_id: "", source_system: "GENERIC_EXCEL", source_reference: "" });
  const [jobProgramRevisions, setJobProgramRevisions] = useState<TenantProgramRevision[]>([]);

  const [familyDraft, setFamilyDraft] = useState({ code: "", name: "", manufacturer: "", description: "" });
  const [typeDraft, setTypeDraft] = useState({ family_id: "", type_code: "", name: "", type_certificate_number: "", authority: "", description: "" });
  const [variantDraft, setVariantDraft] = useState({ aircraft_type_id: "", variant_code: "", model_code: "", marketing_name: "" });
  const [templateDraft, setTemplateDraft] = useState({ variant_id: "", code: "", title: "", visibility: "GLOBAL", description: "" });
  const [revisionDraft, setRevisionDraft] = useState({ template_id: "", revision_code: "", effective_date: "", source_reference: "", release_notes: "" });
  const [selectedRevisionId, setSelectedRevisionId] = useState("");
  const [revisionWorkspace, setRevisionWorkspace] = useState<any>(null);
  const [sourceDraft, setSourceDraft] = useState({ document_type: "MPD", reference: "", revision: "", issue_date: "", authority: "", source_uri: "" });
  const [nodeDraft, setNodeDraft] = useState({ node_key: "", parent_node_key: "", node_type: "POSITION", position_code: "", title: "", ata_chapter: "", minimum_quantity: "1", maximum_quantity: "1", allowable_parts_json: "[]", effectivity_json: "{}" });
  const [requirementDraft, setRequirementDraft] = useState({ requirement_key: "", category: "AIRFRAME", ata_chapter: "", task_code: "", title: "", governing_logic: "WHICHEVER_FIRST", interval_json: "{}", threshold_json: "{}", effectivity_json: "{}", source_reference: "" });

  const [programDraft, setProgramDraft] = useState({ variant_id: "", code: "", title: "", authority: "KCAA", approval_reference: "" });
  const [selectedProgramId, setSelectedProgramId] = useState("");
  const [programRevisions, setProgramRevisions] = useState<TenantProgramRevision[]>([]);
  const [programRevisionDraft, setProgramRevisionDraft] = useState({ base_template_revision_id: "", revision_code: "", effective_date: "", approval_reference: "", approval_date: "", notes: "" });
  const [overrideDraft, setOverrideDraft] = useState({ program_revision_id: "", requirement_key: "", action: "MODIFY", patch_json: "{}", effectivity_json: "{}", justification: "", authority_reference: "" });

  const [mappingDraft, setMappingDraft] = useState({ scope: "TENANT", name: "", source_system: "GENERIC_EXCEL", source_version: "", dataset: "AIRCRAFT_MASTER", fingerprint: "", header_signature_json: "[]", mapping_json: "{}", transformations_json: "{}", defaults_json: "{}", validation_json: "{}" });

  async function refresh() {
    const [nextCatalogue, nextPrograms, nextProfiles, nextJobs] = await Promise.all([
      inductionApi.catalogue(), inductionApi.programs(), inductionApi.mappingProfiles(), inductionApi.jobs(),
    ]);
    setCatalogue(nextCatalogue); setPrograms(nextPrograms); setProfiles(nextProfiles); setJobs(nextJobs);
    if (!selectedJobId && nextJobs[0]) setSelectedJobId(nextJobs[0].id);
  }

  async function run<T>(operation: () => Promise<T>, success?: string) {
    setBusy(true); setError(null); setMessage("");
    try { const value = await operation(); if (success) setMessage(success); await refresh(); return value; }
    catch (err) { setError(err); throw err; }
    finally { setBusy(false); }
  }

  useEffect(() => { refresh().catch(setError); }, []);
  useEffect(() => { if (selectedJobId) inductionApi.workspace(selectedJobId).then(setWorkspace).catch(setError); else setWorkspace(null); }, [selectedJobId, jobs]);
  useEffect(() => { if (jobDraft.program_id) inductionApi.programRevisions(jobDraft.program_id).then(setJobProgramRevisions).catch(setError); else setJobProgramRevisions([]); }, [jobDraft.program_id]);
  useEffect(() => { if (selectedProgramId) inductionApi.programRevisions(selectedProgramId).then(setProgramRevisions).catch(setError); else setProgramRevisions([]); }, [selectedProgramId, programs]);
  useEffect(() => { if (selectedRevisionId) inductionApi.templateRevision(selectedRevisionId).then(setRevisionWorkspace).catch(setError); else setRevisionWorkspace(null); }, [selectedRevisionId, catalogue.revisions]);

  const selectedVariant = catalogue.variants.find((item) => item.id === jobDraft.variant_id);
  const variantTemplates = catalogue.templates.filter((item) => item.variant_id === jobDraft.variant_id);
  const variantTemplateIds = new Set(variantTemplates.map((item) => item.id));
  const variantRevisions = catalogue.revisions.filter((item) => variantTemplateIds.has(item.template_id) && item.status === "PUBLISHED");
  const variantPrograms = programs.filter((item) => item.variant_id === jobDraft.variant_id);
  const compatibleProgramRevisions = jobProgramRevisions.filter((item) => item.status === "APPROVED" && (!jobDraft.template_revision_id || item.base_template_revision_id === jobDraft.template_revision_id));
  const currentStepIndex = workspace ? Math.max(0, STEPS.indexOf(workspace.induction.current_step)) : 0;
  const issueRows = useMemo(() => workspace ? Object.values(workspace.rows_by_dataset).flat().filter((row) => row.errors_json.length || row.warnings_json.length || ["MAPPING_REQUIRED", "INVALID"].includes(row.status)) : [], [workspace]);

  async function submitJob(event: FormEvent) {
    event.preventDefault();
    const payload = { ...jobDraft }; delete (payload as any).program_id;
    const created = await run(() => inductionApi.createJob(payload), "Induction job created");
    if (created) setSelectedJobId((created as InductionJob).id);
  }

  async function uploadFiles() {
    if (!workspace || !files.length) return;
    await run(() => inductionApi.upload(workspace.induction.id, files, sourceSystem, forcedDataset || undefined), "Source datasets staged");
    setFiles([]);
    setWorkspace(await inductionApi.workspace(workspace.induction.id));
  }

  async function jobAction(action: "validate" | "effectivity" | "approve" | "activate") {
    if (!workspace) return;
    const id = workspace.induction.id;
    if (action === "validate") await run(() => inductionApi.validate(id), "Validation completed");
    if (action === "effectivity") await run(() => inductionApi.resolveEffectivity(id), "Effectivity and configuration conformity resolved");
    if (action === "approve") await run(() => inductionApi.approve(id), "Induction approved");
    if (action === "activate") {
      const counters = [] as any[];
      if (openingHours !== "") counters.push({ counter_code: "AIRFRAME_HOURS", unit: "H", value: Number(openingHours) });
      if (openingCycles !== "") counters.push({ counter_code: "AIRFRAME_CYCLES", unit: "C", value: Number(openingCycles) });
      await run(() => inductionApi.activate(id, activationNote, counters), "Aircraft activated from approved universal baseline");
    }
    setWorkspace(await inductionApi.workspace(id));
  }

  const parseJson = (value: string, label: string) => { try { return JSON.parse(value || "{}"); } catch { throw new Error(`${label} must contain valid JSON`); } };

  return <div className="induction-page">
    <header className="induction-header">
      <div><h1>Aircraft Type Library & Induction</h1><p>Build the aircraft type once, adapt the approved programme per operator, then induct each tail from its actual configuration, utilisation and records.</p></div>
      <StatusBadge value="Universal baseline" />
    </header>
    <nav className="induction-tabs">
      {(["inductions", "catalogue", "programmes", "mappings"] as Tab[]).map((item) => <button key={item} className={tab === item ? "active" : ""} onClick={() => setTab(item)}>{item === "inductions" ? "Tail Inductions" : item === "catalogue" ? "Type Library" : item === "programmes" ? "Tenant Programmes" : "Source Mappings"}</button>)}
    </nav>
    <ErrorNotice error={error} />{message && <div className="induction-notice success">{message}</div>}

    {tab === "inductions" && <div className="induction-grid">
      <aside className="induction-stack">
        <section className="induction-card"><h2>New tail induction</h2><form className="induction-form-grid" onSubmit={submitJob}>
          <Field label="Induction reference"><input required value={jobDraft.induction_ref} onChange={(e) => setJobDraft({ ...jobDraft, induction_ref: e.target.value })} /></Field>
          <Field label="Source system"><input value={jobDraft.source_system} onChange={(e) => setJobDraft({ ...jobDraft, source_system: e.target.value })} /></Field>
          <Field label="Aircraft serial / MSN"><input required value={jobDraft.serial_number} onChange={(e) => setJobDraft({ ...jobDraft, serial_number: e.target.value.toUpperCase() })} /></Field>
          <Field label="Registration"><input required value={jobDraft.registration} onChange={(e) => setJobDraft({ ...jobDraft, registration: e.target.value.toUpperCase() })} /></Field>
          <Field label="Aircraft variant" full><select required value={jobDraft.variant_id} onChange={(e) => setJobDraft({ ...jobDraft, variant_id: e.target.value, template_revision_id: "", program_id: "", program_revision_id: "" })}><option value="">Select variant</option>{catalogue.variants.map((item) => <option key={item.id} value={item.id}>{item.model_code} — {item.marketing_name || item.variant_code}</option>)}</select></Field>
          <Field label="Published type revision" full><select required value={jobDraft.template_revision_id} onChange={(e) => setJobDraft({ ...jobDraft, template_revision_id: e.target.value, program_revision_id: "" })}><option value="">Select type revision</option>{variantRevisions.map((item) => <option key={item.id} value={item.id}>{item.revision_code} · {item.source_reference || "controlled baseline"}</option>)}</select></Field>
          <Field label="Tenant programme" full><select required value={jobDraft.program_id} onChange={(e) => setJobDraft({ ...jobDraft, program_id: e.target.value, program_revision_id: "" })}><option value="">Select programme</option>{variantPrograms.map((item) => <option key={item.id} value={item.id}>{item.code} — {item.title}</option>)}</select></Field>
          <Field label="Approved programme revision" full><select required value={jobDraft.program_revision_id} onChange={(e) => setJobDraft({ ...jobDraft, program_revision_id: e.target.value })}><option value="">Select revision</option>{compatibleProgramRevisions.map((item) => <option key={item.id} value={item.id}>{item.revision_code} · {item.approval_reference}</option>)}</select></Field>
          <Field label="Source reference" full><input value={jobDraft.source_reference} onChange={(e) => setJobDraft({ ...jobDraft, source_reference: e.target.value })} /></Field>
          <div className="induction-actions induction-field full"><button className="induction-btn primary" disabled={busy || !selectedVariant}>Create controlled induction</button></div>
        </form></section>
        <section className="induction-card"><div className="induction-section-title"><h2>Induction register</h2><span className="induction-subtle">{jobs.length} jobs</span></div><div className="induction-list">{jobs.map((job) => <button key={job.id} className={`induction-list-item${selectedJobId === job.id ? " active" : ""}`} onClick={() => setSelectedJobId(job.id)}><strong>{job.registration} · {job.serial_number}</strong><small>{job.induction_ref}</small><StatusBadge value={job.status} /></button>)}{!jobs.length && <div className="induction-empty">No induction jobs.</div>}</div></section>
      </aside>
      <main className="induction-stack">
        {!workspace ? <section className="induction-card induction-empty">Select or create an induction.</section> : <>
          <section className="induction-card"><div className="induction-section-title"><div><h2>{workspace.induction.registration} induction control</h2><div className="induction-subtle">{workspace.induction.induction_ref} · {workspace.induction.serial_number}</div></div><StatusBadge value={workspace.induction.status} /></div>
            <div className="induction-steps">{STEPS.map((step, index) => <div key={step} className={`induction-step${index < currentStepIndex ? " done" : index === currentStepIndex ? " current" : ""}`}>{step}</div>)}</div>
            <div className="induction-metrics" style={{ marginTop: 12 }}><div className="induction-metric"><span>Datasets</span><strong>{workspace.datasets.length}</strong></div><div className="induction-metric"><span>Rows</span><strong>{workspace.induction.counts_json?.rows || 0}</strong></div><div className="induction-metric"><span>Applicable tasks</span><strong>{workspace.applicability_snapshot?.applicable_requirements_json?.length || 0}</strong></div><div className="induction-metric"><span>Issues</span><strong>{issueRows.length}</strong></div></div>
          </section>
          <section className="induction-card"><h2>Source package</h2><div className="induction-form-grid"><Field label="Files" full><input type="file" multiple accept=".csv,.xlsx,.xlsm" onChange={(e) => setFiles(Array.from(e.target.files || []))} /></Field><Field label="Source system"><input value={sourceSystem} onChange={(e) => setSourceSystem(e.target.value)} /></Field><Field label="Force dataset (optional)"><select value={forcedDataset} onChange={(e) => setForcedDataset(e.target.value)}><option value="">Auto-classify sheets</option>{DATASETS.map((item) => <option key={item}>{item}</option>)}</select></Field></div><div className="induction-actions"><button className="induction-btn primary" disabled={busy || !files.length} onClick={uploadFiles}>Stage source package</button><button className="induction-btn" disabled={busy || !workspace.datasets.length} onClick={() => jobAction("validate")}>Validate all datasets</button><button className="induction-btn" disabled={busy || workspace.induction.status !== "VALIDATED"} onClick={() => jobAction("effectivity")}>Resolve effectivity</button><button className="induction-btn" disabled={busy || workspace.induction.status !== "EFFECTIVITY_RESOLVED"} onClick={() => jobAction("approve")}>Quality approval</button></div></section>
          <section className="induction-card"><h2>Dataset status</h2><div className="induction-table-wrap"><table className="induction-table"><thead><tr><th>Dataset</th><th>Source</th><th>Rows</th><th>Mapping</th><th>Status</th></tr></thead><tbody>{workspace.datasets.map((item) => <tr key={item.id}><td>{item.dataset}</td><td>{item.source_name}{item.source_sheet ? ` / ${item.source_sheet}` : ""}</td><td>{item.row_count}</td><td>{item.mapping_profile_id ? "Resolved" : "Required"}</td><td><StatusBadge value={item.status} /></td></tr>)}</tbody></table></div></section>
          {issueRows.length > 0 && <section className="induction-card"><h2>Validation and reconciliation issues</h2><div className="induction-table-wrap"><table className="induction-table"><thead><tr><th>Row</th><th>Status</th><th>Errors / warnings</th><th>Normalized data</th><th>Decision</th></tr></thead><tbody>{issueRows.slice(0, 200).map((row: InductionRow) => <tr key={row.id}><td>{row.row_number}</td><td><StatusBadge value={row.status} /></td><td>{[...row.errors_json, ...row.warnings_json].map((item, index) => <div key={index}>{item}</div>)}</td><td><div className="induction-json">{JSON.stringify(row.normalized_json, null, 2)}</div></td><td><div className="induction-actions"><button className="induction-btn" onClick={() => run(() => inductionApi.decideRow(workspace.induction.id, row.id, "ACCEPT", row.normalized_json), "Row accepted").then(() => inductionApi.workspace(workspace.induction.id).then(setWorkspace))}>Accept</button><button className="induction-btn danger" onClick={() => run(() => inductionApi.decideRow(workspace.induction.id, row.id, "REJECT", {}), "Row rejected").then(() => inductionApi.workspace(workspace.induction.id).then(setWorkspace))}>Reject</button></div></td></tr>)}</tbody></table></div></section>}
          {workspace.applicability_snapshot && <section className="induction-card"><h2>Resolved aircraft baseline</h2><div className="induction-two"><div><div className="induction-notice success">Configuration conformity passed. Snapshot <code>{workspace.applicability_snapshot.snapshot_hash.slice(0, 16)}</code></div><h3 style={{ marginTop: 12 }}>Applicable requirements</h3><div className="induction-list">{workspace.applicability_snapshot.applicable_requirements_json.slice(0, 100).map((item: any) => <div className="induction-list-item" key={item.requirement_key}><strong>{item.task_code} · {item.title}</strong><small>{item.category} {item.ata_chapter || ""}</small></div>)}</div></div><div><h3>Excluded with reasons</h3><div className="induction-list">{workspace.applicability_snapshot.excluded_requirements_json.slice(0, 100).map((item: any) => <div className="induction-list-item" key={item.requirement_key}><strong>{item.task_code} · {item.title}</strong><small>{item.exclusion_reason}</small></div>)}</div></div></div></section>}
          <section className="induction-card"><h2>Activation</h2><div className="induction-form-grid"><Field label="Opening airframe hours"><input type="number" min="0" step="0.01" value={openingHours} onChange={(e) => setOpeningHours(e.target.value)} /></Field><Field label="Opening airframe cycles"><input type="number" min="0" step="1" value={openingCycles} onChange={(e) => setOpeningCycles(e.target.value)} /></Field><Field label="Approval statement" full><textarea value={activationNote} onChange={(e) => setActivationNote(e.target.value)} placeholder="Confirm source records, configuration, applicability and programme baseline were reviewed." /></Field></div><button className="induction-btn primary" disabled={busy || workspace.induction.status !== "APPROVED" || activationNote.trim().length < 5} onClick={() => jobAction("activate")}>Activate aircraft baseline</button>{workspace.binding && <div className="induction-notice success" style={{ marginTop: 10 }}>Aircraft is active and bound to the immutable type, programme and applicability revisions.</div>}</section>
        </>}
      </main>
    </div>}

    {tab === "catalogue" && <div className="induction-stack">
      <section className="induction-three">
        <form className="induction-card induction-stack" onSubmit={(e) => { e.preventDefault(); run(() => inductionApi.createFamily(familyDraft), "Family created").then(() => setFamilyDraft({ code: "", name: "", manufacturer: "", description: "" })); }}><h2>1. Aircraft family</h2><Field label="Code"><input required value={familyDraft.code} onChange={(e) => setFamilyDraft({ ...familyDraft, code: e.target.value.toUpperCase() })} /></Field><Field label="Manufacturer"><input required value={familyDraft.manufacturer} onChange={(e) => setFamilyDraft({ ...familyDraft, manufacturer: e.target.value })} /></Field><Field label="Name"><input required value={familyDraft.name} onChange={(e) => setFamilyDraft({ ...familyDraft, name: e.target.value })} /></Field><button className="induction-btn primary">Create family</button></form>
        <form className="induction-card induction-stack" onSubmit={(e) => { e.preventDefault(); run(() => inductionApi.createType(typeDraft), "Type created"); }}><h2>2. Certified type</h2><Field label="Family"><select required value={typeDraft.family_id} onChange={(e) => setTypeDraft({ ...typeDraft, family_id: e.target.value })}><option value="">Select</option>{catalogue.families.map((item) => <option key={item.id} value={item.id}>{item.manufacturer} {item.name}</option>)}</select></Field><Field label="Type code"><input required value={typeDraft.type_code} onChange={(e) => setTypeDraft({ ...typeDraft, type_code: e.target.value.toUpperCase() })} /></Field><Field label="Name"><input required value={typeDraft.name} onChange={(e) => setTypeDraft({ ...typeDraft, name: e.target.value })} /></Field><Field label="Type certificate"><input value={typeDraft.type_certificate_number} onChange={(e) => setTypeDraft({ ...typeDraft, type_certificate_number: e.target.value })} /></Field><button className="induction-btn primary">Create type</button></form>
        <form className="induction-card induction-stack" onSubmit={(e) => { e.preventDefault(); run(() => inductionApi.createVariant(variantDraft), "Variant created"); }}><h2>3. Variant</h2><Field label="Aircraft type"><select required value={variantDraft.aircraft_type_id} onChange={(e) => setVariantDraft({ ...variantDraft, aircraft_type_id: e.target.value })}><option value="">Select</option>{catalogue.types.map((item) => <option key={item.id} value={item.id}>{item.type_code} — {item.name}</option>)}</select></Field><Field label="Variant code"><input required value={variantDraft.variant_code} onChange={(e) => setVariantDraft({ ...variantDraft, variant_code: e.target.value.toUpperCase() })} /></Field><Field label="Model code"><input required value={variantDraft.model_code} onChange={(e) => setVariantDraft({ ...variantDraft, model_code: e.target.value.toUpperCase() })} /></Field><Field label="Marketing name"><input value={variantDraft.marketing_name} onChange={(e) => setVariantDraft({ ...variantDraft, marketing_name: e.target.value })} /></Field><button className="induction-btn primary">Create variant</button></form>
      </section>
      <section className="induction-two">
        <form className="induction-card induction-form-grid" onSubmit={(e) => { e.preventDefault(); run(() => inductionApi.createTemplate(templateDraft), "Type template created"); }}><h2 className="induction-field full">4. Type template</h2><Field label="Variant" full><select required value={templateDraft.variant_id} onChange={(e) => setTemplateDraft({ ...templateDraft, variant_id: e.target.value })}><option value="">Select</option>{catalogue.variants.map((item) => <option key={item.id} value={item.id}>{item.model_code}</option>)}</select></Field><Field label="Code"><input required value={templateDraft.code} onChange={(e) => setTemplateDraft({ ...templateDraft, code: e.target.value.toUpperCase() })} /></Field><Field label="Visibility"><select value={templateDraft.visibility} onChange={(e) => setTemplateDraft({ ...templateDraft, visibility: e.target.value })}><option>GLOBAL</option><option>TENANT</option></select></Field><Field label="Title" full><input required value={templateDraft.title} onChange={(e) => setTemplateDraft({ ...templateDraft, title: e.target.value })} /></Field><button className="induction-btn primary induction-field full">Create template</button></form>
        <form className="induction-card induction-form-grid" onSubmit={(e) => { e.preventDefault(); run(() => inductionApi.createTemplateRevision(revisionDraft.template_id, { ...revisionDraft, template_id: undefined, effective_date: revisionDraft.effective_date || null }), "Draft revision created"); }}><h2 className="induction-field full">5. Immutable revision</h2><Field label="Template" full><select required value={revisionDraft.template_id} onChange={(e) => setRevisionDraft({ ...revisionDraft, template_id: e.target.value })}><option value="">Select</option>{catalogue.templates.map((item) => <option key={item.id} value={item.id}>{item.code}</option>)}</select></Field><Field label="Revision"><input required value={revisionDraft.revision_code} onChange={(e) => setRevisionDraft({ ...revisionDraft, revision_code: e.target.value.toUpperCase() })} /></Field><Field label="Effective date"><input type="date" value={revisionDraft.effective_date} onChange={(e) => setRevisionDraft({ ...revisionDraft, effective_date: e.target.value })} /></Field><Field label="Source reference" full><input value={revisionDraft.source_reference} onChange={(e) => setRevisionDraft({ ...revisionDraft, source_reference: e.target.value })} /></Field><button className="induction-btn primary induction-field full">Create draft revision</button></form>
      </section>
      <section className="induction-card"><div className="induction-section-title"><h2>Revision engineering workspace</h2><select value={selectedRevisionId} onChange={(e) => setSelectedRevisionId(e.target.value)}><option value="">Select revision</option>{catalogue.revisions.map((item) => <option key={item.id} value={item.id}>{item.revision_code} · {item.status}</option>)}</select></div>{!revisionWorkspace ? <div className="induction-empty">Select a revision to add sources, configuration and requirements.</div> : <><div className="induction-metrics"><div className="induction-metric"><span>Sources</span><strong>{revisionWorkspace.source_documents.length}</strong></div><div className="induction-metric"><span>Configuration nodes</span><strong>{revisionWorkspace.configuration_nodes.length}</strong></div><div className="induction-metric"><span>Requirements</span><strong>{revisionWorkspace.requirements.length}</strong></div><div className="induction-metric"><span>Status</span><StatusBadge value={revisionWorkspace.revision.status} /></div></div><div className="induction-three" style={{ marginTop: 12 }}>
        <form className="induction-stack" onSubmit={(e) => { e.preventDefault(); run(() => inductionApi.addSourceDocument(selectedRevisionId, { ...sourceDraft, issue_date: sourceDraft.issue_date || null }), "Source document added").then(() => inductionApi.templateRevision(selectedRevisionId).then(setRevisionWorkspace)); }}><h3>Source document</h3><Field label="Type"><input value={sourceDraft.document_type} onChange={(e) => setSourceDraft({ ...sourceDraft, document_type: e.target.value })} /></Field><Field label="Reference"><input required value={sourceDraft.reference} onChange={(e) => setSourceDraft({ ...sourceDraft, reference: e.target.value })} /></Field><Field label="Revision"><input value={sourceDraft.revision} onChange={(e) => setSourceDraft({ ...sourceDraft, revision: e.target.value })} /></Field><button className="induction-btn">Add source</button></form>
        <form className="induction-stack" onSubmit={(e) => { e.preventDefault(); run(() => inductionApi.addConfigurationNode(selectedRevisionId, { ...nodeDraft, minimum_quantity: Number(nodeDraft.minimum_quantity), maximum_quantity: nodeDraft.maximum_quantity ? Number(nodeDraft.maximum_quantity) : null, allowable_parts_json: parseJson(nodeDraft.allowable_parts_json, "Allowable parts"), counter_rules_json: [], effectivity_json: parseJson(nodeDraft.effectivity_json, "Effectivity") }), "Configuration node added").then(() => inductionApi.templateRevision(selectedRevisionId).then(setRevisionWorkspace)); }}><h3>Configuration node</h3><Field label="Node key"><input required value={nodeDraft.node_key} onChange={(e) => setNodeDraft({ ...nodeDraft, node_key: e.target.value.toUpperCase() })} /></Field><Field label="Position"><input value={nodeDraft.position_code} onChange={(e) => setNodeDraft({ ...nodeDraft, position_code: e.target.value.toUpperCase() })} /></Field><Field label="Title"><input required value={nodeDraft.title} onChange={(e) => setNodeDraft({ ...nodeDraft, title: e.target.value })} /></Field><Field label="Allowable parts JSON"><textarea value={nodeDraft.allowable_parts_json} onChange={(e) => setNodeDraft({ ...nodeDraft, allowable_parts_json: e.target.value })} /></Field><button className="induction-btn">Add node</button></form>
        <form className="induction-stack" onSubmit={(e) => { e.preventDefault(); run(() => inductionApi.addRequirement(selectedRevisionId, { ...requirementDraft, interval_json: parseJson(requirementDraft.interval_json, "Interval"), threshold_json: parseJson(requirementDraft.threshold_json, "Threshold"), effectivity_json: parseJson(requirementDraft.effectivity_json, "Effectivity") }), "Requirement added").then(() => inductionApi.templateRevision(selectedRevisionId).then(setRevisionWorkspace)); }}><h3>Requirement</h3><Field label="Requirement key"><input required value={requirementDraft.requirement_key} onChange={(e) => setRequirementDraft({ ...requirementDraft, requirement_key: e.target.value.toUpperCase() })} /></Field><Field label="Task code"><input required value={requirementDraft.task_code} onChange={(e) => setRequirementDraft({ ...requirementDraft, task_code: e.target.value.toUpperCase() })} /></Field><Field label="Title"><input required value={requirementDraft.title} onChange={(e) => setRequirementDraft({ ...requirementDraft, title: e.target.value })} /></Field><Field label="Interval JSON"><textarea value={requirementDraft.interval_json} onChange={(e) => setRequirementDraft({ ...requirementDraft, interval_json: e.target.value })} /></Field><button className="induction-btn">Add requirement</button></form>
      </div>{revisionWorkspace.revision.status === "DRAFT" && <button className="induction-btn primary" style={{ marginTop: 14 }} onClick={() => { const note = window.prompt("Approval note"); if (note) run(() => inductionApi.publishTemplateRevision(selectedRevisionId, note), "Revision published").then(() => inductionApi.templateRevision(selectedRevisionId).then(setRevisionWorkspace)); }}>Publish immutable revision</button>}</>}</section>
    </div>}

    {tab === "programmes" && <div className="induction-two"><section className="induction-stack"><form className="induction-card induction-form-grid" onSubmit={(e) => { e.preventDefault(); run(() => inductionApi.createProgram(programDraft), "Tenant programme created"); }}><h2 className="induction-field full">Tenant programme overlay</h2><Field label="Variant" full><select required value={programDraft.variant_id} onChange={(e) => setProgramDraft({ ...programDraft, variant_id: e.target.value })}><option value="">Select</option>{catalogue.variants.map((item) => <option key={item.id} value={item.id}>{item.model_code}</option>)}</select></Field><Field label="Code"><input required value={programDraft.code} onChange={(e) => setProgramDraft({ ...programDraft, code: e.target.value.toUpperCase() })} /></Field><Field label="Authority"><input value={programDraft.authority} onChange={(e) => setProgramDraft({ ...programDraft, authority: e.target.value })} /></Field><Field label="Title" full><input required value={programDraft.title} onChange={(e) => setProgramDraft({ ...programDraft, title: e.target.value })} /></Field><button className="induction-btn primary induction-field full">Create programme</button></form><section className="induction-card"><h2>Programme register</h2><div className="induction-list">{programs.map((item) => <button className={`induction-list-item${selectedProgramId === item.id ? " active" : ""}`} key={item.id} onClick={() => setSelectedProgramId(item.id)}><strong>{item.code}</strong><small>{item.title}</small><StatusBadge value={item.status} /></button>)}</div></section></section>
      <section className="induction-stack"><form className="induction-card induction-form-grid" onSubmit={(e) => { e.preventDefault(); run(() => inductionApi.createProgramRevision(selectedProgramId, { ...programRevisionDraft, effective_date: programRevisionDraft.effective_date || null, approval_date: programRevisionDraft.approval_date || null }), "Programme revision created").then(() => inductionApi.programRevisions(selectedProgramId).then(setProgramRevisions)); }}><h2 className="induction-field full">Programme revision</h2><Field label="Published type revision" full><select required value={programRevisionDraft.base_template_revision_id} onChange={(e) => setProgramRevisionDraft({ ...programRevisionDraft, base_template_revision_id: e.target.value })}><option value="">Select</option>{catalogue.revisions.filter((item) => item.status === "PUBLISHED").map((item) => <option key={item.id} value={item.id}>{item.revision_code} · {item.source_reference}</option>)}</select></Field><Field label="Revision code"><input required value={programRevisionDraft.revision_code} onChange={(e) => setProgramRevisionDraft({ ...programRevisionDraft, revision_code: e.target.value.toUpperCase() })} /></Field><Field label="Effective date"><input type="date" value={programRevisionDraft.effective_date} onChange={(e) => setProgramRevisionDraft({ ...programRevisionDraft, effective_date: e.target.value })} /></Field><Field label="Authority approval"><input required value={programRevisionDraft.approval_reference} onChange={(e) => setProgramRevisionDraft({ ...programRevisionDraft, approval_reference: e.target.value })} /></Field><Field label="Approval date"><input required type="date" value={programRevisionDraft.approval_date} onChange={(e) => setProgramRevisionDraft({ ...programRevisionDraft, approval_date: e.target.value })} /></Field><button disabled={!selectedProgramId} className="induction-btn primary induction-field full">Create revision</button></form><section className="induction-card"><h2>Revisions and overrides</h2><div className="induction-list">{programRevisions.map((item) => <div className="induction-list-item" key={item.id}><strong>{item.revision_code}</strong><small>{item.approval_reference}</small><StatusBadge value={item.status} />{item.status === "DRAFT" && <div className="induction-actions" style={{ marginTop: 8 }}><button className="induction-btn" onClick={() => setOverrideDraft({ ...overrideDraft, program_revision_id: item.id })}>Add override</button><button className="induction-btn primary" onClick={() => { const note = window.prompt("Approval note"); if (note) run(() => inductionApi.approveProgramRevision(item.id, note), "Programme revision approved").then(() => inductionApi.programRevisions(selectedProgramId).then(setProgramRevisions)); }}>Approve</button></div>}</div>)}</div>{overrideDraft.program_revision_id && <form className="induction-form-grid" style={{ marginTop: 12 }} onSubmit={(e) => { e.preventDefault(); run(() => inductionApi.addProgramOverride(overrideDraft.program_revision_id, { ...overrideDraft, program_revision_id: undefined, patch_json: parseJson(overrideDraft.patch_json, "Patch"), effectivity_json: parseJson(overrideDraft.effectivity_json, "Effectivity") }), "Programme override added"); }}><Field label="Requirement key"><input required value={overrideDraft.requirement_key} onChange={(e) => setOverrideDraft({ ...overrideDraft, requirement_key: e.target.value.toUpperCase() })} /></Field><Field label="Action"><select value={overrideDraft.action} onChange={(e) => setOverrideDraft({ ...overrideDraft, action: e.target.value })}><option>MODIFY</option><option>ADD</option><option>EXCLUDE</option></select></Field><Field label="Patch JSON" full><textarea value={overrideDraft.patch_json} onChange={(e) => setOverrideDraft({ ...overrideDraft, patch_json: e.target.value })} /></Field><Field label="Justification" full><textarea required value={overrideDraft.justification} onChange={(e) => setOverrideDraft({ ...overrideDraft, justification: e.target.value })} /></Field><button className="induction-btn primary induction-field full">Save controlled override</button></form>}</section></section>
    </div>}

    {tab === "mappings" && <div className="induction-grid"><section className="induction-card"><h2>Mapping profiles</h2><div className="induction-list">{profiles.map((item) => <div key={item.id} className="induction-list-item"><strong>{item.name} v{item.version}</strong><small>{item.source_system} · {item.dataset}</small><StatusBadge value={item.scope} /></div>)}</div></section><form className="induction-card induction-form-grid" onSubmit={(e) => { e.preventDefault(); run(() => inductionApi.createMappingProfile({ ...mappingDraft, header_signature_json: parseJson(mappingDraft.header_signature_json, "Header signature"), mapping_json: parseJson(mappingDraft.mapping_json, "Mapping"), transformations_json: parseJson(mappingDraft.transformations_json, "Transformations"), defaults_json: parseJson(mappingDraft.defaults_json, "Defaults"), validation_json: parseJson(mappingDraft.validation_json, "Validation") }), "Mapping profile version created"); }}><h2 className="induction-field full">Versioned source mapping</h2><Field label="Name"><input required value={mappingDraft.name} onChange={(e) => setMappingDraft({ ...mappingDraft, name: e.target.value })} /></Field><Field label="Scope"><select value={mappingDraft.scope} onChange={(e) => setMappingDraft({ ...mappingDraft, scope: e.target.value })}><option>TENANT</option><option>GLOBAL</option></select></Field><Field label="Source system"><input required value={mappingDraft.source_system} onChange={(e) => setMappingDraft({ ...mappingDraft, source_system: e.target.value.toUpperCase() })} /></Field><Field label="Dataset"><select value={mappingDraft.dataset} onChange={(e) => setMappingDraft({ ...mappingDraft, dataset: e.target.value })}>{DATASETS.map((item) => <option key={item}>{item}</option>)}</select></Field><Field label="Fingerprint" full><input required minLength={16} value={mappingDraft.fingerprint} onChange={(e) => setMappingDraft({ ...mappingDraft, fingerprint: e.target.value })} /></Field><Field label="Source → canonical mapping JSON" full><textarea value={mappingDraft.mapping_json} onChange={(e) => setMappingDraft({ ...mappingDraft, mapping_json: e.target.value })} /></Field><Field label="Transformations JSON" full><textarea value={mappingDraft.transformations_json} onChange={(e) => setMappingDraft({ ...mappingDraft, transformations_json: e.target.value })} /></Field><button className="induction-btn primary induction-field full">Publish mapping version</button></form></div>}
  </div>;
}
