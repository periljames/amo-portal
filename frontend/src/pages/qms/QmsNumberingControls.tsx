import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { CalendarClock, Hash, RotateCcw, RefreshCw } from "lucide-react";
import { apiRequest, qmsPath } from "../../services/apiClient";
import { defaults, validNumbering, formatReferenceDate, referenceDateFormats } from "./numberingRules";

type Rules = Record<string, string | number>;
type Series = { id: string; prefix: string; scope: string; year: number; last_value: number; next_value: number };
type Scope = { code: string; name: string };
type Snapshot = { rules: Rules; series: Series[]; server_date: string; server_period: string; counter_year: number; audit_scopes: Scope[]; car_unit_code: string };
export default function QmsNumberingControls({ amoCode, value, onChange, disabled, revision }: { amoCode: string; value: unknown; onChange: (rules: Rules) => void; disabled: boolean; revision?: string }) {
  const queryClient = useQueryClient();
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState("");
  const errorRef = useRef<HTMLDivElement>(null);
  const dateRef = useRef("");
  useEffect(() => { if (error) errorRef.current?.scrollIntoView({ block: "nearest" }); }, [error]);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [selected, setSelected] = useState("");
  const [prefix, setPrefix] = useState("");
  const [scope, setScope] = useState("");
  const [last, setLast] = useState(0);
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const effective = snapshot?.rules || defaults;
  const rules = { ...effective, ...(value as Rules || {}) };
  const serverDate = snapshot?.server_date || "";
  const year = snapshot?.counter_year;
  const family = prefix || String(effective.audit_prefix);
  const auditScopes = snapshot?.audit_scopes || [];
  const unit = family === effective.audit_prefix ? (scope || auditScopes.find(s => s.code === "MO")?.code || auditScopes[0]?.code || "") : (snapshot?.car_unit_code || "");
  const current = snapshot?.series.find(item => item.prefix === family && item.scope === unit && item.year === year);
  const selectedSeries = snapshot?.series.find(item => item.id === selected);
  const families = [String(effective.audit_prefix), String(effective.car_prefix), String(effective.reliability_car_prefix)];
  const historical = Boolean(selectedSeries && (selectedSeries.year !== year || !families.includes(selectedSeries.prefix) || (family === effective.audit_prefix && !auditScopes.some(s => s.code === unit))));
  const formatsChanged = Object.keys(defaults).some(key => rules[key] !== effective[key]);
  const datePart = formatReferenceDate(serverDate, String(rules.date_format));
  const sample = `${rules.audit_prefix}/MO/${datePart}/${String(1).padStart(Number(rules.sequence_digits), "0")}`;
  const load = useCallback(async (quiet = false) => {
    if (!quiet) setError("");
    try {
      const data = await apiRequest<Snapshot>(qmsPath(amoCode, "/settings/numbering"), { cacheTtlMs: 0 });
      if (dateRef.current && dateRef.current !== data.server_date) setConfirmed(false);
      dateRef.current = data.server_date;
      setSnapshot(previous => quiet && previous ? { ...previous, server_date: data.server_date, server_period: data.server_period, counter_year: data.counter_year } : data);
      if (!quiet) setLoaded(true);
    } catch (cause) { if (!quiet) { setLoaded(false); setError(cause instanceof Error ? cause.message : "Could not load reference series."); } }
  }, [amoCode]);
  useEffect(() => { void load(); }, [load, revision]);
  useEffect(() => {
    const refreshClock = () => { if (!document.hidden) void load(true); };
    const timer = window.setInterval(refreshClock, 60000);
    window.addEventListener("focus", refreshClock);
    return () => { clearInterval(timer); window.removeEventListener("focus", refreshClock); };
  }, [load]);
  const resetValid = loaded && !historical && !formatsChanged && Boolean(snapshot?.server_period) && families.includes(family) && Boolean(unit) && Number.isInteger(last) && last >= 0 && last <= 999999999 && reason.trim().length >= 10 && reason.trim().length <= 500 && confirmed;
  async function reset() {
    if (disabled || busy || !resetValid || !snapshot) return;
    setBusy(true); setError(""); setStatus("");
    try {
      await apiRequest(qmsPath(amoCode, "/settings/numbering/reset"), { method: "POST", headers: { "Content-Type": "application/json", "X-AMO-Silent-Error": "1" }, body: JSON.stringify({ prefix: family, scope: unit, expected_period: snapshot.server_period, expected_date_format: effective.date_format, last_value: last, expected_last_value: current?.last_value ?? 0, reason: reason.trim(), confirmed }) });
      setStatus(`Series updated. The next number is ${last + 1}.`); setConfirmed(false); setReason(""); void queryClient.invalidateQueries({ queryKey: ["qms-audit-scopes", amoCode] }); await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Series change failed. Your entries are retained."); }
    finally { setBusy(false); }
  }
  return <>
    <section className="qms-settings__card"><h2><Hash size={19} /> Reference formats</h2><p>Applies to new records. Existing references stay unchanged.</p>
      <div className="qms-settings__control-grid">{[
        ["audit_prefix", "Audit Prefix", "Audit reference family."], ["car_prefix", "CAR Prefix", "Quality corrective action requests."], ["reliability_car_prefix", "Reliability CAR Prefix", "Reliability corrective action requests."], ["finding_prefix", "Finding Prefix", "Marker after the parent audit reference."],
      ].map(([key, label, description]) => { const invalid = !/^[A-Z][A-Z0-9]{0,15}$/.test(String(rules[key])) || (key === "audit_prefix" && String(rules[key]).length < 2); return <label className="qms-settings__field" key={key}><span>{label}</span><input aria-label={label} value={String(rules[key])} maxLength={16} spellCheck={false} autoComplete="off" disabled={disabled || !loaded} aria-invalid={invalid} onChange={event => onChange({ ...rules, [key]: event.target.value.toUpperCase() })} /><small>{invalid ? `Use ${key === "audit_prefix" ? "2" : "1"}–16 letters or numbers; start with a letter.` : description}</small></label>; })}
      <label className="qms-settings__field"><span>Sequence digits</span><select aria-label="Sequence digits" value={rules.sequence_digits} disabled={disabled || !loaded} onChange={event => onChange({ ...rules, sequence_digits: Number(event.target.value) })}>{[3, 4, 5, 6].map(n => <option key={n} value={n}>{n} digits · {String(1).padStart(n, "0")}</option>)}</select><small>Minimum width; numbers continue growing.</small></label>
      <label className="qms-settings__field"><span>Reference date format</span><select aria-label="Reference date format" value={rules.date_format} disabled={disabled || !loaded} onChange={event => onChange({ ...rules, date_format: event.target.value })}>{referenceDateFormats.map(format => <option key={format} value={format}>{format} · {formatReferenceDate(serverDate, format)}{format === "YYYY-MM" ? " · ISO" : ""}</option>)}</select><small>Automatic server date. Counter continues within the calendar year.</small></label></div>
      <div className="qms-settings__clock"><CalendarClock size={16} /><span>Server date (UTC)</span><output aria-label="Server reference date">{serverDate || "Loading…"}</output></div>
      {!validNumbering(rules) && <p role="status" className="qms-settings__error">Check the reference formats and use distinct audit and CAR prefixes.</p>}
      <div className="qms-settings__preview"><span>Format examples · MO scope</span><code>{sample}</code><code>{rules.car_prefix}/MO/{datePart}/{String(1).padStart(Number(rules.sequence_digits), "0")}</code><code>{sample}-{rules.finding_prefix}-{String(1).padStart(Number(rules.sequence_digits), "0")}</code></div>
    </section>
    <section className="qms-settings__card"><div className="qms-settings__section-heading"><h2><RotateCcw size={19} /> Series & counters</h2><button type="button" onClick={() => void load()} disabled={busy}><RefreshCw size={15} /> Refresh series</button></div><p>Dates and CAR unit codes come from the server. Choose an approved audit scope when needed.</p>
      {error && <div ref={errorRef} role="alert" data-portal-error-feedback className="qms-settings__error">{error}</div>}{status && <p role="status" className="qms-settings__success">{status}</p>}
      <label className="qms-settings__field"><span>Reference series</span><select aria-label="Reference series" value={selected} onChange={event => { setSelected(event.target.value); const item = snapshot?.series.find(c => c.id === event.target.value); setPrefix(item?.prefix || ""); setScope(item?.scope || ""); setLast(item?.last_value || 0); setConfirmed(false); }}><option value="">Current period / configured formats</option>{snapshot?.series.map(item => <option key={item.id} value={item.id}>{item.prefix} / {item.scope} · {Number(snapshot.server_period.slice(0,2)) * 100 + item.year} · next {item.next_value}</option>)}</select></label>
      {(selectedSeries || current) && <p className="qms-settings__counter">Last issued <strong>{(selectedSeries || current)?.last_value}</strong><span>Next <strong>{(selectedSeries || current)?.next_value}</strong></span></p>}
      {historical && <p>Historical or inactive series · view only. New series use the current server year.</p>}
      {formatsChanged && <p role="status">Save reference formats before adjusting a series.</p>}
      {!disabled && !historical && <><button type="button" aria-expanded={resetOpen} disabled={formatsChanged || !loaded} onClick={() => setResetOpen(!resetOpen)}>Adjust or initialise a series</button>{resetOpen && <fieldset disabled={busy || formatsChanged || !loaded} className="qms-settings__reset"><p>Enter zero to start at 001. Issued numbers cannot be reused; save a new prefix for a fresh series.</p><div className="qms-settings__control-grid">
        <label className="qms-settings__field"><span>Series prefix</span><select aria-label="Series prefix" value={family} onChange={event => { setSelected(""); setPrefix(event.target.value); setScope(""); setLast(0); setConfirmed(false); }}>{families.map((code,index) => <option key={code} value={code}>{["Audit", "Quality CAR", "Reliability CAR"][index]} · {code}</option>)}</select></label>
        {family === effective.audit_prefix ? <label className="qms-settings__field"><span>Audit scope</span><select aria-label="Audit scope" value={unit} onChange={event => { setSelected(""); setScope(event.target.value); setLast(0); setConfirmed(false); }}>{auditScopes.map(item => <option key={item.code} value={item.code}>{item.code} · {item.name}</option>)}</select></label> : <div className="qms-settings__field"><span>CAR unit</span><output aria-label="CAR unit">{unit}</output><small>Assigned from this tenant's organisation.</small></div>}
        <div className="qms-settings__field"><span>Reference period</span><output aria-label="Reference period">{snapshot?.server_period} · server UTC</output><small>Automatic; historical periods cannot be reset.</small></div>
        <label className="qms-settings__field"><span>Last issued number</span><input aria-label="Last issued number" aria-invalid={!Number.isInteger(last) || last < 0 || last > 999999999} type="number" min={0} max={999999999} step={1} value={Number.isNaN(last) ? "" : last} onChange={event => { setLast(event.target.valueAsNumber); setConfirmed(false); }} /><small>Next number: {Number.isInteger(last) && last >= 0 && last <= 999999999 ? last + 1 : "Enter a whole number from 0 to 999999999"}</small></label>
      </div><label className="qms-settings__field"><span>Reason for series change</span><input value={reason} minLength={10} maxLength={500} onChange={event => setReason(event.target.value)} /><small>10–500 characters. Recorded in tenant activity history.</small></label>
      <label className="qms-settings__toggle"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} /><span>I confirm {family}/{unit}/{formatReferenceDate(serverDate, String(effective.date_format))} will issue {last + 1} next.</span></label><button type="button" disabled={!resetValid || busy} onClick={() => void reset()}>{busy ? "Updating series…" : "Apply series change"}</button></fieldset>}</>}
    </section>
  </>;
}
