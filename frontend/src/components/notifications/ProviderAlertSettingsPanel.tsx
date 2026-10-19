import React, { useCallback, useEffect, useState } from "react";
import { BellRing, RefreshCw, Save } from "lucide-react";
import { apiRequest } from "../../services/apiClient";

type Dept = "QUALITY" | "PROCUREMENT" | "MAINTENANCE" | "STORES";
type Config = {
  lead_days: number[]; escalation_days: number[]; recipient_roles: string[];
  channels: { in_app: boolean; email: boolean }; templates: Record<string, string>;
};
type Policy = {
  revision: number; departments: Partial<Record<Dept, Config>>;
  catalog: Record<string, string>; digest: { enabled: boolean; hour: number };
  quiet_hours: { enabled: boolean; start: string; end: string };
  can_manage_delivery_window: boolean;
};
type Job = { id: string; event_key: string; due_at: string; status: string;
  attempts: number; last_error: string | null; email_log_id: string | null;
  email_processing_status: string | null; email_delivery_status: string | null;
  acknowledged_at: string | null };
const departmentRoles: Record<Dept, string[]> = {
  QUALITY: ["QUALITY_MANAGER", "QUALITY_OFFICER"],
  PROCUREMENT: ["PROCUREMENT_MANAGER", "PROCUREMENT_OFFICER"],
  MAINTENANCE: ["BASE_MAINTENANCE_MANAGER", "LINE_MAINTENANCE_MANAGER", "WORKSHOP_MANAGER"],
  STORES: ["STORES_MANAGER"],
};
const days = (value: string): number[] => {
  const parts = value.split(",").map((entry) => entry.trim()).filter(Boolean);
  if (parts.some((entry) => !/^\d+$/.test(entry))) throw new Error("Enter whole-day values separated by commas.");
  return parts.map(Number);
};

export default function ProviderAlertSettingsPanel({ amoCode, department }:
  { amoCode: string; department: Dept }): React.ReactElement {
  const [open, setOpen] = useState(false);
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [rows, setRows] = useState<Job[]>([]);
  const [lead, setLead] = useState("");
  const [escalation, setEscalation] = useState("");
  const [roles, setRoles] = useState<string[]>([]);
  const [email, setEmail] = useState(false);
  const [inApp, setInApp] = useState(true);
  const [templates, setTemplates] = useState<Record<string, string>>({});
  const [digest, setDigest] = useState(false);
  const [digestHour, setDigestHour] = useState(8);
  const [quiet, setQuiet] = useState(false);
  const [start, setStart] = useState("21:00");
  const [end, setEnd] = useState("07:00");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const root = "/api/maintenance/" + encodeURIComponent(amoCode) + "/provider-alerts";

  const load = useCallback(async () => {
    try {
      setError("");
      const [saved, delivery] = await Promise.all([
        apiRequest<Policy>(root + "/policy", { cacheTtlMs: 0 }),
        apiRequest<{ items: Job[] }>(root + "/delivery-history?department=" + department,
          { cacheTtlMs: 0 }),
      ]);
      const config = saved.departments[department];
      if (!config) throw new Error("Notification configuration requires an appointed departmental role.");
      setPolicy(saved); setRows(delivery.items);
      setLead(config.lead_days.join(", ")); setEscalation(config.escalation_days.join(", "));
      setRoles(config.recipient_roles); setEmail(config.channels.email);
      setInApp(config.channels.in_app); setTemplates(config.templates);
      setDigest(saved.digest.enabled); setDigestHour(saved.digest.hour);
      setQuiet(saved.quiet_hours.enabled); setStart(saved.quiet_hours.start);
      setEnd(saved.quiet_hours.end);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to load alert settings."); }
  }, [root, department]);
  useEffect(() => { if (open) void load(); }, [open, load]);

  async function save() {
    if (!policy) return;
    setBusy(true); setError(""); setMessage("");
    try {
      await apiRequest(root + "/policy/" + department, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          revision: policy.revision, lead_days: days(lead),
          escalation_days: days(escalation), recipient_roles: roles,
          in_app: inApp, email, templates,
          digest_enabled: digest, digest_hour: digestHour,
          quiet_enabled: quiet, quiet_start: start, quiet_end: end,
        }), cacheTtlMs: 0,
      });
      setMessage("Notification policy updated.");
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Save failed."); }
    finally { setBusy(false); }
  }
  async function retry(id: string) {
    setBusy(true); setError("");
    try {
      await apiRequest(root + "/delivery-history/" + encodeURIComponent(id) + "/retry",
        { method: "POST", cacheTtlMs: 0 });
      setMessage("Dispatch requeued for the scheduled worker.");
      await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Retry failed."); }
    finally { setBusy(false); }
  }
  return (
    <section className="qms-provider-register" aria-label="External provider notification controls">
      <div className="qms-provider-section-heading">
        <div><span className="qms-provider-eyebrow">Provider lifecycle automation</span>
          <h3><BellRing size={18} /> Renewals, reminders & escalations</h3>
          <p>Tenant-defined thresholds, departmental recipients, and delivery history.</p></div>
        <button type="button" className="qms-provider-button is-secondary"
          aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "Close" : "Notification settings"}</button>
      </div>
      {open && <div className="qms-provider-detail-section">
        {error && <p role="alert">{error}</p>}
        {message && <p role="status">{message}</p>}
        {!policy ? <button onClick={() => void load()}>Reload policy</button> : <>
          <p>Policy revision {policy.revision}. Notice periods are tenant rules, not statutory deadlines.</p>
          <div className="qms-provider-detail-grid">
            <label>Lead days, descending<input aria-label="Expiry lead days" value={lead}
              onChange={(e) => setLead(e.target.value)} /></label>
            <label>Escalation days, ascending<input aria-label="Overdue escalation days" value={escalation}
              onChange={(e) => setEscalation(e.target.value)} /></label>
            <fieldset><legend>Recipients</legend>{departmentRoles[department].map((role) =>
              <label key={role} style={{ display: "block" }}><input type="checkbox"
                checked={roles.includes(role)} onChange={(e) => setRoles(e.target.checked ?
                  [...roles, role] : roles.filter((r) => r !== role))} />
                {role.replaceAll("_", " ")}</label>)}</fieldset>
            <fieldset><legend>Channels</legend>
              <label><input type="checkbox" checked={inApp} onChange={(e) => setInApp(e.target.checked)} /> In-app</label>
              <label><input type="checkbox" checked={email} onChange={(e) => setEmail(e.target.checked)} /> Email</label>
            </fieldset>
          </div>
          {policy.can_manage_delivery_window && <fieldset><legend>Tenant delivery windows</legend>
            <label><input type="checkbox" checked={digest} onChange={(e) => setDigest(e.target.checked)} /> Digest window</label>
            <label>Local hour <input type="number" min={0} max={23} value={digestHour}
              onChange={(e) => setDigestHour(Number(e.target.value))} /></label>
            <label><input type="checkbox" checked={quiet} onChange={(e) => setQuiet(e.target.checked)} /> Quiet hours</label>
            <label>From <input type="time" value={start} onChange={(e) => setStart(e.target.value)} /></label>
            <label>To <input type="time" value={end} onChange={(e) => setEnd(e.target.value)} /></label>
          </fieldset>}
          <details><summary>Department event templates</summary>
            {Object.entries(policy.catalog).filter((entry) => entry[1] === department).map(([key]) =>
              <label key={key} style={{ display: "block" }}>{key}
                <input maxLength={200} value={templates[key] || ""}
                  placeholder="Default generic label" onChange={(e) => setTemplates((old) =>
                    ({ ...old, [key]: e.target.value }))} /></label>)}
          </details>
          <button className="qms-provider-button" disabled={busy} onClick={() => void save()}>
            <Save size={16} /> Save notification policy</button>
          <div className="qms-provider-section-heading"><h3>Dispatch history</h3>
            <button className="qms-provider-button is-secondary" disabled={busy}
              onClick={() => void load()}><RefreshCw size={16} /> Refresh</button></div>
          <p>In-app dispatch is separate from Resend acceptance, final delivery, spam placement and read receipts.</p>
          <div className="qms-provider-table-wrap"><table className="qms-provider-table">
            <thead><tr><th>Event</th><th>Scheduled</th><th>State</th><th>Email</th><th>Retry</th></tr></thead>
            <tbody>{rows.map((row) => <tr key={row.id}>
              <td>{row.event_key}</td><td>{new Date(row.due_at).toLocaleString()}</td>
              <td>{row.status}{row.acknowledged_at ? " · acknowledged" : ""}{row.last_error ? " · " + row.last_error : ""}</td>
              <td>{row.email_log_id ? (row.email_delivery_status || row.email_processing_status || "Pending provider evidence") : "Not attempted"}</td>
              <td>{["FAILED", "RETRY"].includes(row.status) ?
                <button disabled={busy} onClick={() => void retry(row.id)}>Retry</button> : "—"}</td>
            </tr>)}
            {!rows.length && <tr><td colSpan={5}>No alerts in this department.</td></tr>}</tbody>
          </table></div>
        </>}
      </div>}
    </section>
  );
}
