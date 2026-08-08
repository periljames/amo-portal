import { useCallback, useEffect, useState } from "react";
import { Archive, Boxes, FolderTree, RefreshCw, Settings, ShieldCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";

import {
  getDocumentControlSettings,
  updateDocumentControlSettings,
  type DocumentControlSettings,
} from "../../services/documentControlReports";
import DocumentControlShell, {
  DocumentControlError,
  DocumentControlLoading,
  DocumentControlSection,
} from "./DocumentControlShell";
import { useDocumentControlRoute } from "./documentControlRoute";
import "./dmsHome.css";

export default function DocumentControlAdministrationPage() {
  const navigate = useNavigate();
  const { tenant, basePath } = useDocumentControlRoute();
  const [settings, setSettings] = useState<DocumentControlSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    if (!tenant) return;
    setLoading(true);
    setError("");
    try {
      setSettings(await getDocumentControlSettings(tenant));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Document Control administration could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [tenant]);

  useEffect(() => { void load(); }, [load]);

  const save = async () => {
    if (!settings) return;
    setSaving(true);
    setSaved(false);
    setError("");
    try {
      const next = await updateDocumentControlSettings(tenant, {
        default_retention_years: settings.default_retention_years,
        default_review_interval_months: settings.default_review_interval_months,
        regulated_workflow_enabled: settings.regulated_workflow_enabled,
        default_ack_required: settings.default_ack_required,
      });
      setSettings(next);
      setSaved(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Document Control administration could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  return <DocumentControlShell
    title="Administration"
    eyebrow="LOW-FREQUENCY CONTROL"
    subtitle="Tenant-wide Document Control defaults and governed administration entry points. Operational decisions remain in their owning workspaces."
    canControl
    actions={<button type="button" className="dc-button" onClick={() => void load()}><RefreshCw size={14} /> Refresh</button>}
  >
    <div data-testid="document-control-administration">
      {loading ? <DocumentControlLoading label="Loading Document Control administration…" /> : null}
      {error ? <DocumentControlError message={error} retry={() => void load()} /> : null}

      {!loading && settings ? <>
        <DocumentControlSection
          title="Governance defaults"
          description="Defaults applied to new controlled-information records. Changing these values does not rewrite existing approved evidence."
          actions={<button type="button" className="dc-button dc-button--primary" disabled={saving} onClick={() => void save()}>{saving ? "Saving…" : "Save defaults"}</button>}
        >
          {saved ? <div className="dc-callout dc-callout--success" role="status"><ShieldCheck size={16} /> Administration defaults saved.</div> : null}
          <form className="dc-form" onSubmit={(event) => { event.preventDefault(); void save(); }}>
            <label><span>Default retention years</span><input aria-label="Default retention years" type="number" min={1} max={100} value={settings.default_retention_years} onChange={(event) => setSettings({ ...settings, default_retention_years: Number(event.target.value) })} /></label>
            <label><span>Default review interval months</span><input aria-label="Default review interval months" type="number" min={1} max={120} value={settings.default_review_interval_months} onChange={(event) => setSettings({ ...settings, default_review_interval_months: Number(event.target.value) })} /></label>
            <label><span><input type="checkbox" checked={settings.regulated_workflow_enabled} onChange={(event) => setSettings({ ...settings, regulated_workflow_enabled: event.target.checked })} /> Enable regulated-workflow defaults</span></label>
            <label><span><input type="checkbox" checked={settings.default_ack_required} onChange={(event) => setSettings({ ...settings, default_ack_required: event.target.checked })} /> Require acknowledgement by default</span></label>
          </form>
        </DocumentControlSection>

        <DocumentControlSection title="Administrative tools" description="Specialist tools remain available without occupying permanent DMS navigation.">
          <div className="dms-home__quick-actions">
            <button type="button" onClick={() => navigate(`${basePath}/structure`)}><FolderTree size={16} /><span><strong>Hierarchy & taxonomy</strong><small>Review controlled document structure</small></span></button>
            <button type="button" onClick={() => navigate(`${basePath}/records`)}><Archive size={16} /><span><strong>Retained generated records</strong><small>Review controlled retained evidence</small></span></button>
            <button type="button" onClick={() => navigate(`${basePath}/controlled-copies`)}><Boxes size={16} /><span><strong>Physical copy operations</strong><small>Register, locate and reconcile numbered copies</small></span></button>
            <button type="button" onClick={() => navigate(`${basePath}/library?indexing_status=FAILED`)}><Settings size={16} /><span><strong>Indexing exceptions</strong><small>Resolve documents that require indexing attention</small></span></button>
          </div>
        </DocumentControlSection>
      </> : null}
    </div>
  </DocumentControlShell>;
}
