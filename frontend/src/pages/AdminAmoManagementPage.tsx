import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { Button, InlineAlert, PageHeader, Panel } from "../components/UI/Admin";
import { apiGet, apiPut } from "../services/crs";
import type { AdminAmoRead } from "../services/adminUsers";
import "../styles/tenant-administration.css";

type Profile = Pick<AdminAmoRead, "name" | "icao_code" | "country" | "contact_email" | "contact_phone" | "time_zone">;
const fields: { key: keyof Profile; label: string; type?: string; placeholder?: string }[] = [
  { key: "name", label: "Organisation name" },
  { key: "icao_code", label: "ICAO code" },
  { key: "country", label: "Country" },
  { key: "contact_email", label: "Contact email", type: "email" },
  { key: "contact_phone", label: "Contact phone", type: "tel" },
  { key: "time_zone", label: "Time zone", placeholder: "Africa/Nairobi" },
];
const toProfile = (amo: AdminAmoRead): Profile => Object.fromEntries(fields.map(({ key }) => [key, amo[key] ?? ""])) as Profile;

export default function AdminAmoManagementPage() {
  const { amoCode = "" } = useParams();
  const base = `/maintenance/${encodeURIComponent(amoCode)}`;
  const [amo, setAmo] = useState<AdminAmoRead | null>(null);
  const [draft, setDraft] = useState<Profile | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setAmo(null); setDraft(null); setError(""); setSaved(false);
    apiGet<AdminAmoRead>("/accounts/admin/organisation", { offline: { cache: false, allowStaleFallback: false } })
      .then((value) => { if (!cancelled) { setAmo(value); setDraft(toProfile(value)); } })
      .catch((cause) => { if (!cancelled) setError(cause?.message || "Organisation details could not be loaded."); });
    return () => { cancelled = true; };
  }, [amoCode, reload]);
  const dirty = Boolean(amo && draft && JSON.stringify(draft) !== JSON.stringify(toProfile(amo)));
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!draft || saving) return;
    setSaving(true); setError(""); setSaved(false);
    try {
      const payload = Object.fromEntries(fields.map(({ key }) => [key, String(draft[key] || "").trim() || null]));
      const value = await apiPut<AdminAmoRead>("/accounts/admin/organisation", payload);
      setAmo(value); setDraft(toProfile(value)); setSaved(true);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "The organisation could not be saved."); }
    finally { setSaving(false); }
  }
  const workflows = [
    ["People & access", "Enrol people, assign departments and manage employment changes.", "admin/users"],
    ["Organisation structure", "Maintain positions, reporting lines and personnel appointments.", "rostering/settings?section=workforce&workforce_view=governance"],
    ["Administrator governance", "Appoint administrators, review requests and manage appointment duration.", "access-governance"],
    ["Bases & departments", "Maintain operating locations and department enrolment destinations.", "admin/amo-assets?section=bases"],
    ["Release assets", "Upload, preview and download the AMO logo and CRS PDF template.", "admin/amo-assets?section=assets"],
    ["Access profiles", "Review the role reference tree and configure module permissions.", "admin/users?tab=roles"],
  ];
  return <DepartmentLayout amoCode={amoCode} activeDepartment="admin-amos">
    <div className="admin-page tenant-administration">
      <PageHeader title="AMO Management" subtitle="Organisation details, people and operating setup for your AMO." />
      {error && <InlineAlert tone="danger" title="Unable to complete request"><span>{error}</span>{!amo && <Button onClick={() => setReload((value) => value + 1)}>Retry</Button>}</InlineAlert>}
      {saved && <InlineAlert tone="success" title="Organisation saved"><span>Your AMO details have been updated.</span></InlineAlert>}
      <div className="tenant-administration__grid">
        <Panel title={amo?.name || "Organisation profile"} subtitle={amo ? `${amo.amo_code} / ${amo.is_active ? "Active" : "Inactive"} / Login: ${amo.login_slug}` : "Loading your AMO..."}>
          {draft && <form className="form-grid" onSubmit={save}>
            {fields.map(({ key, label, type, placeholder }) => <div className="form-row" key={key}>
              <label htmlFor={`amo-${key}`}>{label}</label>
              <input id={`amo-${key}`} type={type || "text"} required={key === "name"} placeholder={placeholder} value={draft[key] || ""} disabled={saving}
                onChange={(event) => { setDraft({ ...draft, [key]: event.target.value }); setSaved(false); }} />
            </div>)}
            <div className="tenant-administration__actions">
              <Button type="submit" disabled={!dirty || saving}>{saving ? "Saving..." : "Save organisation"}</Button>
              <Button type="button" variant="secondary" disabled={!dirty || saving} onClick={() => amo && setDraft(toProfile(amo))}>Discard changes</Button>
            </div>
          </form>}
        </Panel>
        <Panel title="Administration workflows" subtitle="Open the workspace for the task you need to complete.">
          <nav className="tenant-administration__links" aria-label="AMO administration workflows">
            {workflows.map(([title, description, route]) => <Link key={route} to={`${base}/${route}`}><strong>{title}</strong><span>{description}</span></Link>)}
          </nav>
        </Panel>
      </div>
    </div>
  </DepartmentLayout>;
}
