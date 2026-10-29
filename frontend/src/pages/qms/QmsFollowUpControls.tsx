import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { LockKeyhole, Plus, X } from "lucide-react";
import { apiRequest, qmsPath } from "../../services/apiClient";
import { SettingsFeedback, SettingsSaveButton } from "./QmsSettingsFeedback";
import { settingsError } from "./settingsError";

type FollowUp = { report_due_days: number; report_reminder_days: number[]; car_reminder_percentages: number[]; final_reminder_days_before_due: number; auto_escalation_enabled: boolean };
export default function QmsFollowUpControls({ amoCode, disabled }: { amoCode: string; disabled: boolean }) {
  const queryClient = useQueryClient();
  const [saved, setSaved] = useState<FollowUp | null>(null);
  const [draft, setDraft] = useState<FollowUp | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const load = useCallback(async () => {
    try { const data = await apiRequest<{ settings: FollowUp }>(qmsPath(amoCode, "/settings/follow-up"), { cacheTtlMs: 0, headers: { "X-AMO-Silent-Error": "1" } }); setSaved(data.settings); setDraft(data.settings); setError(""); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not load follow-up settings."); }
  }, [amoCode]);
  useEffect(() => { void load(); }, [load]);
  const integer = (n: number, min: number, max: number) => Number.isInteger(n) && n >= min && n <= max;
  const valid = draft && integer(draft.report_due_days, 1, 60) && integer(draft.final_reminder_days_before_due, 0, 30) && draft.report_reminder_days.length > 0 && new Set(draft.report_reminder_days).size === draft.report_reminder_days.length && draft.report_reminder_days.every(n => integer(n, 0, 60)) && draft.car_reminder_percentages.length > 0 && new Set(draft.car_reminder_percentages).size === draft.car_reminder_percentages.length && draft.car_reminder_percentages.every(n => integer(n, 1, 99));
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved);
  async function save() {
    if (!draft || !valid || !dirty || busy || disabled) return;
    setBusy(true); setError(""); setNotice("");
    try { const changes = { report_due_days: draft.report_due_days, report_reminder_days: draft.report_reminder_days, car_reminder_percentages: draft.car_reminder_percentages, final_reminder_days_before_due: draft.final_reminder_days_before_due }; const result = await apiRequest<{ settings: FollowUp }>(qmsPath(amoCode, "/settings/follow-up"), { method: "PATCH", headers: { "Content-Type": "application/json", "X-AMO-Silent-Error": "1" }, body: JSON.stringify({ ...changes, expected_settings: saved }) }); setSaved(result.settings); setDraft(result.settings); setNotice("Follow-up settings saved."); void queryClient.invalidateQueries({ queryKey: ["qms-workflow-settings", amoCode] }); }
    catch (cause) { setError(settingsError(cause, "Could not save. Your entries are retained.")); }
    finally { setBusy(false); }
  }
  return <section className="qms-settings__card" onChangeCapture={() => { setNotice(""); setError(""); }}><h2>Deadlines & follow-up</h2><p>Tenant defaults for report delivery and CAR reminders.</p>
    {!draft && <SettingsFeedback message={error} error><button type="button" onClick={() => void load()}>Retry loading follow-up</button></SettingsFeedback>}
    {!draft ? (!error && <p>Loading follow-up controls…</p>) : <><div className="qms-settings__control-grid">{([
      ["report_due_days", "Report due after fieldwork (days)", 1, 60], ["final_reminder_days_before_due", "Final reminder before due (days)", 0, 30],
    ] as const).map(([key, label, min, max]) => <label className="qms-settings__field" key={key}><span>{label}</span><input aria-label={label} type="number" required min={min} max={max} step={1} disabled={disabled || busy} value={Number.isNaN(draft[key]) ? "" : draft[key]} aria-invalid={!integer(draft[key], min, max)} onChange={event => setDraft({ ...draft, [key]: event.target.valueAsNumber })} /><small>{integer(draft[key], min, max) ? `Whole days, ${min}–${max}.` : `Enter a whole number from ${min} to ${max}.`}</small></label>)}</div>
    {([ ["report_reminder_days", "Report reminder days before due", 0, 60], ["car_reminder_percentages", "CAR reminder milestones (%)", 1, 99] ] as const).map(([key, label, min, max]) => <fieldset className="qms-settings__reminders" key={key}><legend>{label}</legend><div>{draft[key].map((amount, index) => <label key={index}><span className="sr-only">{label} {index + 1}</span><input type="number" min={min} max={max} step={1} required disabled={disabled || busy} aria-invalid={!integer(amount, min, max)} value={Number.isNaN(amount) ? "" : amount} onChange={event => setDraft({ ...draft, [key]: draft[key].map((n, i) => i === index ? event.target.valueAsNumber : n) })} /><button type="button" aria-label={`Remove ${label.toLowerCase()} ${index + 1}`} disabled={disabled || busy || draft[key].length <= 1} onClick={() => setDraft({ ...draft, [key]: draft[key].filter((_, i) => i !== index) })}><X size={15} /></button></label>)}<button type="button" disabled={disabled || busy || draft[key].length >= 10} onClick={() => setDraft({ ...draft, [key]: [...draft[key], min] })}><Plus size={15} /> Add reminder</button></div><small>One value per control · {min}–{max} · up to 10 reminders.</small></fieldset>)}
    <p className="qms-settings__locked"><LockKeyhole size={15} /> Automatic escalation: {draft.auto_escalation_enabled ? "enabled" : "disabled by platform administration"}. Governed control.</p>
    {!valid && <p role="status" className="qms-settings__error">Use valid, distinct reminder values before saving.</p>}
    {!disabled && <footer className="qms-settings__save"><SettingsFeedback message={error || notice} error={Boolean(error)} onDismiss={() => { setError(""); setNotice(""); }}>{error && <button type="button" onClick={() => { setNotice(""); void load(); }}>Load current values (replace draft)</button>}</SettingsFeedback><span>{dirty ? "Unsaved follow-up changes" : "Follow-up up to date"}</span><button type="button" disabled={!dirty || busy} onClick={() => setDraft(saved)}>Discard follow-up</button><SettingsSaveButton type="button" busy={busy} saved={Boolean(notice) && !dirty} disabled={!dirty || !valid || busy} onClick={() => void save()}>{busy ? "Saving..." : "Save follow-up"}</SettingsSaveButton></footer>}</>}
  </section>;
}
