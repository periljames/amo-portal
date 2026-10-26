import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowRight, Settings, Hash, Bell, ShieldCheck, Workflow, Building2, SlidersHorizontal } from "lucide-react";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { apiRequest, qmsPath } from "../../services/apiClient";
import { hasQmsRolePermission } from "../../app/routeGuards";
import { eventLabel, type AmoCompliancePolicy, type RetentionExtensions } from "../../services/amoCompliancePolicy";

import QmsMailIdentityPage from "./QmsMailIdentityPage";
import QmsFollowUpControls from "./QmsFollowUpControls";
import QmsNumberingControls from "./QmsNumberingControls";
import { validNumbering } from "./numberingRules";
import "./qms-settings.css";

type Value = string | number | boolean | null | Value[] | { [key: string]: Value };
type Configuration = Record<string, Value>;
const sections = [
  { id: "general", label: "Overview", description: "Quality configuration and the workspaces that own it.", keys: [] },
  { id: "workflows", label: "Workflows & approvals", description: "Review workflow, approval and risk policies.", keys: [] },
  { id: "numbering", label: "Numbering", description: "Reference rules for Quality records.", keys: ["numbering_rules"] },
  { id: "notifications", label: "Notifications", description: "Email identity, reply addresses and notification rules.", keys: [] },
  { id: "retention", label: "Retention", description: "Retention policies and governed evidence.", keys: ["retention_rules"] },
];
const icons = { general: SlidersHorizontal, workflows: Workflow, numbering: Hash, notifications: Bell, retention: ShieldCheck };

export default function QmsSettingsPage() {
  const queryClient = useQueryClient();
  const { amoCode = "", "*": tail = "" } = useParams();
  const selected = sections.find(section => section.id === tail) || sections[0];
  const base = `/maintenance/${encodeURIComponent(amoCode)}/quality`;
  const [settings, setSettings] = useState<Configuration | null>(null);
  const [tenant, setTenant] = useState(amoCode);
  const [policy, setPolicy] = useState<AmoCompliancePolicy | null>(null);
  const [draft, setDraft] = useState<Configuration>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const errorRef = useRef<HTMLDivElement>(null);
  useEffect(() => { if (error) errorRef.current?.scrollIntoView({ block: "nearest" }); }, [error]);
  const [notice, setNotice] = useState("");
  const canManage = hasQmsRolePermission("qms.settings.manage");
  const dirty = selected.keys.some(key => JSON.stringify(draft[key]) !== JSON.stringify(settings?.[key]));
  const extensions = (draft.retention_rules || {}) as RetentionExtensions;
  const invalidNumbering = selected.id === "numbering" && !validNumbering(draft.numbering_rules);
  const invalidRetention = selected.id === "retention" && Boolean(policy?.retention.some(rule => {
    const value = (rule.years ? extensions.extensions_years : extensions.extensions_days)?.[rule.code];
    return value !== undefined && (!Number.isInteger(value) || value < (rule.years || rule.days) || value > (rule.years ? 100 : 36500));
  }));
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const response = await apiRequest<{ tenant?: { amo_code: string }; settings: Configuration | null; compliance_policy: AmoCompliancePolicy }>(qmsPath(amoCode, "/settings"), { cacheTtlMs: 0 }); setTenant(response.tenant?.amo_code || amoCode); setSettings(response.settings || {}); setDraft(response.settings || {}); setPolicy(response.compliance_policy); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load QMS settings."); }
    finally { setLoading(false); }
  }, [amoCode]);
  useEffect(() => { void load(); }, [load]);
  async function save(event: React.FormEvent) {
    event.preventDefault(); if (!canManage || !dirty || saving || invalidRetention || invalidNumbering) return;
    setSaving(true); setError(""); setNotice("");
    try {
      const keys = selected.keys.filter(key => JSON.stringify(draft[key]) !== JSON.stringify(settings?.[key]));
      const latest = await apiRequest<{ settings: Configuration | null }>(qmsPath(amoCode, "/settings"), { cacheTtlMs: 0 });
      if (keys.some(key => JSON.stringify(latest.settings?.[key]) !== JSON.stringify(settings?.[key]))) throw new Error("These settings changed while you were editing. Your entries are retained. Reload the current settings before saving.");
      const changes = Object.fromEntries(keys.map(key => [key, draft[key]]));
      const result = await apiRequest<{ settings: Configuration }>(qmsPath(amoCode, "/settings"), { method: "PATCH", headers: { "Content-Type": "application/json", "X-AMO-Silent-Error": "1" }, body: JSON.stringify({ ...changes, expected_settings: Object.fromEntries(keys.map(key => [key, settings?.[key] ?? {}])) }) });
      setSettings(result.settings); setDraft(previous => ({ ...previous, ...Object.fromEntries(keys.map(key => [key, result.settings[key]])) })); setNotice("Settings saved and recorded in Quality activity history.");
      if (keys.includes("numbering_rules")) { void queryClient.invalidateQueries({ queryKey: ["qms-workflow-settings", amoCode] }); void queryClient.invalidateQueries({ queryKey: ["qms-audit-scopes", amoCode] }); }
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Settings could not be saved. Your entries are retained."); }
    finally { setSaving(false); }
  }
  return <DepartmentLayout amoCode={amoCode} activeDepartment="quality"><div className="qms-settings-page">
    <header className="qms-settings__header"><h1>Settings{selected.id !== "general" ? ` · ${selected.label}` : ""}</h1><Settings size={22} /></header>
    <div className="qms-settings__scope"><Building2 size={16} /><strong>{tenant}</strong><span>Tenant configuration</span><span className="qms-settings__access">{canManage ? "Can configure" : "Read only"}</span></div>
    <nav className="qms-settings__tabs" aria-label="Settings sections">{sections.map(section => { const Icon = icons[section.id as keyof typeof icons]; return <Link key={section.id} to={`${base}/settings/${section.id}`} aria-current={selected.id === section.id ? "page" : undefined}><Icon size={17} /><span>{section.label}</span></Link>; })}</nav>
    {error && <div ref={errorRef} role="alert" data-portal-error-feedback className="qms-settings__error">{error}<button type="button" onClick={() => void load()} disabled={loading}>Reload settings</button></div>}
    {notice && <p role="status" className="qms-settings__success">{notice}</p>}
    {loading ? <p role="status">Loading Quality settings…</p> : settings && <>
      {!canManage && <p>You have read-only access to this configuration.</p>}
      {selected.id === "general" ? <div className="qms-settings__cards">{sections.slice(1).map(section => <Link className="qms-settings__card" to={`${base}/settings/${section.id}`} key={section.id}><h2>{(() => { const Icon = icons[section.id as keyof typeof icons]; return <Icon size={21} />; })()}{section.label}<ArrowRight size={18} /></h2><p>{section.description}</p><span>Open configuration</span></Link>)}</div> : <>
        {selected.id === "notifications" && <QmsMailIdentityPage embedded />}
        {selected.id === "workflows" && <Link className="qms-settings__card" to={`${base}/audits/program`}><h2>Audit programme & notice controls <ArrowRight size={18} /></h2><p>Manage audit work and governed notices at their source.</p></Link>}
        {selected.id === "retention" && <Link className="qms-settings__card" to={`${base}/evidence-vault/immutable-archive`}><h2>Retained evidence <ArrowRight size={18} /></h2><p>Open retained evidence and source records.</p></Link>}
        {selected.id === "workflows" && <QmsFollowUpControls amoCode={amoCode} disabled={!canManage} />}
        <form onSubmit={event => void save(event)} className="qms-settings__form">
          {selected.id === "numbering" ? <QmsNumberingControls revision={String(settings.updated_at || "")} amoCode={amoCode} value={draft.numbering_rules} disabled={!canManage || saving} onChange={value => setDraft(previous => ({ ...previous, numbering_rules: value }))} /> : selected.id === "retention" ? <section className="qms-settings__card"><h2>MOPM retention minimums</h2><p>Event dates govern retention. Missing dates and preservation holds prevent disposal. Tenant periods may only be longer.</p><div className="qms-retention-policy">{policy?.retention.map(rule => {
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
          })}</div><h3>Contracting controls</h3><p>Current approved AMO, scope, site, written agreement and authority access are required. Further subcontracting needs prior written acceptance. Complete type-certificated product contracting is excluded.</p><small>{policy?.contracting.reference}</small></section> : null}
          {canManage && selected.keys.length > 0 && <footer className="qms-settings__save"><span>{dirty ? "Unsaved changes" : "No unsaved changes"}</span><button type="button" disabled={!dirty || saving} onClick={() => setDraft(previous => ({ ...previous, ...Object.fromEntries(selected.keys.map(key => [key, settings[key]])) }))}>Discard changes</button><button type="submit" disabled={!dirty || saving || invalidRetention || invalidNumbering}>{saving ? "Saving…" : "Save changes"}</button></footer>}
        </form>
      </>}
    </>}
  </div></DepartmentLayout>;
}
