import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  BadgeCheck, Bot, Building2, CheckCircle2, ClipboardList, Download, FileUp, History, MapPin,
  PackageOpen, Plus, Save, Settings2, ShieldCheck, UserRoundCog, XCircle,
} from "lucide-react";

import Drawer from "../shared/Drawer";
import {
  createAssessmentTemplate, createControlledTrainingForm, createTrainingReferenceResource,
  getTrainingAutomationStatus, getTrainingOperatingSettings, getTrainingSetupReadiness,
  createTrainingSetupVersion, getTrainingConfigurationExport, listTrainingSetupVersions,
  listAssessmentTemplates, listControlledTrainingForms, listTrainingConfigurationRevisions,
  listTrainingReferenceResources, runTrainingPlanAutomation, transitionControlledTrainingForm,
  transitionTrainingSetupVersion, updateTrainingOperatingSettings, validateTrainingSetupVersion,
} from "../../services/trainingOperating";
import type {
  AssessmentTemplate, AutomationStatus, ConfigurationRevision, ControlledFormTemplate,
  SetupReadiness, SetupVersion, TrainingOperatingSettings, TrainingReferenceResource,
} from "../../types/trainingOperating";
import { parseFormFieldLines, parseSignatoryLines } from "./trainingSetupModel";
import { downloadTrainingWorkbookTemplate, listTrainingWorkbookImports } from "../../services/trainingWorkbookImport";
import type { TrainingWorkbookImportJob } from "../../types/trainingWorkbookImport";
import CurrencySelect from "./CurrencySelect";
import TrainingReminderPolicyEditor from "./TrainingReminderPolicyEditor";

const parseLines = parseFormFieldLines;

type Props = {
  canManage: boolean;
  onOpenImport: () => void;
  onChanged?: () => void | Promise<void>;
};

type ResourceDraft = {
  resource_type: "PROVIDER" | "LOCATION" | "INSTRUCTOR";
  code: string;
  name: string;
  contact_name: string;
  email: string;
  phone: string;
  address: string;
};

const resourceDraft = (): ResourceDraft => ({
  resource_type: "PROVIDER", code: "", name: "", contact_name: "", email: "", phone: "", address: "",
});

const formDraft = () => ({
  code: "", title: "", workflow: "PLAN", dms_document_id: "", dms_revision_id: "", retention_rule: "",
  fields: "title|Text|true\nnotes|Long text|false",
});

const assessmentDraft = () => ({
  code: "", name: "", assessment_type: "WRITTEN", outcome_scheme: "NUMERIC", pass_threshold: "80",
  manual_reference: "", questions: "1|Assessment criterion|TEXT|true|0",
});

const TrainingSetupWorkspace: React.FC<Props> = ({ canManage, onOpenImport, onChanged }) => {
  const [settings, setSettings] = useState<TrainingOperatingSettings | null>(null);
  const [readiness, setReadiness] = useState<SetupReadiness | null>(null);
  const [resources, setResources] = useState<TrainingReferenceResource[]>([]);
  const [forms, setForms] = useState<ControlledFormTemplate[]>([]);
  const [templates, setTemplates] = useState<AssessmentTemplate[]>([]);
  const [revisions, setRevisions] = useState<ConfigurationRevision[]>([]);
  const [automation, setAutomation] = useState<AutomationStatus | null>(null);
  const [setupVersions, setSetupVersions] = useState<SetupVersion[]>([]);
  const [importJobs, setImportJobs] = useState<TrainingWorkbookImportJob[]>([]);
  const [startMode, setStartMode] = useState<"BLANK" | "TEMPLATE_PACK" | "WORKBOOK">("BLANK");
  const [resourceOpen, setResourceOpen] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [assessmentOpen, setAssessmentOpen] = useState(false);
  const [resourceForm, setResourceForm] = useState(resourceDraft);
  const [controlledForm, setControlledForm] = useState(formDraft);
  const [assessmentForm, setAssessmentForm] = useState(assessmentDraft);
  const [signatoryText, setSignatoryText] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    const results = await Promise.allSettled([
      getTrainingOperatingSettings(), getTrainingSetupReadiness(), listTrainingReferenceResources(),
      listControlledTrainingForms(), listAssessmentTemplates(), listTrainingConfigurationRevisions(), getTrainingAutomationStatus(), listTrainingSetupVersions(), listTrainingWorkbookImports(),
    ]);
    const [settingsResult, readinessResult, resourcesResult, formsResult, templatesResult, revisionsResult, automationResult, versionsResult, importsResult] = results;
    if (settingsResult.status === "fulfilled") {
      setSettings(settingsResult.value);
      setSignatoryText((settingsResult.value.certificate_signatories || []).map((item) => `${item.name}|${item.title}`).join("\n"));
    }
    if (readinessResult.status === "fulfilled") setReadiness(readinessResult.value);
    if (resourcesResult.status === "fulfilled") setResources(resourcesResult.value);
    if (formsResult.status === "fulfilled") setForms(formsResult.value);
    if (templatesResult.status === "fulfilled") setTemplates(templatesResult.value);
    if (revisionsResult.status === "fulfilled") setRevisions(revisionsResult.value);
    if (automationResult.status === "fulfilled") setAutomation(automationResult.value);
    if (versionsResult.status === "fulfilled") setSetupVersions(versionsResult.value);
    if (importsResult.status === "fulfilled") setImportJobs(importsResult.value.items);
    const failures = results.filter((result) => result.status === "rejected");
    if (failures.length) setError(`${failures.length} setup source${failures.length === 1 ? "" : "s"} could not be loaded. No missing source is being shown as zero.`);
  }, []);

  useEffect(() => { void load(); }, [load]);

  const run = async (operation: () => Promise<unknown>, success: string) => {
    setBusy(true); setError(null); setMessage(null);
    try {
      await operation();
      await load();
      await onChanged?.();
      setMessage(success);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The setup action could not be completed.");
    } finally { setBusy(false); }
  };

  const saveSettings = () => {
    if (!settings) return;
    const signatories = parseSignatoryLines(signatoryText);
    void run(() => updateTrainingOperatingSettings({ ...settings, certificate_signatories: signatories }), "Tenant training policy saved as a controlled revision.");
  };

  const createSetupDraft = () => void run(async () => {
    if (startMode === "WORKBOOK") {
      onOpenImport();
      return;
    }
    await createTrainingSetupVersion({
      source_mode: startMode,
      title: `${startMode === "TEMPLATE_PACK" ? "Controlled template pack" : "Blank tenant"} setup`,
      change_summary: "Tenant setup draft created from the frontend setup workspace.",
      snapshot: startMode === "TEMPLATE_PACK" ? { template_pack: "AMO_BASELINE", proposed_only: true } : {},
    });
  }, startMode === "WORKBOOK" ? "Workbook reconciliation opened." : "Tenant setup draft created.");

  const downloadConfiguration = () => void run(async () => {
    const bundle = await getTrainingConfigurationExport();
    const href = URL.createObjectURL(new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = href; anchor.download = `training-configuration-v${bundle.version || "draft"}.json`; anchor.click();
    URL.revokeObjectURL(href);
  }, "Tenant configuration exported.");

  const groupedResources = useMemo(() => ({
    PROVIDER: resources.filter((item) => item.resource_type === "PROVIDER"),
    LOCATION: resources.filter((item) => item.resource_type === "LOCATION"),
    INSTRUCTOR: resources.filter((item) => item.resource_type === "INSTRUCTOR"),
  }), [resources]);

  if (!settings) return <div className="tos-empty"><Settings2 size={24} /><strong>Setup source unavailable</strong><span>Refresh after the operating API is available.</span></div>;

  return (
    <div className="tos-stack tos-setup-workspace">
      {message ? <div className="tos-banner tos-banner--success"><CheckCircle2 size={17} />{message}<button onClick={() => setMessage(null)} aria-label="Dismiss">×</button></div> : null}
      {error ? <div className="tos-banner tos-banner--error"><XCircle size={17} />{error}<button onClick={() => setError(null)} aria-label="Dismiss">×</button></div> : null}

      <section className="tos-card tos-setup-start">
        <div><p className="tos-kicker">Start or revise setup</p><h2>One governed tenant configuration</h2><p>Choose a starting mode, inspect the proposed objects, validate readiness and activate an effective-dated version—without Python or database seeding.</p></div>
        <div className="tos-mode-selector" role="radiogroup" aria-label="Setup starting mode">{([
          ["BLANK", "Blank tenant", "Create every tenant object in these frontend workspaces."],
          ["TEMPLATE_PACK", "Template pack", "Load reviewable AMO proposals; nothing activates silently."],
          ["WORKBOOK", "Workbook migration", "Preview sheets, reconcile identities and commit atomically."],
        ] as const).map(([value, label, detail]) => <button key={value} role="radio" aria-checked={startMode === value} className={startMode === value ? "is-active" : ""} onClick={() => setStartMode(value)}><PackageOpen size={18} /><strong>{label}</strong><small>{detail}</small></button>)}</div>
        <div className="tos-actions"><button className="primary-chip-btn" disabled={!canManage || busy} onClick={createSetupDraft}>{startMode === "WORKBOOK" ? <FileUp size={16} /> : <Plus size={16} />} {startMode === "WORKBOOK" ? "Open reconciliation" : "Create setup draft"}</button><button disabled={!canManage || busy} onClick={downloadConfiguration}><Download size={16} /> Export configuration</button></div>
      </section>

      <section className="tos-card tos-setup-commandbar">
        <div><p className="tos-kicker">Tenant setup</p><h2>{readiness?.completion_percent ?? 0}% configured</h2><p>{readiness?.go_live_ready ? "Blocking foundations are ready. Warnings remain visible below." : "Complete each blocking foundation before activating autonomous operation."}</p></div>
        <button className="primary-chip-btn" disabled={!canManage} onClick={onOpenImport}><FileUp size={16} /> Import Excel</button>
        <button disabled={!canManage || busy} onClick={() => void run(() => downloadTrainingWorkbookTemplate(), "Current workbook template downloaded.")}><Download size={16} /> Excel template</button>
        <button disabled={!canManage} onClick={() => setFormOpen(true)}><ClipboardList size={16} /> Register / import form</button>
        <button disabled={busy || !canManage} onClick={() => void run(() => runTrainingPlanAutomation(), "Monthly expiry plan synchronized.")}><Bot size={16} /> Run monthly plan</button>
        <button disabled={busy || !canManage} onClick={saveSettings}><Save size={16} /> Save policy</button>
      </section>

      <div className="tos-readiness-grid">
        {readiness?.items.map((item) => <article key={item.key} className={`tos-readiness-item is-${item.status.toLowerCase()}`}><span>{item.status === "READY" ? <CheckCircle2 size={17} /> : <XCircle size={17} />}</span><div><strong>{item.label}</strong><small>{item.reason}</small></div><span>{item.blocking ? "Required" : "Recommended"}</span></article>)}
      </div>

      <details className="tos-disclosure" open id="operating-policy">
        <summary><span><Settings2 size={18} /><strong>Operating policy &amp; automation</strong></span><small>Timing, currency, plan runs and activation state</small></summary>
        <div className="tos-disclosure__body"><div className="tos-form-grid tos-form-grid--compact">
          <label>Planning lead days<input type="number" min="1" max="365" value={settings.default_planning_lead_days} onChange={(event) => setSettings({ ...settings, default_planning_lead_days: Number(event.target.value) })} /></label>
          <label>Recurrent window days<input type="number" min="1" max="365" value={settings.default_recurrent_window_days} onChange={(event) => setSettings({ ...settings, default_recurrent_window_days: Number(event.target.value) })} /></label>
          <label>Attendance window minutes<input type="number" min="5" max="720" value={settings.attendance_window_minutes} onChange={(event) => setSettings({ ...settings, attendance_window_minutes: Number(event.target.value) })} /></label>
          <label>QR lifetime minutes<input type="number" min="1" max="60" value={settings.attendance_qr_lifetime_minutes} onChange={(event) => setSettings({ ...settings, attendance_qr_lifetime_minutes: Number(event.target.value) })} /></label>
          <label>Competence review months<input type="number" min="1" max="120" value={settings.competence_review_frequency_months} onChange={(event) => setSettings({ ...settings, competence_review_frequency_months: Number(event.target.value) })} /></label>
          <label>Experience review months<input type="number" min="1" max="24" value={settings.experience_review_frequency_months} onChange={(event) => setSettings({ ...settings, experience_review_frequency_months: Number(event.target.value) })} /></label>
          <label>Auditor observer audits<input type="number" min="1" max="20" value={settings.auditor_observer_count} onChange={(event) => setSettings({ ...settings, auditor_observer_count: Number(event.target.value) })} /></label>
          <label>Budget decimal places<input type="number" min="0" max="6" value={settings.budget_rounding_places} onChange={(event) => setSettings({ ...settings, budget_rounding_places: Number(event.target.value) })} /></label>
          <label>Reporting currency<CurrencySelect value={settings.reporting_currency} onChange={(currency) => setSettings({ ...settings, reporting_currency: currency })} /></label>
          <label>Tenant timezone<input value={settings.timezone} onChange={(event) => setSettings({ ...settings, timezone: event.target.value })} placeholder="Africa/Nairobi" /></label>
          <label>Monthly run day<input type="number" min="1" max="28" value={settings.plan_run_day} onChange={(event) => setSettings({ ...settings, plan_run_day: Number(event.target.value) })} /></label>
          <label>Run hour (0–23)<input type="number" min="0" max="23" value={settings.plan_run_hour} onChange={(event) => setSettings({ ...settings, plan_run_hour: Number(event.target.value) })} /></label>
          <label className="tos-check"><input type="checkbox" checked={settings.plan_automation_enabled} onChange={(event) => setSettings({ ...settings, plan_automation_enabled: event.target.checked })} /><span>Autonomously refresh the annual plan each month</span></label>
          <label>Setup state<select value={settings.setup_status} onChange={(event) => setSettings({ ...settings, setup_status: event.target.value as "DRAFT" | "ACTIVE" })}><option value="DRAFT">Draft</option><option value="ACTIVE">Active</option></select></label>
        </div><div className="tos-inline-proof"><Bot size={17} /><span>{automation?.enabled ? `Next scheduled evaluation: ${automation.next_run_at ? new Date(automation.next_run_at).toLocaleString() : "pending"}` : "Automation disabled"}</span><strong>{automation?.last_run ? `Last: ${automation.last_run.status}` : "No run yet"}</strong></div></div>
      </details>

      <TrainingReminderPolicyEditor
        value={settings.notification_policy || {}}
        disabled={!canManage || busy}
        onChange={(notification_policy) => setSettings({ ...settings, notification_policy })}
      />

      <details className="tos-disclosure" id="certificate-policy">
        <summary><span><BadgeCheck size={18} /><strong>Certificate &amp; decision policy</strong></span><small>Server-side numbering, signatories and committee defaults</small></summary>
        <div className="tos-disclosure__body"><div className="tos-form-grid">
          <label>Certificate prefix<input value={settings.certificate_number_prefix} onChange={(event) => setSettings({ ...settings, certificate_number_prefix: event.target.value.toUpperCase() })} /></label>
          <label>Certificate template / DMS reference<input value={settings.certificate_template_reference || ""} onChange={(event) => setSettings({ ...settings, certificate_template_reference: event.target.value || null })} /></label>
          <label className="tos-span-2">Signatories (one <code>Name|Title</code> per line)<textarea value={signatoryText} onChange={(event) => setSignatoryText(event.target.value)} placeholder="Jane Quality|Head of Quality" /></label>
          <label className="tos-span-2">Public verification privacy text<textarea value={settings.certificate_public_privacy_text || ""} onChange={(event) => setSettings({ ...settings, certificate_public_privacy_text: event.target.value || null })} /></label>
          <label className="tos-span-2">Committee positions (comma separated)<input value={settings.default_committee_positions.join(", ")} onChange={(event) => setSettings({ ...settings, default_committee_positions: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) })} /></label>
        </div></div>
      </details>

      <details className="tos-disclosure" open id="resource-catalogues">
        <summary><span><Building2 size={18} /><strong>Provider, location &amp; instructor catalogues</strong></span><small>{resources.length} tenant-managed entries</small></summary>
        <div className="tos-disclosure__body"><div className="tos-section-heading"><p>Reusable scheduling options are managed here—no backend seed script required.</p><button disabled={!canManage} onClick={() => setResourceOpen(true)}><Plus size={15} /> Add entry</button></div><div className="tos-resource-grid">
          {(["PROVIDER", "LOCATION", "INSTRUCTOR"] as const).map((kind) => <section key={kind} className="tos-mini-register"><h3>{kind === "PROVIDER" ? <Building2 size={16} /> : kind === "LOCATION" ? <MapPin size={16} /> : <UserRoundCog size={16} />}{kind.toLowerCase()}s <span>{groupedResources[kind].length}</span></h3>{groupedResources[kind].map((item) => <div key={item.id}><strong>{item.name}</strong><small>{item.code}{item.email ? ` · ${item.email}` : ""}</small></div>)}{!groupedResources[kind].length ? <small>No entries yet.</small> : null}</section>)}
        </div></div>
      </details>

      <details className="tos-disclosure" open id="controlled-forms">
        <summary><span><ClipboardList size={18} /><strong>Controlled forms &amp; DMS mappings</strong></span><small>{forms.length} revisions</small></summary>
        <div className="tos-disclosure__body"><div className="tos-section-heading"><p>Define fields in the frontend or link the effective DMS document revision.</p><button disabled={!canManage} onClick={() => setFormOpen(true)}><Plus size={15} /> New form revision</button></div><div className="tos-list">{forms.map((form) => <div key={form.id}><div><strong>{form.code} · {form.title}</strong><small>{form.workflow} · Rev {form.revision_no} · {form.dms_revision_id ? `DMS ${form.dms_revision_id}` : `${Object.keys(form.schema_json || {}).length} schema group(s)`}</small></div><div className="tos-actions"><span className="tos-pill tos-pill--ok">{form.status}</span>{form.status === "DRAFT" ? <button disabled={!canManage || busy} onClick={() => void run(() => transitionControlledTrainingForm(form.id, "ACTIVE"), `${form.code} activated.`)}><ShieldCheck size={15} /> Activate</button> : null}</div></div>)}</div></div>
      </details>

      <details className="tos-disclosure" id="assessment-templates">
        <summary><span><ShieldCheck size={18} /><strong>Assessment criteria builder</strong></span><small>{templates.length} active templates</small></summary>
        <div className="tos-disclosure__body"><div className="tos-section-heading"><p>Questions and mandatory criteria are stored with each controlled template revision.</p><button disabled={!canManage} onClick={() => setAssessmentOpen(true)}><Plus size={15} /> New template</button></div><div className="tos-list">{templates.map((template) => <div key={template.id}><div><strong>{template.code} · {template.name}</strong><small>{template.assessment_type} · Rev {template.revision_no} · {template.questions?.length || 0} criteria</small></div><span className="tos-pill tos-pill--ok">{template.active ? "ACTIVE" : "INACTIVE"}</span></div>)}</div></div>
      </details>

      <details className="tos-disclosure" open id="setup-versions">
        <summary><span><ShieldCheck size={18} /><strong>Setup versions, review &amp; promotion</strong></span><small>{setupVersions.length} effective-dated bundles</small></summary>
        <div className="tos-disclosure__body"><div className="tos-list">{setupVersions.map((version) => <div key={version.id}><div><strong>Version {version.version_no} · {version.title}</strong><small>{version.source_mode.replaceAll("_", " ")} · {version.validation_result.status || "NOT VALIDATED"}{version.effective_from ? ` · effective ${new Date(version.effective_from).toLocaleString()}` : ""}</small>{version.validation_result.blockers?.length ? <small>Blockers: {version.validation_result.blockers.join(", ")}</small> : null}</div><div className="tos-actions"><span className="tos-pill tos-pill--ok">{version.status}</span>{version.status === "DRAFT" ? <><button disabled={!canManage || busy} onClick={() => void run(() => validateTrainingSetupVersion(version.id), `Version ${version.version_no} validated.`)}>Validate</button><button disabled={!canManage || busy} onClick={() => void run(() => transitionTrainingSetupVersion(version.id, "IN_REVIEW", "Submitted from tenant setup workspace"), `Version ${version.version_no} submitted for review.`)}>Submit</button></> : null}{version.status === "IN_REVIEW" ? <button className="primary-chip-btn" disabled={!canManage || busy || Boolean(version.validation_result.blockers?.length)} onClick={() => void run(() => transitionTrainingSetupVersion(version.id, "ACTIVE", "Readiness reviewed and accepted"), `Version ${version.version_no} activated.`)}>Activate</button> : null}{version.status === "ACTIVE" ? <button disabled={!canManage || busy} onClick={() => void run(() => transitionTrainingSetupVersion(version.id, "ROLLED_BACK", "Controlled rollback requested"), `Version ${version.version_no} rolled back.`)}>Roll back</button> : null}</div></div>)}{!setupVersions.length ? <div><div><strong>No setup version yet</strong><small>Choose a starting mode above to create the first tenant-owned draft.</small></div></div> : null}</div></div>
      </details>

      <details className="tos-disclosure">
        <summary><span><History size={18} /><strong>Configuration history</strong></span><small>{revisions.length} saved revisions</small></summary>
        <div className="tos-disclosure__body"><div className="tos-list">{revisions.map((revision) => <div key={revision.id}><div><strong>Revision {revision.revision_no}</strong><small>{revision.change_summary || "Controlled settings revision"}</small></div><time>{new Date(revision.created_at).toLocaleString()}</time></div>)}</div></div>
      </details>

      <details className="tos-disclosure" id="import-history">
        <summary><span><FileUp size={18} /><strong>Workbook import history</strong></span><small>{importJobs.length} recent retained jobs</small></summary>
        <div className="tos-disclosure__body"><div className="tos-section-heading"><p>Preview, conflict, commit and plan-sync outcomes remain available after the upload dialog closes.</p><div className="tos-actions"><button disabled={!canManage || busy} onClick={() => void run(() => downloadTrainingWorkbookTemplate(), "Current workbook template downloaded.")}><Download size={15} /> Template</button><button disabled={!canManage} onClick={onOpenImport}><FileUp size={15} /> New import</button></div></div><div className="tos-list">{importJobs.map((job) => <div key={job.id}><div><strong>{job.filename}</strong><small>{new Date(job.created_at).toLocaleString()} · {job.processed_rows}/{job.total_rows} rows · {job.review_count} review · {job.failed_count} failed</small>{job.summary?.plan_sync ? <small>Plan sync: {String((job.summary.plan_sync as { action?: string }).action || "Unknown")}</small> : null}{job.error_message ? <small>{job.error_message}</small> : null}</div><span className={`tos-pill ${job.status === "FAILED" ? "tos-pill--critical" : "tos-pill--ok"}`}>{job.status}</span></div>)}{!importJobs.length ? <div><div><strong>No workbook imports retained</strong><small>Download the current template or begin a governed preview.</small></div></div> : null}</div></div>
      </details>

      <Drawer title="Add scheduling catalogue entry" isOpen={resourceOpen} onClose={() => setResourceOpen(false)} panelClassName="training-form-drawer training-form-drawer--compact">
        <div className="tos-drawer-form"><label>Type<select value={resourceForm.resource_type} onChange={(event) => setResourceForm({ ...resourceForm, resource_type: event.target.value as ResourceDraft["resource_type"] })}><option>PROVIDER</option><option>LOCATION</option><option>INSTRUCTOR</option></select></label><label>Code<input value={resourceForm.code} onChange={(event) => setResourceForm({ ...resourceForm, code: event.target.value })} /></label><label>Name<input value={resourceForm.name} onChange={(event) => setResourceForm({ ...resourceForm, name: event.target.value })} /></label><label>Contact name<input value={resourceForm.contact_name} onChange={(event) => setResourceForm({ ...resourceForm, contact_name: event.target.value })} /></label><label>Email<input type="email" value={resourceForm.email} onChange={(event) => setResourceForm({ ...resourceForm, email: event.target.value })} /></label><label>Phone<input value={resourceForm.phone} onChange={(event) => setResourceForm({ ...resourceForm, phone: event.target.value })} /></label><label>Address<textarea value={resourceForm.address} onChange={(event) => setResourceForm({ ...resourceForm, address: event.target.value })} /></label><div className="tos-actions"><button onClick={() => setResourceOpen(false)}>Cancel</button><button className="primary-chip-btn" disabled={busy || !resourceForm.code || !resourceForm.name} onClick={() => void run(async () => { await createTrainingReferenceResource({ ...resourceForm, metadata_json: {}, active: true }); setResourceForm(resourceDraft()); setResourceOpen(false); }, "Catalogue entry created.")}>Save</button></div></div>
      </Drawer>

      <Drawer title="Create controlled form revision" isOpen={formOpen} onClose={() => setFormOpen(false)} panelClassName="training-form-drawer">
        <div className="tos-drawer-form"><label>Import JSON form schema<input type="file" accept=".json,application/json" onChange={async (event) => { const file = event.target.files?.[0]; if (!file) return; try { const parsed = JSON.parse(await file.text()) as { code?: string; title?: string; workflow?: string; fields?: Array<{ key?: string; label?: string; required?: boolean }> }; const fields = (parsed.fields || []).map((field, index) => `${field.key || `field_${index + 1}`}|${field.label || field.key || `Field ${index + 1}`}|${Boolean(field.required)}`).join("\n"); setControlledForm((current) => ({ ...current, code: parsed.code || current.code, title: parsed.title || current.title, workflow: parsed.workflow || current.workflow, fields: fields || current.fields })); } catch { setError("That file is not a valid JSON form schema."); } }} /><small>Accepted keys: code, title, workflow and fields[].</small></label><label>Form code<input value={controlledForm.code} onChange={(event) => setControlledForm({ ...controlledForm, code: event.target.value })} /></label><label>Title<input value={controlledForm.title} onChange={(event) => setControlledForm({ ...controlledForm, title: event.target.value })} /></label><label>Workflow<select value={controlledForm.workflow} onChange={(event) => setControlledForm({ ...controlledForm, workflow: event.target.value })}>{["PLAN", "BUDGET", "ATTENDANCE", "ASSESSMENT", "AUTHORIZATION", "EFFECTIVENESS", "OTHER"].map((item) => <option key={item}>{item}</option>)}</select></label><label>DMS document ID<input value={controlledForm.dms_document_id} onChange={(event) => setControlledForm({ ...controlledForm, dms_document_id: event.target.value })} /></label><label>DMS effective revision ID<input value={controlledForm.dms_revision_id} onChange={(event) => setControlledForm({ ...controlledForm, dms_revision_id: event.target.value })} /></label><label>Retention rule<input value={controlledForm.retention_rule} onChange={(event) => setControlledForm({ ...controlledForm, retention_rule: event.target.value })} /></label><label>Fields (one <code>key|label|required</code> per line)<textarea value={controlledForm.fields} onChange={(event) => setControlledForm({ ...controlledForm, fields: event.target.value })} /></label><div className="tos-actions"><button onClick={() => setFormOpen(false)}>Cancel</button><button className="primary-chip-btn" disabled={busy || !controlledForm.code || !controlledForm.title} onClick={() => void run(async () => { await createControlledTrainingForm({ code: controlledForm.code, title: controlledForm.title, workflow: controlledForm.workflow, dms_document_id: controlledForm.dms_document_id || null, dms_revision_id: controlledForm.dms_revision_id || null, retention_rule: controlledForm.retention_rule || null, schema_json: { fields: parseLines(controlledForm.fields) } }); setControlledForm(formDraft()); setFormOpen(false); }, "Controlled form revision created.")}>Create revision</button></div></div>
      </Drawer>

      <Drawer title="Create assessment template" isOpen={assessmentOpen} onClose={() => setAssessmentOpen(false)} panelClassName="training-form-drawer">
        <div className="tos-drawer-form"><label>Code<input value={assessmentForm.code} onChange={(event) => setAssessmentForm({ ...assessmentForm, code: event.target.value })} /></label><label>Name<input value={assessmentForm.name} onChange={(event) => setAssessmentForm({ ...assessmentForm, name: event.target.value })} /></label><label>Type<select value={assessmentForm.assessment_type} onChange={(event) => setAssessmentForm({ ...assessmentForm, assessment_type: event.target.value })}>{["WRITTEN", "ORAL", "PRACTICAL", "OJT", "OBSERVATION", "SUPERVISOR_REVIEW", "PERFORMANCE_REVIEW", "TRAINING_EFFECTIVENESS"].map((item) => <option key={item}>{item}</option>)}</select></label><label>Outcome scheme<select value={assessmentForm.outcome_scheme} onChange={(event) => setAssessmentForm({ ...assessmentForm, outcome_scheme: event.target.value })}><option>NUMERIC</option><option>PASS_FAIL</option><option>COMPETENT</option><option>SATISFACTORY</option><option>STRUCTURED</option></select></label><label>Pass threshold<input type="number" min="0" max="100" value={assessmentForm.pass_threshold} onChange={(event) => setAssessmentForm({ ...assessmentForm, pass_threshold: event.target.value })} /></label><label>Manual / DMS reference<input value={assessmentForm.manual_reference} onChange={(event) => setAssessmentForm({ ...assessmentForm, manual_reference: event.target.value })} /></label><label>Criteria (one <code>sequence|question|type|mandatory|marks</code> per line)<textarea value={assessmentForm.questions} onChange={(event) => setAssessmentForm({ ...assessmentForm, questions: event.target.value })} /></label><div className="tos-actions"><button onClick={() => setAssessmentOpen(false)}>Cancel</button><button className="primary-chip-btn" disabled={busy || !assessmentForm.code || !assessmentForm.name} onClick={() => void run(async () => { const questions = assessmentForm.questions.split("\n").map((line) => line.trim()).filter(Boolean).map((line, index) => { const [sequence, question_text, response_type, mandatory, marks] = line.split("|").map((item) => item.trim()); return { sequence_no: Number(sequence || index + 1), question_text, response_type: response_type || "TEXT", mandatory: mandatory === "true", marks: Number(marks || 0), answer_options: [], evaluation_rule: {} }; }); await createAssessmentTemplate({ ...assessmentForm, pass_threshold: assessmentForm.pass_threshold ? Number(assessmentForm.pass_threshold) : null, manual_reference: assessmentForm.manual_reference || null, questions }); setAssessmentForm(assessmentDraft()); setAssessmentOpen(false); }, "Assessment template and criteria created.")}>Create template</button></div></div>
      </Drawer>
    </div>
  );
};

export default TrainingSetupWorkspace;
