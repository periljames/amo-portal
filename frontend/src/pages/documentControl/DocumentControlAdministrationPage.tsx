import { useCallback, useEffect, useState } from "react";
import {
  Archive,
  BellRing,
  Boxes,
  FileCog,
  FileStack,
  FolderTree,
  History,
  Link2,
  Plus,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  getDocumentControlAdministration,
  updateDocumentControlAdministration,
  type DocumentControlAdministration,
} from "../../services/documentControlReports";
import DocumentControlShell, {
  DocumentControlEmpty,
  DocumentControlError,
  DocumentControlLoading,
  DocumentControlSection,
} from "./DocumentControlShell";
import { useDocumentControlRoute } from "./documentControlRoute";
import "./dmsHome.css";
import "./dmsAdministration.css";

function formatAuditTime(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function parseLeadDays(value: string): number[] {
  return Array.from(new Set(
    value
      .split(",")
      .map((item) => Number(item.trim()))
      .filter((item) => Number.isInteger(item) && item >= 1 && item <= 365),
  )).sort((a, b) => b - a);
}

export default function DocumentControlAdministrationPage() {
  const navigate = useNavigate();
  const { tenant, basePath } = useDocumentControlRoute();
  const [settings, setSettings] = useState<DocumentControlAdministration | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [classText, setClassText] = useState("");
  const [integrationText, setIntegrationText] = useState("");
  const [reminderLeadText, setReminderLeadText] = useState("30, 14, 7");

  const load = useCallback(async () => {
    if (!tenant) return;
    setLoading(true);
    setError("");
    try {
      const next = await getDocumentControlAdministration(tenant);
      setSettings(next);
      setClassText(next.document_classes.join(", "));
      setIntegrationText(next.integration_modules.join(", "));
      setReminderLeadText(next.reminder_policy.lead_days.join(", "));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Document Control administration could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [tenant]);

  useEffect(() => { void load(); }, [load]);

  const save = async () => {
    if (!settings) return;
    const reminderLeadDays = parseLeadDays(reminderLeadText);
    if (!reminderLeadDays.length) {
      setError("Reminder lead days must contain at least one whole number between 1 and 365.");
      return;
    }
    if (settings.reminder_policy.quality_escalation_days < settings.reminder_policy.owner_escalation_days) {
      setError("Quality escalation cannot occur before the governed document-owner escalation.");
      return;
    }
    setSaving(true);
    setSaved(false);
    setError("");
    try {
      const documentClasses = classText.split(",").map((value) => value.trim()).filter(Boolean);
      const integrationModules = integrationText.split(",").map((value) => value.trim()).filter(Boolean);
      const next = await updateDocumentControlAdministration(tenant, {
        default_retention_years: settings.default_retention_years,
        default_review_interval_months: settings.default_review_interval_months,
        regulated_workflow_enabled: settings.regulated_workflow_enabled,
        default_ack_required: settings.default_ack_required,
        document_classes: documentClasses,
        workflow_policy: settings.workflow_policy,
        retention_classes: settings.retention_classes,
        indexing_policy: settings.indexing_policy,
        integration_modules: integrationModules,
        physical_copy_policy: settings.physical_copy_policy,
        reminder_policy: { ...settings.reminder_policy, lead_days: reminderLeadDays },
      });
      setSettings(next);
      setClassText(next.document_classes.join(", "));
      setIntegrationText(next.integration_modules.join(", "));
      setReminderLeadText(next.reminder_policy.lead_days.join(", "));
      setSaved(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Document Control administration could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  const updateRetention = (index: number, key: "code" | "label" | "years", value: string | number) => {
    if (!settings) return;
    const next = settings.retention_classes.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item);
    setSettings({ ...settings, retention_classes: next });
  };

  const addRetention = () => {
    if (!settings) return;
    setSettings({ ...settings, retention_classes: [...settings.retention_classes, { code: "NEW", label: "New retention class", years: settings.default_retention_years }] });
  };

  const removeRetention = (index: number) => {
    if (!settings) return;
    setSettings({ ...settings, retention_classes: settings.retention_classes.filter((_item, itemIndex) => itemIndex !== index) });
  };

  const auditHistory = settings?.audit_history || [];

  return <DocumentControlShell
    title="Administration"
    eyebrow="LOW-FREQUENCY CONTROL"
    subtitle="Tenant-wide Document Control policy, defaults, reminders and specialist administration. Operational approvals and evidence remain in their owning workspaces."
    canControl
    actions={<><button type="button" className="dc-button" onClick={() => void load()}><RefreshCw size={14} /> Refresh</button><button type="button" className="dc-button dc-button--primary" disabled={saving || !settings} onClick={() => void save()}>{saving ? "Saving…" : "Save administration"}</button></>}
  >
    <div className="dms-admin" data-testid="document-control-administration">
      {loading ? <DocumentControlLoading label="Loading governed Document Control administration…" /> : null}
      {error ? <DocumentControlError message={error} retry={() => void load()} /> : null}

      {!loading && settings ? <>
        {saved ? <div className="dc-callout dc-callout--success" role="status"><ShieldCheck size={16} /> Document Control administration saved with audit evidence.</div> : null}

        <DocumentControlSection title="Governance defaults" description="Defaults applied to new controlled-information work. Existing approved evidence is never rewritten by changing these values.">
          <form className="dc-form dms-admin__grid" onSubmit={(event) => { event.preventDefault(); void save(); }}>
            <label><span>Default retention years</span><input aria-label="Default retention years" type="number" min={1} max={100} value={settings.default_retention_years} onChange={(event) => setSettings({ ...settings, default_retention_years: Number(event.target.value) })} /></label>
            <label><span>Default review interval months</span><input aria-label="Default review interval months" type="number" min={1} max={120} value={settings.default_review_interval_months} onChange={(event) => setSettings({ ...settings, default_review_interval_months: Number(event.target.value) })} /></label>
            <label className="dms-admin__wide"><span>Document classes</span><input aria-label="Document classes" value={classText} onChange={(event) => setClassText(event.target.value)} placeholder="INTERNAL, EXTERNAL, RECORD" /><small>Comma-separated governed class identifiers.</small></label>
            <label><span><input type="checkbox" checked={settings.regulated_workflow_enabled} onChange={(event) => setSettings({ ...settings, regulated_workflow_enabled: event.target.checked })} /> Enable regulated-workflow defaults</span></label>
            <label><span><input type="checkbox" checked={settings.default_ack_required} onChange={(event) => setSettings({ ...settings, default_ack_required: event.target.checked })} /> Require acknowledgement by default</span></label>
          </form>
        </DocumentControlSection>

        <DocumentControlSection title="Workflow policy" description="Defines which review gates new controlled changes expect. Backend workflow state and individual decision authority remain authoritative.">
          <div className="dms-admin__policy-grid">
            <label><input type="checkbox" checked={settings.workflow_policy.technical_review_required} onChange={(event) => setSettings({ ...settings, workflow_policy: { ...settings.workflow_policy, technical_review_required: event.target.checked } })} /> Technical review required</label>
            <label><input type="checkbox" checked={settings.workflow_policy.quality_review_required} onChange={(event) => setSettings({ ...settings, workflow_policy: { ...settings.workflow_policy, quality_review_required: event.target.checked } })} /> Quality review required</label>
            <label><input type="checkbox" checked={settings.workflow_policy.management_approval_required} onChange={(event) => setSettings({ ...settings, workflow_policy: { ...settings.workflow_policy, management_approval_required: event.target.checked } })} /> Management approval required</label>
            <label><span>Authority routing</span><select aria-label="Authority routing policy" value={settings.workflow_policy.authority_routing} onChange={(event) => setSettings({ ...settings, workflow_policy: { ...settings.workflow_policy, authority_routing: event.target.value as DocumentControlAdministration["workflow_policy"]["authority_routing"] } })}><option value="WHEN_REQUIRED">When required</option><option value="ALWAYS">Always</option><option value="NEVER">Never by default</option></select></label>
          </div>
        </DocumentControlSection>

        <DocumentControlSection title="Reminder and escalation policy" description="Controls accountable due-work reminders. Each reminder stage is stored once in an immutable delivery ledger, so an hourly scheduler cannot repeatedly notify the same person for the same threshold.">
          <div className="dms-admin__policy-grid" data-testid="document-control-reminder-policy">
            <label><input type="checkbox" checked={settings.reminder_policy.enabled} onChange={(event) => setSettings({ ...settings, reminder_policy: { ...settings.reminder_policy, enabled: event.target.checked } })} /> Enable Document Control reminders</label>
            <label><input type="checkbox" checked={settings.reminder_policy.portal_notifications_enabled} onChange={(event) => setSettings({ ...settings, reminder_policy: { ...settings.reminder_policy, portal_notifications_enabled: event.target.checked } })} /> Portal notifications</label>
            <label><input type="checkbox" checked={settings.reminder_policy.email_notifications_enabled} onChange={(event) => setSettings({ ...settings, reminder_policy: { ...settings.reminder_policy, email_notifications_enabled: event.target.checked } })} /> Email reminders when tenant delivery policy permits</label>
            <label className="dms-admin__wide"><span>Lead reminder days</span><input aria-label="Document Control reminder lead days" value={reminderLeadText} onChange={(event) => setReminderLeadText(event.target.value)} placeholder="30, 14, 7" /><small>Comma-separated whole days before the due date. A threshold is sent once per obligation and recipient.</small></label>
            <label><span>Repeat overdue every</span><input aria-label="Document Control overdue repeat days" type="number" min={1} max={90} value={settings.reminder_policy.overdue_repeat_days} onChange={(event) => setSettings({ ...settings, reminder_policy: { ...settings.reminder_policy, overdue_repeat_days: Number(event.target.value) } })} /><small>Days between overdue stages.</small></label>
            <label><span>Escalate to document owner after</span><input aria-label="Document owner escalation days" type="number" min={1} max={365} value={settings.reminder_policy.owner_escalation_days} onChange={(event) => setSettings({ ...settings, reminder_policy: { ...settings.reminder_policy, owner_escalation_days: Number(event.target.value) } })} /><small>Overdue days.</small></label>
            <label><span>Escalate to Quality after</span><input aria-label="Quality escalation days" type="number" min={1} max={365} value={settings.reminder_policy.quality_escalation_days} onChange={(event) => setSettings({ ...settings, reminder_policy: { ...settings.reminder_policy, quality_escalation_days: Number(event.target.value) } })} /><small>Overdue days; must not precede document-owner escalation.</small></label>
          </div>
          <div className="dc-callout"><BellRing size={16} /><div><strong>Covered obligations</strong><div>Periodic reviews, temporary-revision expiry, external-source currency checks, controlled-copy returns, authority responses and distribution acknowledgements. Personal reminders are routed only to authoritative owners, holders, submitters or recipients.</div></div></div>
        </DocumentControlSection>

        <DocumentControlSection title="Retention classes" description="Reusable retention classifications for generated controlled evidence." actions={<button type="button" className="dc-button" onClick={addRetention}><Plus size={14} /> Add class</button>}>
          <div className="dms-admin__retention">
            {settings.retention_classes.map((item, index) => <div key={`${String(item.code || "class")}-${index}`}>
              <input aria-label={`Retention class ${index + 1} code`} value={String(item.code || "")} onChange={(event) => updateRetention(index, "code", event.target.value)} placeholder="Code" />
              <input aria-label={`Retention class ${index + 1} label`} value={String(item.label || "")} onChange={(event) => updateRetention(index, "label", event.target.value)} placeholder="Label" />
              <input aria-label={`Retention class ${index + 1} years`} type="number" min={1} max={100} value={Number(item.years || settings.default_retention_years)} onChange={(event) => updateRetention(index, "years", Number(event.target.value))} />
              <button type="button" aria-label={`Remove retention class ${index + 1}`} onClick={() => removeRetention(index)}><Trash2 size={14} /></button>
            </div>)}
          </div>
        </DocumentControlSection>

        <DocumentControlSection title="Indexing and integration policy" description="Controls automatic controlled-content indexing and records which portal modules participate in governed Document Control relationships.">
          <div className="dms-admin__grid">
            <label><span><input type="checkbox" checked={settings.indexing_policy.auto_index_on_publish} onChange={(event) => setSettings({ ...settings, indexing_policy: { ...settings.indexing_policy, auto_index_on_publish: event.target.checked } })} /> Auto-index on publication</span></label>
            <label><span><input type="checkbox" checked={settings.indexing_policy.require_source_hash} onChange={(event) => setSettings({ ...settings, indexing_policy: { ...settings.indexing_policy, require_source_hash: event.target.checked } })} /> Require source checksum before indexing</span></label>
            <label><span>Index retry limit</span><input aria-label="Index retry limit" type="number" min={0} max={20} value={settings.indexing_policy.retry_limit} onChange={(event) => setSettings({ ...settings, indexing_policy: { ...settings.indexing_policy, retry_limit: Number(event.target.value) } })} /></label>
            <label className="dms-admin__wide"><span>Governed integration modules</span><input aria-label="Governed integration modules" value={integrationText} onChange={(event) => setIntegrationText(event.target.value)} placeholder="QMS, TRAINING, PLANNING, PROCUREMENT" /><small>Comma-separated source modules permitted to create governed relationship mappings.</small></label>
          </div>
        </DocumentControlSection>

        <DocumentControlSection title="Physical controlled-copy policy" description="Default custody controls for new numbered copies. Existing custody evidence remains immutable.">
          <div className="dms-admin__policy-grid">
            <label><span>Default return days</span><input aria-label="Default physical copy return days" type="number" min={1} max={3650} value={settings.physical_copy_policy.default_due_days} onChange={(event) => setSettings({ ...settings, physical_copy_policy: { ...settings.physical_copy_policy, default_due_days: Number(event.target.value) } })} /></label>
            <label><input type="checkbox" checked={settings.physical_copy_policy.custody_acknowledgement_required} onChange={(event) => setSettings({ ...settings, physical_copy_policy: { ...settings.physical_copy_policy, custody_acknowledgement_required: event.target.checked } })} /> Custody acknowledgement required</label>
            <label><input type="checkbox" checked={settings.physical_copy_policy.location_verification_required} onChange={(event) => setSettings({ ...settings, physical_copy_policy: { ...settings.physical_copy_policy, location_verification_required: event.target.checked } })} /> Location verification required</label>
            <label><input type="checkbox" checked={settings.physical_copy_policy.recall_on_supersession} onChange={(event) => setSettings({ ...settings, physical_copy_policy: { ...settings.physical_copy_policy, recall_on_supersession: event.target.checked } })} /> Recall copies on supersession</label>
          </div>
        </DocumentControlSection>

        <DocumentControlSection title="Administration audit history" description={`The latest ${settings.audit_history_limit || 25} policy changes are retained server-side and shown here for controller verification.`}>
          {auditHistory.length ? <div className="dc-table-wrap" data-testid="administration-audit-history"><table className="dc-table"><thead><tr><th>When</th><th>Action</th><th>Actor</th><th>Evidence</th></tr></thead><tbody>{auditHistory.map((item) => <tr key={item.id}><td>{formatAuditTime(item.at)}</td><td><strong>{item.action}</strong></td><td>{item.actor_id || "System"}</td><td>{item.changes?.before && item.changes?.after ? "Before / after retained" : "Change payload retained"}</td></tr>)}</tbody></table></div> : <DocumentControlEmpty icon={History} title="No administration changes yet" message="The first governed administration change will appear here after it is saved." />}
        </DocumentControlSection>

        <DocumentControlSection title="Administrative tools" description="Specialist configuration remains available without occupying permanent DMS navigation.">
          <div className="dms-home__quick-actions dms-admin__tools">
            <button type="button" onClick={() => navigate(`${basePath}/library?sort=type&direction=asc`)}><FolderTree size={16} /><span><strong>Hierarchy & taxonomy</strong><small>Review controlled document structure and aliases</small></span></button>
            <button type="button" onClick={() => navigate(`${basePath}/library?type=FORM`)}><FileStack size={16} /><span><strong>Controlled templates</strong><small>Review form and template source documents</small></span></button>
            <button type="button" onClick={() => navigate(`${basePath}/reports?view=retention`)}><Archive size={16} /><span><strong>Retained generated records</strong><small>Review retention and disposition evidence</small></span></button>
            <button type="button" onClick={() => navigate(`${basePath}/distribution?view=physical-copies`)}><Boxes size={16} /><span><strong>Physical copy operations</strong><small>Register, locate, recall and reconcile numbered copies</small></span></button>
            <button type="button" onClick={() => navigate(`${basePath}/compliance?view=relationships`)}><Link2 size={16} /><span><strong>Integration mappings</strong><small>Review governed cross-module relationships</small></span></button>
            <button type="button" onClick={() => navigate(`${basePath}/library?indexing_status=FAILED`)}><FileCog size={16} /><span><strong>Indexing exceptions</strong><small>Resolve documents requiring indexing attention</small></span></button>
          </div>
        </DocumentControlSection>
      </> : null}
    </div>
  </DocumentControlShell>;
}
