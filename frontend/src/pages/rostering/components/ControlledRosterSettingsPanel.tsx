import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileCheck2, Save } from "lucide-react";

import {
  getControlledRosterSettings,
  updateControlledRosterSettings,
  type ControlledRosterSettings,
} from "../../../services/rosteringControl";
import { errorMessage } from "../rosterUi";
import { useWorkforcePermissions } from "../hooks/useWorkforcePermissions";
import { RosterLoading } from "./RosterShell";
import { RosterShiftOperationalPolicyPanel } from "./RosterShiftOperationalPolicyPanel";

const SETTINGS_KEY = ["rostering", "settings", "controlled-document"] as const;

export function ControlledRosterSettingsPanel() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ControlledRosterSettings | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const settingsQuery = useQuery({ queryKey: SETTINGS_KEY, queryFn: getControlledRosterSettings, staleTime: 15 * 60_000 });
  const permissionsQuery = useWorkforcePermissions();
  const canManage = (permissionsQuery.data?.permissions || []).includes("roster.manage_shift_templates");

  useEffect(() => {
    if (settingsQuery.data) setForm(settingsQuery.data);
  }, [settingsQuery.data]);

  if (settingsQuery.isPending && !settingsQuery.data) return <RosterLoading label="Loading controlled roster settings…" />;
  if (!form) return <div className="wr-inline-error" role="alert">{errorMessage(settingsQuery.error || new Error("Controlled roster settings are unavailable"))}</div>;

  const set = <K extends keyof ControlledRosterSettings>(key: K, value: ControlledRosterSettings[K]) => {
    setForm((current) => current ? { ...current, [key]: value } : current);
  };

  const save = async () => {
    setBusy(true);
    setActionError(null);
    try {
      const updated = await updateControlledRosterSettings(form);
      setForm(updated);
      await queryClient.invalidateQueries({ queryKey: SETTINGS_KEY });
    } catch (cause) {
      setActionError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <section className="wr-panel">
        <div className="wr-section-heading">
          <div>
            <span className="wr-eyebrow">Controlled output</span>
            <h2><FileCheck2 size={19} /> Printable roster document</h2>
            <p>These tenant-owned fields are captured into the published roster snapshot. Later edits cannot change an already published roster document.</p>
          </div>
          <span className="wr-header-badge">{form.page_size} landscape</span>
        </div>
        {actionError ? <div className="wr-inline-error" role="alert">{actionError}</div> : null}
        <div className="wr-form-grid">
          <label>Form number<input value={form.form_number} disabled={!canManage} onChange={(event) => set("form_number", event.target.value)} placeholder="e.g. SL/MCM/27" /></label>
          <label>Revision<input value={form.revision_label || ""} disabled={!canManage} onChange={(event) => set("revision_label", event.target.value || null)} placeholder="e.g. Rev 0" /></label>
          <label>Revision date<input type="date" value={form.revision_date || ""} disabled={!canManage} onChange={(event) => set("revision_date", event.target.value || null)} /></label>
          <label>Page size<select value={form.page_size} disabled={!canManage} onChange={(event) => set("page_size", event.target.value as "A3" | "A4")}><option value="A3">A3</option><option value="A4">A4</option></select></label>
          <label>Prepared by label<input value={form.prepared_by_label} disabled={!canManage} onChange={(event) => set("prepared_by_label", event.target.value)} /></label>
          <label>Approved by label<input value={form.approved_by_label} disabled={!canManage} onChange={(event) => set("approved_by_label", event.target.value)} /></label>
          <label style={{ gridColumn: "1 / -1" }}>Roster note<textarea rows={3} value={form.footer_note || ""} disabled={!canManage} onChange={(event) => set("footer_note", event.target.value || null)} placeholder="Controlled roster note / break statement" /></label>
        </div>
        <div className="wr-inline-warning" role="status">Draft exports carry a DRAFT — NOT CONTROLLED watermark. Published exports use the immutable version snapshot, including the exact roster code legend and aircraft allocations captured at publication.</div>
        {canManage ? <div className="wr-actions wr-actions--end"><button type="button" className="wr-button wr-button--primary" disabled={busy || !form.form_number.trim()} onClick={() => void save()}><Save size={14} /> Save controlled-document settings</button></div> : null}
      </section>
      <RosterShiftOperationalPolicyPanel />
    </>
  );
}
