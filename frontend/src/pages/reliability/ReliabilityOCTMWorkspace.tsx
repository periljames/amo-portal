import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { apiRequest } from "../../services/apiClient";
import "../../styles/reliability-v2.css";
import "./ReliabilityOCTMWorkspace.css";

type EventType = "TOP_UP" | "CHECK_ZERO" | "MISSING" | "NO_OPERATION" | "OIL_CHANGE" | "MAINTENANCE_REFILL" | "LEAK_SERVICING";
type EntryPayload = {
  aircraft_serial_number: string;
  engine_position: string;
  engine_serial_number: string;
  installation_ref: string;
  event_date: string;
  event_sequence: number;
  techsheet_ref: string;
  sector_ref: string;
  source_type: "PAPER_TECHSHEET" | "REVIEWED_OCR" | "AVI_PRO_EXPORT" | "AVI_PRO_API";
  external_record_id: string;
  source_evidence_ref: string;
  maintenance_complete: "YES" | "NO" | "UNKNOWN";
  event_type: EventType;
  oil_quantity: number | null;
  oil_unit: "QT" | "L" | "US_GAL" | null;
  oil_specification: string;
  reference_method: string;
  reference_level: string;
  engine_counter_hours: number | null;
  flight_hours: number | null;
  remarks: string;
};
type Entry = EntryPayload & { id: string; review_status: string; created_at: string; review_note: string | null };
type Interval = {
  engine_serial_number: string;
  installation_ref: string;
  aircraft_serial_number: string;
  window_start: string;
  window_end: string;
  oil_added_quarts: number;
  flight_hours: number;
  rate_qt_per_fh: number | null;
  manufacturer_limit_qt_per_fh: number | null;
  manufacturer_limit_exceeded: boolean | null;
  trend_increase_percent: number | null;
  trend_alert: boolean | null;
  status: string;
};
type Profile = { id: string; engine_serial_number: string; installation_ref: string; engine_model: string;
  version: number; status: string; limit_qt_per_fh: number; technical_data_ref: string; technical_data_revision: string };
type Monitoring = { intervals: Interval[]; verified_source_count: number; truncated: boolean };
type Caps = { capabilities: string[] };
type View = "entry" | "review" | "register" | "trends" | "profiles";
type AircraftOption = { serial_number: string; registration: string; is_active: boolean };
type EngineHint = { engine_position: string; engine_serial_number: string; installation_ref: string;
  last_observed: string; basis: "PREVIOUS_OCTM_ENTRY" };
type Readiness = { errors: string[]; warnings: string[]; ready_for_verification: boolean };

const blankEntry = (): EntryPayload => ({
  aircraft_serial_number: "", engine_position: "", engine_serial_number: "", installation_ref: "",
  event_date: new Date(Date.now() - new Date().getTimezoneOffset() * 60_000).toISOString().slice(0, 10), event_sequence: 1, techsheet_ref: "",
  sector_ref: "", source_type: "PAPER_TECHSHEET", external_record_id: "", source_evidence_ref: "",
  maintenance_complete: "UNKNOWN", event_type: "TOP_UP", oil_quantity: null, oil_unit: "QT",
  oil_specification: "", reference_method: "", reference_level: "", engine_counter_hours: null,
  flight_hours: null, remarks: "",
});
const eventTypes: EventType[] = ["TOP_UP", "CHECK_ZERO", "MISSING", "NO_OPERATION", "OIL_CHANGE", "MAINTENANCE_REFILL", "LEAK_SERVICING"];
const safeError = (error: unknown): string => {
  const body = error && typeof error === "object" && "body" in error ? (error as { body: unknown }).body : null;
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "validation_issues" in detail) {
      return (detail as { validation_issues: string[] }).validation_issues.join("; ");
    }
  }
  return error instanceof Error ? error.message : String(error);
};
const numeric = (value: string): number | null => value.trim() === "" ? null : Number(value);
const trim = (text: string): string | null => text.trim() ? text.trim() : null;

export default function ReliabilityOCTMWorkspace(): React.ReactElement {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode?: string }>();
  const home = "/maintenance/" + encodeURIComponent(amoCode) + "/reliability";
  const [view, setView] = useState<View>("entry");
  const [form, setForm] = useState<EntryPayload>(blankEntry);
  const [correcting, setCorrecting] = useState<string | null>(null);
  const [correctionReason, setCorrectionReason] = useState("");
  const [entries, setEntries] = useState<Entry[]>([]);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [monitoring, setMonitoring] = useState<Monitoring>({ intervals: [], verified_source_count: 0, truncated: false });
  const [caps, setCaps] = useState<string[]>([]);
  const [filter, setFilter] = useState("");
  const [aircraftOptions, setAircraftOptions] = useState<AircraftOption[]>([]);
  const [engineHints, setEngineHints] = useState<EngineHint[]>([]);
  const [continueEntry, setContinueEntry] = useState(true);
  const [reviewTarget, setReviewTarget] = useState<Entry | null>(null);
  const [reviewDecision, setReviewDecision] = useState<"VERIFIED" | "RETURNED">("VERIFIED");
  const [reviewNote, setReviewNote] = useState("");
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [selectedEngine, setSelectedEngine] = useState("");
  const [newProfile, setNewProfile] = useState({ engine_serial_number: "", installation_ref: "", engine_model: "",
    limit_qt_per_fh: "", alert_increase_percent: "", technical_data_ref: "", technical_data_revision: "", effective_from: "" });
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    const [items, rates, p, permissions, aircraft] = await Promise.all([
      apiRequest<Entry[]>("/reliability/octm/entries"),
      apiRequest<Monitoring>("/reliability/octm/monitoring"),
      apiRequest<Profile[]>("/reliability/octm/profiles"),
      apiRequest<Caps>("/reliability/capabilities"),
      apiRequest<AircraftOption[]>("/reliability/octm/aircraft"),
    ]);
    setEntries(items);
    setMonitoring(rates);
    setProfiles(p);
    setCaps(permissions.capabilities);
    setAircraftOptions(aircraft);
  }, []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    void refresh().catch((cause) => { if (active) setError(safeError(cause)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [refresh]);

  useEffect(() => {
    if (!form.aircraft_serial_number || !form.event_date) { setEngineHints([]); return; }
    let active = true;
    void apiRequest<EngineHint[]>("/reliability/octm/engine-hints?aircraft=" +
      encodeURIComponent(form.aircraft_serial_number) + "&event_date=" + encodeURIComponent(form.event_date))
      .then((items) => { if (active) setEngineHints(items); })
      .catch(() => { if (active) setEngineHints([]); });
    return () => { active = false; };
  }, [form.aircraft_serial_number, form.event_date]);

  const has = (capability: string) => caps.includes(capability);
  const set = <K extends keyof EntryPayload>(name: K, value: EntryPayload[K]) =>
    setForm((prior) => ({ ...prior, [name]: value }));

  const run = async (operation: () => Promise<unknown>, onSuccess?: () => void) => {
    setBusy(true); setError(""); setMessage("");
    try {
      await operation();
      await refresh();
      onSuccess?.();
      setMessage("Saved successfully.");
    } catch (cause) {
      setError(safeError(cause));
    } finally { setBusy(false); }
  };

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    const payload = {
      ...form,
      sector_ref: trim(form.sector_ref), external_record_id: trim(form.external_record_id),
      source_evidence_ref: trim(form.source_evidence_ref), oil_specification: trim(form.oil_specification),
      reference_method: trim(form.reference_method), reference_level: trim(form.reference_level),
      remarks: trim(form.remarks),
      oil_quantity: ["MISSING", "NO_OPERATION", "CHECK_ZERO"].includes(form.event_type) ? null : form.oil_quantity,
      oil_unit: ["MISSING", "NO_OPERATION", "CHECK_ZERO"].includes(form.event_type) ? null : form.oil_unit,
    };
    await run(
      () => correcting
        ? apiRequest("/reliability/octm/entries/" + encodeURIComponent(correcting) + "/correct", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ replacement: payload, reason: correctionReason }),
          })
        : apiRequest("/reliability/octm/entries", {
            method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
          }),
      () => {
        setForm((previous) => correcting || !continueEntry ? blankEntry() : {
          ...previous, event_sequence: previous.event_sequence + 1, sector_ref: "",
          oil_quantity: null, oil_unit: "QT", flight_hours: null, engine_counter_hours: null,
          remarks: "", maintenance_complete: "UNKNOWN", event_type: "TOP_UP",
        });
        setCorrecting(null); setCorrectionReason("");
      }
    );
  };

  const prepareReview = async (item: Entry, decision: "VERIFIED" | "RETURNED") => {
    setReviewTarget(item); setReviewDecision(decision); setReviewNote(""); setReadiness(null);
    setReviewLoading(true); setError("");
    try {
      const checked = await apiRequest<Readiness>("/reliability/octm/entries/" +
        encodeURIComponent(item.id) + "/readiness");
      setReadiness(checked);
    } catch (cause) { setError(safeError(cause)); } finally { setReviewLoading(false); }
  };

  const submitReview = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!reviewTarget) return;
    if (reviewDecision === "VERIFIED" && !readiness?.ready_for_verification) return;
    await run(() => apiRequest("/reliability/octm/entries/" + encodeURIComponent(reviewTarget.id) + "/review", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision: reviewDecision, note: reviewNote.trim() }),
    }), () => { setReviewTarget(null); setReadiness(null); setReviewNote(""); });
  };

  const chooseCorrection = (item: Entry) => {
    const { id, review_status, created_at, review_note, ...values } = item;
    void review_status; void created_at; void review_note;
    setForm(values);
    setCorrecting(id);
    setView("entry");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const filtered = useMemo(() => entries.filter((entry) =>
    [entry.aircraft_serial_number, entry.engine_serial_number, entry.techsheet_ref, entry.installation_ref]
      .some((part) => part.toLowerCase().includes(filter.toLowerCase()))), [entries, filter]);
  const queue = filtered.filter((item) => item.review_status !== "VERIFIED");
  const formIssues = [
    ...(!form.aircraft_serial_number ? ["Select a registered aircraft"] : []),
    ...(!form.engine_position || !form.engine_serial_number || !form.installation_ref
      ? ["Confirm the physical engine serial, position and installation reference"] : []),
    ...(!form.techsheet_ref || !form.source_evidence_ref
      ? ["Record the techsheet and source evidence reference"] : []),
    ...(form.maintenance_complete !== "YES" && form.event_type !== "NO_OPERATION"
      ? ["Maintenance completion is not confirmed"] : []),
    ...(form.event_type === "TOP_UP" && (!form.oil_quantity || !form.oil_specification)
      ? ["Record positive uplift and oil specification"] : []),
    ...(["TOP_UP", "CHECK_ZERO"].includes(form.event_type) &&
      (!form.reference_method || !form.reference_level || form.flight_hours === null)
      ? ["Reference level/method and flight-hour exposure are needed for verification"] : []),
    ...(form.flight_hours && !form.sector_ref ? ["Sector reference required when flight hours are entered"] : []),
  ];
  const engines = Array.from(new Set(monitoring.intervals.map((item) => item.engine_serial_number)));
  const trend = monitoring.intervals.filter((row) => row.status === "VALID" &&
    (!selectedEngine || row.engine_serial_number === selectedEngine)).slice().reverse();

  return <DepartmentLayout amoCode={amoCode} activeDepartment="reliability">
    <main className="reliability-v2 octm">
      <header className="reliability-v2__header">
        <div>
          <p className="reliability-v2__eyebrow">Reliability / Engine monitoring</p>
          <h1>Oil consumption monitoring</h1>
          <p>Technical-log source entries, independent verification, disjoint 40 ± 10 flight-hour trends, and controlled manufacturer limits.</p>
        </div>
        <Link className="btn btn-secondary" to={home}>Reliability overview</Link>
      </header>
      <nav className="octm__tabs" aria-label="Oil consumption workspaces">
        {([["entry", "Daily entry"], ["review", "Review queue"], ["register", "Source register"], ["trends", "Engine trends"], ["profiles", "Limit profiles"]] as const)
          .map(([key, label]) => <button key={key} type="button" className={view === key ? "octm__tab active" : "octm__tab"}
            aria-current={view === key ? "page" : undefined} onClick={() => setView(key)}>{label}
            {key === "review" ? " (" + queue.length + ")" : ""}</button>)}
      </nav>
      {error && <p className="octm__error" role="alert">{error}</p>}
      {message && <p className="octm__message" role="status">{message}</p>}
      {loading ? <p>Loading OCTM records…</p> : <>
        {view === "entry" && <section className="octm__panel">
          <h2>{correcting ? "Correct existing source record" : "Register technical-log oil entry"}</h2>
          <p>Every engine/sector event has a unique sequence. Enter zero only when oil was checked and none added. Missing data is not zero.</p>
          <form onSubmit={(event) => void save(event)} className="octm__form">
            <label>Registered aircraft
              <select required value={form.aircraft_serial_number} onChange={(event) => set("aircraft_serial_number", event.target.value)}>
                <option value="">Select aircraft…</option>
                {aircraftOptions.map((aircraft) => <option key={aircraft.serial_number} value={aircraft.serial_number}>
                  {aircraft.registration} · {aircraft.serial_number}{!aircraft.is_active ? " (historical)" : ""}
                </option>)}
              </select>
            </label>
            <label>Previously recorded engines (hints, not installation proof)
              <select value="" onChange={(event) => {
                const hint = engineHints[Number(event.target.value)];
                if (hint) setForm((previous) => ({ ...previous,
                  engine_position: hint.engine_position,
                  engine_serial_number: hint.engine_serial_number, installation_ref: hint.installation_ref }));
              }}>
                <option value="">Enter manually or select previous engine…</option>
                {engineHints.map((hint, index) => <option key={hint.engine_serial_number + hint.installation_ref + index} value={index}>
                  {hint.engine_position} · {hint.engine_serial_number} · {hint.installation_ref} (last seen {hint.last_observed})
                </option>)}
              </select>
            </label>
            <label>Engine position<input required value={form.engine_position} onChange={(event) => set("engine_position", event.target.value)} /></label>
            <label>Engine serial number<input required value={form.engine_serial_number} onChange={(event) => set("engine_serial_number", event.target.value)} /></label>
            <label>Installation reference<input required value={form.installation_ref} onChange={(event) => set("installation_ref", event.target.value)} /></label>
            <label>Event date<input type="date" required max={blankEntry().event_date} value={form.event_date} onChange={(event) => set("event_date", event.target.value)} /></label>
            <label>Techsheet / TechLog number<input required value={form.techsheet_ref} onChange={(event) => set("techsheet_ref", event.target.value)} /></label>
            <label>Sector / flight reference {form.flight_hours !== null && form.flight_hours > 0 ? "(required)" : ""}
              <input required={form.flight_hours !== null && form.flight_hours > 0}
                value={form.sector_ref} onChange={(event) => set("sector_ref", event.target.value)} />
            </label>
            <label>Event sequence<input type="number" min="1" required value={form.event_sequence} onChange={(event) => set("event_sequence", Number(event.target.value))} /></label>
            <label>Oil event<select value={form.event_type} onChange={(event) => set("event_type", event.target.value as EventType)}>
              {eventTypes.map((type) => <option key={type} value={type}>{type.replaceAll("_", " ")}</option>)}</select></label>
            <label>Source<select value={form.source_type} onChange={(event) => set("source_type", event.target.value as EntryPayload["source_type"])}>
              <option value="PAPER_TECHSHEET">Paper techsheet</option><option value="REVIEWED_OCR">Reviewed OCR draft</option></select></label>
            <label>Maintenance information complete?<select value={form.maintenance_complete}
              onChange={(event) => set("maintenance_complete", event.target.value as EntryPayload["maintenance_complete"])}>
              <option value="UNKNOWN">Unknown</option><option value="NO">No</option><option value="YES">Yes</option></select></label>
            <label>Oil added<input type="number" min="0" step="any" value={form.oil_quantity ?? ""}
              disabled={["CHECK_ZERO", "MISSING", "NO_OPERATION"].includes(form.event_type)}
              onChange={(event) => set("oil_quantity", numeric(event.target.value))} /></label>
            <label>Original volume unit<select value={form.oil_unit ?? "QT"} disabled={["CHECK_ZERO", "MISSING", "NO_OPERATION"].includes(form.event_type)}
              onChange={(event) => set("oil_unit", event.target.value as EntryPayload["oil_unit"])}>
              <option value="QT">US quart</option><option value="L">Litre</option><option value="US_GAL">US gallon</option></select></label>
            <label>Flight hours for this sector (not block hours)
              <input type="number" min="0" max="100" step="any" value={form.flight_hours ?? ""}
              onChange={(event) => set("flight_hours", numeric(event.target.value))} /></label>
            <label>Engine counter (hours)<input type="number" min="0" step="any" value={form.engine_counter_hours ?? ""}
              onChange={(event) => set("engine_counter_hours", numeric(event.target.value))} /></label>
            <label>Reference method<input value={form.reference_method} placeholder="Dipstick / sight glass"
              onChange={(event) => set("reference_method", event.target.value)} /></label>
            <label>Reference level<input value={form.reference_level} onChange={(event) => set("reference_level", event.target.value)} /></label>
            <label>Oil specification<input value={form.oil_specification} onChange={(event) => set("oil_specification", event.target.value)} /></label>
            <label>Source evidence reference (needed for verification)<input value={form.source_evidence_ref} placeholder="Scanned TechLog / DMS document reference"
              onChange={(event) => set("source_evidence_ref", event.target.value)} /></label>
            <label>External event ID<input value={form.external_record_id} onChange={(event) => set("external_record_id", event.target.value)} /></label>
            <label className="octm__full">Remarks<textarea rows={2} value={form.remarks} onChange={(event) => set("remarks", event.target.value)} /></label>
            {correcting && <label className="octm__full">Correction reason<input required minLength={5} value={correctionReason}
              onChange={(event) => setCorrectionReason(event.target.value)} /></label>}
            <div className="octm__full octm__readiness" aria-live="polite">
              <strong>Verification checklist</strong>
              {formIssues.length ? <ul>{formIssues.map((issue) => <li key={issue}>{issue}</li>)}</ul>
                : <p>All required source fields are present. A different authorized reviewer must still verify the source and installation.</p>}
              <p>Drafts can be incomplete. They never enter official OCTM calculations until independently verified.</p>
            </div>
            <div className="octm__full octm__actions">
              <button className="btn btn-primary" disabled={busy || !(correcting ? has("reliability.ingest") || has("reliability.data_quality.resolve") : has("reliability.ingest"))}>
                {correcting ? "Save correction for re-verification" : "Save as draft"}</button>
              {!correcting && <label className="octm__continue"><input type="checkbox" checked={continueEntry}
                onChange={(event) => setContinueEntry(event.target.checked)} />
                Keep aircraft, engine, techsheet and date for next event</label>}
              {correcting && <button type="button" className="btn btn-secondary" onClick={() => { setCorrecting(null); setCorrectionReason(""); setForm(blankEntry()); }}>Cancel correction</button>}
            </div>
          </form>
        </section>}
        {(view === "review" || view === "register") && <section className="octm__panel">
          <h2>{view === "review" ? "Unverified source records" : "Source register (most recent 200 entries)"}</h2>
          <p>Only verified observations enter official intervals. Crew closure does not substitute for maintenance completion.</p>
          <label>Find source or engine<input value={filter} onChange={(event) => setFilter(event.target.value)} /></label>
          <div className="octm__table-wrap"><table><thead><tr><th>Date / sequence</th><th>Aircraft</th><th>Engine / installation</th><th>Techsheet</th><th>Event</th><th>Qty</th><th>FH</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>{(view === "review" ? queue : filtered).map((item) => <tr key={item.id}>
              <td>{item.event_date} · {item.event_sequence}</td><td>{item.aircraft_serial_number}</td>
              <td>{item.engine_serial_number}<small>{item.installation_ref}</small></td><td>{item.techsheet_ref}</td>
              <td>{item.event_type}</td><td>{item.oil_quantity ?? "—"} {item.oil_unit ?? ""}</td>
              <td>{item.flight_hours ?? "—"}</td><td>{item.review_status}<small>{item.review_note}</small></td>
              <td><div className="octm__row-actions">
                <button disabled={!has("reliability.data_quality.resolve") || busy || item.review_status === "VERIFIED"}
                  onClick={() => void prepareReview(item, "VERIFIED")}>Inspect / verify</button>
                <button disabled={!has("reliability.data_quality.resolve") || busy || item.review_status === "VERIFIED"}
                  onClick={() => void prepareReview(item, "RETURNED")}>Return</button>
                <button disabled={busy || !(has("reliability.data_quality.resolve") ||
                  (item.review_status !== "VERIFIED" && has("reliability.ingest")))}
                  onClick={() => chooseCorrection(item)}>Correct</button>
              </div></td>
            </tr>)}</tbody></table></div>
          {!(view === "review" ? queue : filtered).length && <p>No source entries match the filter.</p>}
          {reviewTarget && <div className="octm__review" role="region" aria-label="Source verification">
            <h3>Review {reviewTarget.techsheet_ref} · {reviewTarget.engine_serial_number}</h3>
            <p>Source evidence: <strong>{reviewTarget.source_evidence_ref || "Not provided"}</strong>.
              Sector: {reviewTarget.sector_ref || "Not entered"}.
              Oil reference: {reviewTarget.reference_method || "Not entered"} / {reviewTarget.reference_level || "Not entered"}.</p>
            <p>Maintenance completed: {reviewTarget.maintenance_complete}.
              Oil: {reviewTarget.oil_quantity ?? "not recorded"} {reviewTarget.oil_unit || ""}.
              Flight hours: {reviewTarget.flight_hours ?? "not recorded"}.</p>
            {reviewLoading ? <p>Checking source and existing engine records…</p> : readiness && <>
              {readiness.errors.length > 0 && <div className="octm__error"><strong>Verification blocked:</strong>
                <ul>{readiness.errors.map((item) => <li key={item}>{item}</li>)}</ul></div>}
              {readiness.warnings.length > 0 && <div className="octm__readiness">
                <strong>Reviewer attention</strong><ul>{readiness.warnings.map((item) => <li key={item}>{item}</li>)}</ul></div>}
            </>}
            <form onSubmit={(event) => void submitReview(event)}>
              <label>Reason or source verification notes
                <textarea required minLength={3} maxLength={2000} rows={3} value={reviewNote}
                  onChange={(event) => setReviewNote(event.target.value)} /></label>
              <div className="octm__row-actions">
                <button type="submit" className="btn btn-primary" disabled={busy || reviewLoading ||
                  reviewNote.trim().length < 3 || (reviewDecision === "VERIFIED" && !readiness?.ready_for_verification)}>
                  {reviewDecision === "VERIFIED" ? "Confirm independent verification" : "Return for correction"}</button>
                <button type="button" className="btn btn-secondary" onClick={() => { setReviewTarget(null); setReadiness(null); }}>Cancel</button>
              </div>
            </form>
          </div>}
        </section>}
        {view === "trends" && <section className="octm__panel">
          <h2>Verified engine monitoring intervals</h2>
          <p>{monitoring.verified_source_count} verified source entries. Rates are recomputed from matched quantities and flight hours, not an average of spreadsheet rates.</p>
          {monitoring.truncated && <p role="alert">Results are truncated at 20,000 observations. Do not use for formal reporting until the complete period is retrieved.</p>}
          <label>Engine <select value={selectedEngine} onChange={(event) => setSelectedEngine(event.target.value)}>
            <option value="">All engines</option>{engines.map((e) => <option value={e} key={e}>{e}</option>)}</select></label>
          {!!trend.length && <div className="octm__chart"><ResponsiveContainer width="100%" height={300}>
            <LineChart data={trend}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="window_end" /><YAxis />
              <Tooltip /><Legend /><Line dataKey="rate_qt_per_fh" name="Oil qt / FH" stroke="#0f766e" />
              <Line dataKey="manufacturer_limit_qt_per_fh" name="Approved limit qt / FH" stroke="#b45309" strokeDasharray="5 5" connectNulls={false} /></LineChart>
          </ResponsiveContainer></div>}
          <div className="octm__table-wrap"><table><thead><tr><th>Engine</th><th>Installation</th><th>Interval</th><th>Oil qt</th><th>FH</th><th>Rate qt/FH</th><th>Approved limit</th><th>Result</th></tr></thead>
            <tbody>{monitoring.intervals.filter((item) => !selectedEngine || item.engine_serial_number === selectedEngine).map((item, index) => <tr key={item.engine_serial_number + item.window_end + index}>
              <td>{item.engine_serial_number}</td><td>{item.installation_ref}</td>
              <td>{item.window_start} – {item.window_end}</td><td>{item.oil_added_quarts}</td><td>{item.flight_hours}</td>
              <td>{item.rate_qt_per_fh ?? "Withheld"}</td><td>{item.manufacturer_limit_qt_per_fh ?? "Not approved"}</td>
              <td>{item.status === "OUT_OF_RANGE" ? "Interval outside 30–50 FH" : item.manufacturer_limit_exceeded ? "Manufacturer limit exceeded" : item.trend_alert ? "Trend alert" : item.manufacturer_limit_exceeded === null ? "Limit unverified" : "Within limit"}</td>
            </tr>)}</tbody></table></div>
          {!monitoring.intervals.length && <p>No completed verified 40 ± 10 FH intervals. Verify source observations first.</p>}
        </section>}
        {view === "profiles" && <section className="octm__panel">
          <h2>Controlled manufacturer limits</h2>
          <p>Enter values only from confirmed current technical data. A second authorized person must approve a profile before its limits are applied.</p>
          <form className="octm__form" onSubmit={(event) => { event.preventDefault(); void run(() => apiRequest("/reliability/octm/profiles", {
            method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
              ...newProfile, limit_qt_per_fh: Number(newProfile.limit_qt_per_fh),
              alert_increase_percent: trim(newProfile.alert_increase_percent) ? Number(newProfile.alert_increase_percent) : null,
            }),
          }), () => setNewProfile({ engine_serial_number: "", installation_ref: "", engine_model: "",
            limit_qt_per_fh: "", alert_increase_percent: "", technical_data_ref: "", technical_data_revision: "", effective_from: "" })); }}>
            {(Object.keys(newProfile) as Array<keyof typeof newProfile>).map((field) =>
              <label key={field}>{field.replaceAll("_", " ")}<input required={field !== "alert_increase_percent"}
                type={field === "effective_from" ? "date" : field === "limit_qt_per_fh" || field === "alert_increase_percent" ? "number" : "text"}
                step={field === "limit_qt_per_fh" || field === "alert_increase_percent" ? "any" : undefined}
                min={field === "limit_qt_per_fh" || field === "alert_increase_percent" ? "0.000001" : undefined}
                value={newProfile[field]} onChange={(event) => setNewProfile((prior) => ({ ...prior, [field]: event.target.value }))} /></label>)}
            <div className="octm__full"><button className="btn btn-primary" disabled={busy || !has("reliability.metric.manage")}>Save limit as draft</button></div>
          </form>
          <div className="octm__table-wrap"><table><thead><tr><th>Engine / installation</th><th>Profile</th><th>Limit (qt/FH)</th><th>Technical-data reference</th><th>Status</th><th>Action</th></tr></thead>
            <tbody>{profiles.map((profile) => <tr key={profile.id}>
              <td>{profile.engine_serial_number}<small>{profile.installation_ref}</small></td><td>{profile.engine_model} · v{profile.version}</td>
              <td>{profile.limit_qt_per_fh}</td><td>{profile.technical_data_ref} · {profile.technical_data_revision}</td><td>{profile.status}</td>
              <td><button disabled={busy || profile.status !== "DRAFT" || !has("reliability.programme.approve")} onClick={() =>
                void run(() => apiRequest("/reliability/octm/profiles/" + encodeURIComponent(profile.id) + "/approve", { method: "POST" }))}>Approve</button></td>
            </tr>)}</tbody></table></div>
        </section>}
      </>}
    </main>
  </DepartmentLayout>;
}
