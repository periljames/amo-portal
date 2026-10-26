import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowRight, Settings } from "lucide-react";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { apiRequest, qmsPath } from "../../services/apiClient";
import { hasQmsRolePermission } from "../../app/routeGuards";
import { eventLabel, type AmoCompliancePolicy, type RetentionExtensions } from "../../services/amoCompliancePolicy";

type Value = string | number | boolean | null | Value[] | { [key: string]: Value };
type Configuration = Record<string, Value>;
const sections = [
  { id: "general", label: "Overview", description: "Quality configuration and the workspaces that own it.", keys: [] },
  { id: "workflows", label: "Workflows & approvals", description: "Review workflow, approval and risk policies.", keys: ["workflow_rules", "approval_matrix", "risk_matrix"] },
  { id: "numbering", label: "Numbering", description: "Reference rules for Quality records.", keys: ["numbering_rules"] },
  { id: "notifications", label: "Notifications", description: "Email identity, reply addresses and notification rules.", keys: ["notification_rules"] },
  { id: "retention", label: "Retention", description: "Retention policies and governed evidence.", keys: ["retention_rules"] },
];
const humanise = (key: string) => key.replaceAll("_", " ").replace(/\b\w/g, letter => letter.toUpperCase());

function PolicyFields({ value, onChange, label, disabled, depth = 0 }: { value: Value; onChange: (value: Value) => void; label: string; disabled: boolean; depth?: number }) {
  if (value === null) return <p>{label}: No override</p>;
  if (typeof value === "boolean") return <label className="qms-settings__toggle"><input type="checkbox" checked={value} disabled={disabled} onChange={event => onChange(event.target.checked)} /><span>{label}</span></label>;
  if (typeof value === "string" || typeof value === "number") return <label className="qms-settings__field"><span>{label}</span><input type={typeof value === "number" ? "number" : "text"} step={typeof value === "number" ? "any" : undefined} required={typeof value === "number"} value={value} disabled={disabled} onChange={event => { if (typeof value === "string") onChange(event.target.value); else if (event.target.value !== "" && Number.isFinite(event.target.valueAsNumber)) onChange(event.target.valueAsNumber); }} /></label>;
  if (Array.isArray(value) || depth > 4) return <div><strong>{label}</strong><p>Structured policy entries are managed in their source workflow.</p></div>;
  if (!Object.keys(value).length) return <p className="qms-settings__default">No tenant overrides configured. The source workflow applies its governed defaults.</p>;
  return <div className="qms-settings__fields">{Object.entries(value).map(([key, item]) => <fieldset key={key}><legend>{typeof item === "object" && item !== null ? humanise(key) : undefined}</legend><PolicyFields label={humanise(key)} value={item} disabled={disabled || key === "independence_policy"} depth={depth + 1} onChange={next => onChange({ ...value, [key]: next })} />{key === "independence_policy" && <small>Auditor independence policy is governed by platform administration.</small>}</fieldset>)}</div>;
}

export default function QmsSettingsPage() {
  const { amoCode = "", "*": tail = "" } = useParams();
  const selected = sections.find(section => section.id === tail) || sections[0];
  const base = `/maintenance/${encodeURIComponent(amoCode)}/quality`;
  const [settings, setSettings] = useState<Configuration | null>(null);
  const [policy, setPolicy] = useState<AmoCompliancePolicy | null>(null);
  const [draft, setDraft] = useState<Configuration>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const canManage = hasQmsRolePermission("qms.settings.manage");
  const dirty = selected.keys.some(key => JSON.stringify(draft[key]) !== JSON.stringify(settings?.[key]));
  const extensions = (draft.retention_rules || {}) as RetentionExtensions;
  const invalidRetention = selected.id === "retention" && Boolean(policy?.retention.some(rule => {
    const value = (rule.years ? extensions.extensions_years : extensions.extensions_days)?.[rule.code];
    return value !== undefined && (!Number.isInteger(value) || value < (rule.years || rule.days) || value > (rule.years ? 100 : 36500));
  }));
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const response = await apiRequest<{ settings: Configuration | null; compliance_policy: AmoCompliancePolicy }>(qmsPath(amoCode, "/settings"), { cacheTtlMs: 0 }); setSettings(response.settings || {}); setDraft(response.settings || {}); setPolicy(response.compliance_policy); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load QMS settings."); }
    finally { setLoading(false); }
  }, [amoCode]);
  useEffect(() => { void load(); }, [load]);
  async function save(event: React.FormEvent) {
    event.preventDefault(); if (!canManage || !dirty || saving || invalidRetention) return;
    setSaving(true); setError(""); setNotice("");
    try {
      const keys = selected.keys.filter(key => JSON.stringify(draft[key]) !== JSON.stringify(settings?.[key]));
      const latest = await apiRequest<{ settings: Configuration | null }>(qmsPath(amoCode, "/settings"), { cacheTtlMs: 0 });
      if (keys.some(key => JSON.stringify(latest.settings?.[key]) !== JSON.stringify(settings?.[key]))) throw new Error("These settings changed while you were editing. Your entries are retained. Reload the current settings before saving.");
      const changes = Object.fromEntries(keys.map(key => [key, draft[key]]));
      const result = await apiRequest<{ settings: Configuration }>(qmsPath(amoCode, "/settings"), { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(changes) });
      setSettings(result.settings); setDraft(previous => ({ ...previous, ...Object.fromEntries(keys.map(key => [key, result.settings[key]])) })); setNotice("Settings saved and recorded in Quality activity history.");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Settings could not be saved. Your entries are retained."); }
    finally { setSaving(false); }
  }
  return <DepartmentLayout amoCode={amoCode} activeDepartment="quality"><div className="qms-settings-page">
    <header className="qms-settings__header"><h1>Settings{selected.id !== "general" ? ` · ${selected.label}` : ""}</h1><Settings size={22} /></header>
    {error && <div role="alert" className="qms-settings__error">{error}<button type="button" onClick={() => void load()} disabled={loading}>Reload settings</button></div>}
    {notice && <p role="status" className="qms-settings__success">{notice}</p>}
    {loading ? <p role="status">Loading Quality settings…</p> : settings && <>
      {!canManage && <p>You have read-only access to this configuration.</p>}
      {selected.id === "general" ? <div className="qms-settings__cards">{sections.slice(1).map(section => <Link className="qms-settings__card" to={`${base}/settings/${section.id}`} key={section.id}><h2>{section.label}<ArrowRight size={18} /></h2><p>{section.description}</p><span>Open configuration</span></Link>)}</div> : <>
        {selected.id === "notifications" && <Link className="qms-settings__card" to={`${base}/mail-identity/overview`}><h2>Email sender & reply addresses <ArrowRight size={18} /></h2><p>Choose the sender, add reply addresses one at a time, and check delivery readiness.</p></Link>}
        {selected.id === "workflows" && <Link className="qms-settings__card" to={`${base}/audits/program`}><h2>Audit programme & notice controls <ArrowRight size={18} /></h2><p>Manage audit work and governed notices at their source.</p></Link>}
        {selected.id === "retention" && <Link className="qms-settings__card" to={`${base}/evidence-vault/immutable-archive`}><h2>Retained evidence <ArrowRight size={18} /></h2><p>Open retained evidence and source records.</p></Link>}
        <form onSubmit={event => void save(event)} className="qms-settings__form">
          {selected.id === "retention" ? <section className="qms-settings__card"><h2>MOPM retention minimums</h2><p>Event dates govern retention. Missing dates and preservation holds prevent disposal. Tenant periods may only be longer.</p><div className="qms-retention-policy">{policy?.retention.map(rule => {
            const key = rule.years ? "extensions_years" : "extensions_days";
            const floor = rule.years || rule.days;
            const amount = extensions[key]?.[rule.code] ?? floor;
            const invalid = !Number.isInteger(amount) || amount < floor || amount > (rule.years ? 100 : 36500);
            return <div className="qms-retention-policy__row" key={rule.code}><div><strong>{rule.label}</strong><small>{floor ? `${floor} ${rule.years ? "years" : "days"} after ${eventLabel(rule.event).toLowerCase()}` : "Retain pending the governing Quality records schedule"}</small><small>{rule.reference}</small></div>{floor > 0 && <label><span>Tenant {rule.years ? "years" : "days"}</span><input aria-invalid={invalid} type="number" required min={floor} max={rule.years ? 100 : 36500} step={1} value={Number.isNaN(amount) ? "" : amount} disabled={!canManage || saving} onChange={event => {
              const next = { ...extensions[key] };
              const value = event.target.valueAsNumber;
              if (value === floor) delete next[rule.code]; else next[rule.code] = value;
              const updated: RetentionExtensions = { ...extensions, [key]: next };
              if (!Object.keys(next).length) delete updated[key];
              setDraft(previous => ({ ...previous, retention_rules: updated as Value }));
            }} />{invalid && <small role="status">Enter a whole number of at least {floor}.</small>}</label>}</div>;
          })}</div><h3>Contracting controls</h3><p>Current approved AMO, scope, site, written agreement and authority access are required. Further subcontracting needs prior written acceptance. Complete type-certificated product contracting is excluded.</p><small>{policy?.contracting.reference}</small></section> : selected.keys.map(key => <section className="qms-settings__card" key={key}><h2>{humanise(key)}</h2><PolicyFields label={humanise(key)} value={draft[key] ?? {}} disabled={!canManage || saving} onChange={value => setDraft(previous => ({ ...previous, [key]: value }))} /></section>)}
          {canManage && <footer className="qms-settings__save"><span>{dirty ? "Unsaved changes" : "No unsaved changes"}</span><button type="button" disabled={!dirty || saving} onClick={() => setDraft(previous => ({ ...previous, ...Object.fromEntries(selected.keys.map(key => [key, settings[key]])) }))}>Discard changes</button><button type="submit" disabled={!dirty || saving || invalidRetention}>{saving ? "Saving…" : "Save changes"}</button></footer>}
        </form>
      </>}
    </>}
  </div></DepartmentLayout>;
}
