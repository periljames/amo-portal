import InlineLoading from "../../components/shared/InlineLoading";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import ReliabilityTechlogPageEntry from "./ReliabilityTechlogPageEntry";
import ReliabilityTechlogEvidence from "./ReliabilityTechlogEvidence";
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
type SourcePageContext = {
  document_type?: string; page_flight_hours?: number;
  ttaf_brought_forward?: number | null; ttaf_updated?: number | null;
  apu_oil_added?: number | null; apu_oil_unit?: string | null;
  original_legs?: Array<{ number: number; from_airport: string | null; to_airport: string | null;
    flight_hours: number; left_oil_level: string | null; right_oil_level: string | null }>;
  deferred_defect_references?: string[]; defect_references?: string[];
  maintenance_release_ref?: string | null;
};
type Entry = EntryPayload & { id: string; review_status: string; created_at: string;
  review_note: string | null; source_scope?: "SECTOR" | "TECHLOG_PAGE";
  source_context?: SourcePageContext | null };
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
type StatusSummary = { total: number; unverified: number; status_counts: Record<string, number> };
type Revision = { changed_at: string; reason: string; before: Record<string, unknown>;
  after: Record<string, unknown> };
type View = "entry" | "techlog" | "review" | "register" | "coverage" | "trends" | "profiles";
type DailyCoverage = { operating_date: string; registered_snapshot_sectors: number; matched_sectors: number;
  unmatched_sectors: Array<{ aircraft_serial_number: string; engine_position: string; flight_leg: string;
    engine_serial_number: string | null }>; entered_octm_observations: number;
  verified_observations: number; unverified_observations: number; truncated: boolean; important: string };
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
  const location = useLocation();
  const navigate = useNavigate();
  const home = "/maintenance/" + encodeURIComponent(amoCode) + "/reliability";
  const routeTab = location.pathname.split("/reliability/octm/")[1]?.split("/")[0] || "trends";
  const validTabs: View[] = ["entry", "techlog", "review", "register", "coverage", "trends", "profiles"];
  const currentTab = validTabs.includes(routeTab as View) ? routeTab as View : "trends";
  const [view, setView] = useState<View>(currentTab);
  useEffect(() => { setView(currentTab); }, [currentTab]);
  const [form, setForm] = useState<EntryPayload>(blankEntry);
  const [correcting, setCorrecting] = useState<string | null>(null);
  const [editingPage, setEditingPage] = useState<{ aircraft: string; techsheet: string } | null>(null);
  const [correctionReason, setCorrectionReason] = useState("");
  const [entries, setEntries] = useState<Entry[]>([]);
  const [pendingEntries, setPendingEntries] = useState<Entry[]>([]);
  const [summary, setSummary] = useState<StatusSummary>({ total: 0, unverified: 0, status_counts: {} });
  const [registerPage, setRegisterPage] = useState(0);
  const [coverageDate, setCoverageDate] = useState(blankEntry().event_date);
  const [coverage, setCoverage] = useState<DailyCoverage | null>(null);
  const [coverageLoading, setCoverageLoading] = useState(false);
  const [coverageRefresh, setCoverageRefresh] = useState(0);
  const [queuePage, setQueuePage] = useState(0);
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
  const [reviewChecks, setReviewChecks] = useState({ source: false, engine: false, exposure: false });
  const [profileApproval, setProfileApproval] = useState<Profile | null>(null);
  const [profileApprovalNote, setProfileApprovalNote] = useState("");
  const [profileDataConfirmed, setProfileDataConfirmed] = useState(false);
  const [historyTarget, setHistoryTarget] = useState<Entry | null>(null);
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [selectedEngine, setSelectedEngine] = useState("");
  const [trendPage, setTrendPage] = useState(0);
  const [trendPageSize, setTrendPageSize] = useState(50);
  const [newProfile, setNewProfile] = useState({ engine_serial_number: "", installation_ref: "", engine_model: "",
    limit_qt_per_fh: "", alert_increase_percent: "", technical_data_ref: "", technical_data_revision: "", effective_from: "" });
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    const [items, pending, counts, rates, p, permissions, aircraft] = await Promise.all([
      apiRequest<Entry[]>("/reliability/octm/entries?limit=200&offset=" + registerPage * 200, { cacheTtlMs: 0 }),
      apiRequest<Entry[]>("/reliability/octm/entries?status=UNVERIFIED&limit=200&offset=" + queuePage * 200, { cacheTtlMs: 0 }),
      apiRequest<StatusSummary>("/reliability/octm/status-summary", { cacheTtlMs: 0 }),
      apiRequest<Monitoring>("/reliability/octm/monitoring", { cacheTtlMs: 0 }),
      apiRequest<Profile[]>("/reliability/octm/profiles", { cacheTtlMs: 0 }),
      apiRequest<Caps>("/reliability/capabilities"),
      apiRequest<AircraftOption[]>("/reliability/octm/aircraft"),
    ]);
    setEntries(items);
    setPendingEntries(pending);
    setSummary(counts);
    setMonitoring(rates);
    setProfiles(p);
    setCaps(permissions.capabilities);
    setAircraftOptions(aircraft);
  }, [registerPage, queuePage]);

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

  useEffect(() => {
    if (view !== "coverage") return;
    let active = true;
    setCoverageLoading(true);
    void apiRequest<DailyCoverage>("/reliability/octm/daily-coverage?operating_date=" +
      encodeURIComponent(coverageDate), { cacheTtlMs: 0 })
      .then((value) => { if (active) setCoverage(value); })
      .catch((cause) => { if (active) setError(safeError(cause)); })
      .finally(() => { if (active) setCoverageLoading(false); });
    return () => { active = false; };
  }, [view, coverageDate, coverageRefresh]);

  const has = (capability: string) => caps.includes(capability);
  const set = <K extends keyof EntryPayload>(name: K, value: EntryPayload[K]) =>
    setForm((prior) => ({ ...prior, [name]: value }));

  const run = async (operation: () => Promise<unknown>, onSuccess?: () => void) => {
    setBusy(true); setError(""); setMessage("");
    try {
      await operation();
      onSuccess?.();
      setCoverageRefresh((value) => value + 1);
      setMessage("The action was saved successfully.");
      try {
        await refresh();
      } catch (cause) {
        setError("The action was saved, but the screen could not refresh: " + safeError(cause));
      }
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
    setReviewChecks({ source: false, engine: false, exposure: false });
    setReviewLoading(true); setError("");
    try {
      const checked = await apiRequest<Readiness>("/reliability/octm/entries/" +
        encodeURIComponent(item.id) + "/readiness", { cacheTtlMs: 0 });
      setReadiness(checked);
    } catch (cause) { setError(safeError(cause)); } finally { setReviewLoading(false); }
  };

  const submitReview = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!reviewTarget) return;
    if (reviewDecision === "VERIFIED" && (!readiness?.ready_for_verification ||
      !reviewChecks.source || !reviewChecks.engine || !reviewChecks.exposure)) return;
    await run(() => apiRequest("/reliability/octm/entries/" + encodeURIComponent(reviewTarget.id) + "/review", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision: reviewDecision, note: reviewNote.trim(),
        source_checked: reviewChecks.source, engine_identity_checked: reviewChecks.engine,
        exposure_checked: reviewChecks.exposure }),
    }), () => { setReviewTarget(null); setReadiness(null); setReviewNote(""); });
  };

  const showHistory = async (item: Entry) => {
    setHistoryTarget(item); setRevisions([]); setError("");
    try {
      const result = await apiRequest<Revision[]>("/reliability/octm/entries/" +
        encodeURIComponent(item.id) + "/history", { cacheTtlMs: 0 });
      setRevisions(result);
    } catch (cause) { setError(safeError(cause)); }
  };

  const chooseCorrection = (item: Entry) => {
    if (item.source_scope === "TECHLOG_PAGE") {
      setEditingPage({ aircraft: item.aircraft_serial_number, techsheet: item.techsheet_ref });
      setView("techlog");
      navigate(home + "/octm/techlog");
      return;
    }
    const base = blankEntry();
    const raw = item as unknown as Record<string, unknown>;
    const values = Object.fromEntries(Object.keys(base).map((field) =>
      [field, raw[field] ?? (base as unknown as Record<string, unknown>)[field]])) as EntryPayload;
    setForm(values);
    setCorrecting(item.id);
    setView("entry");
    navigate(home + "/octm/entry");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const filtered = useMemo(() => entries.filter((entry) =>
    [entry.aircraft_serial_number, entry.engine_serial_number, entry.techsheet_ref, entry.installation_ref]
      .some((part) => part.toLowerCase().includes(filter.toLowerCase()))), [entries, filter]);
  const queue = pendingEntries.filter((entry) =>
    [entry.aircraft_serial_number, entry.engine_serial_number, entry.techsheet_ref, entry.installation_ref]
      .some((part) => part.toLowerCase().includes(filter.toLowerCase())));
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
  const trendChart = trend.slice(-180);
  const trendTable = monitoring.intervals.filter((row) => !selectedEngine ||
    row.engine_serial_number === selectedEngine);
  const visibleTrendTable = trendTable.slice(trendPage * trendPageSize, (trendPage + 1) * trendPageSize);

  return <main className="reliability-v2 octm">
      <header className="reliability-v2__header">
        <div>
          <p className="reliability-v2__eyebrow">Reliability / Engine monitoring</p>
          <h1>Oil consumption monitoring</h1>
          <p>Technical-log source entries, independent verification, disjoint 40 ± 10 flight-hour trends, and controlled manufacturer limits.</p>
        </div>
        <Link className="btn btn-secondary" to={home}>Reliability overview</Link>
      </header>
      <nav className="octm__tabs" aria-label="Oil consumption workspaces">
        {([["entry", "Sector entry"], ["techlog", "Techlog page"], ["review", "Review queue"], ["register", "Source register"], ["coverage", "Daily coverage"], ["trends", "Engine trends"], ["profiles", "Limit profiles"]] as const)
          .map(([key, label]) => <button key={key} type="button" className={view === key ? "octm__tab active" : "octm__tab"}
            aria-current={view === key ? "page" : undefined} onClick={() => { setView(key); navigate(home + "/octm/" + key); }}>{label}
            {key === "review" ? " (" + summary.unverified + ")" : ""}</button>)}
      </nav>
      {error && <p className="octm__error" role="alert">{error}</p>}
      {message && <p className="octm__message" role="status">{message}</p>}
      {loading ? <p><InlineLoading label={"Loading OCTM records…"}/></p> : <>
        {view === "techlog" && <ReliabilityTechlogPageEntry aircraftOptions={aircraftOptions}
          canCreate={has("reliability.ingest") || (!!editingPage && has("reliability.data_quality.resolve"))}
          editPage={editingPage} onExitEdit={() => { setEditingPage(null); setView("register"); navigate(home + "/octm/register"); }}
          onSaved={refresh} />}
        {view === "entry" && <section className="octm__panel">
          <h2>{correcting ? "Correct existing source record" : "Register sector-level oil event"}</h2>
          <p>Use the <strong>Techlog page</strong> tab for the paper SL/MCM/1 format:
          its Oil Added values are PAGE totals, not flight-leg totals. Only use this sector
          screen where a separate source identifies individual sector oil quantities.</p>
          <p>Every engine/sector event has a unique sequence. Select <strong>Checked — zero added</strong> only when an actual oil check found no top-up necessary.
             Use <strong>Missing</strong> when the record is unavailable, never to mean zero.</p>
           <p className="octm__hint">Check engine serial, position and installation against technical records for the selected date.
             Previously entered engine details are hints, not installation approvals. Flight hours belong to the flight sector
             and must not be counted again for repeated oil servicing within the same sector.</p>
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
              {eventTypes.map((type) => <option key={type} value={type}>{
                type === "CHECK_ZERO" ? "Checked — zero added" :
                type === "MISSING" ? "Oil information missing" :
                type === "NO_OPERATION" ? "Aircraft did not operate" : type.replaceAll("_", " ")}</option>)}</select></label>
            <label>Source<select value={form.source_type} onChange={(event) => set("source_type", event.target.value as EntryPayload["source_type"])}>
              <option value="PAPER_TECHSHEET">Paper techsheet</option><option value="REVIEWED_OCR">Manually checked OCR draft</option></select></label>
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
            <div className="octm__full">
              <ReliabilityTechlogEvidence aircraft={form.aircraft_serial_number}
                techsheet={form.techsheet_ref} reference={form.source_evidence_ref || ""}
                canUpload={has("reliability.ingest") || has("reliability.data_quality.resolve")}
                onReference={(reference) => set("source_evidence_ref", reference)} />
            </div>
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
          <h2>{view === "review" ? "Unverified source records" : "Source register"}</h2>
          <p>Only verified observations enter official intervals. Crew closure does not substitute for maintenance completion.</p>
          <label>Find source or engine<input value={filter} onChange={(event) => setFilter(event.target.value)} /></label>
          <div className={"octm__review-layout " + (reviewTarget || historyTarget ? "octm__review-layout--open" : "")}>
            <div className="octm__review-register">
          <div className="octm__table-wrap"><table><thead><tr><th>Date / sequence</th><th>Aircraft</th><th>Engine / installation</th><th>Techsheet</th><th>Event</th><th>Qty</th><th>FH</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>{(view === "review" ? queue : filtered).map((item) => <tr key={item.id}>
              <td>{item.event_date} · {item.event_sequence}</td><td>{item.aircraft_serial_number}</td>
              <td>{item.engine_serial_number}<small>{item.installation_ref}</small></td><td>{item.techsheet_ref}</td>
<td>{item.event_type}<small>{item.source_scope === "TECHLOG_PAGE" ? "Page total" : "Sector event"}</small></td><td>{item.oil_quantity ?? "—"} {item.oil_unit ?? ""}</td>
              <td>{item.flight_hours ?? "—"}</td><td>{item.review_status}<small>{item.review_note}</small></td>
              <td><div className="octm__row-actions">
                <button disabled={!has("reliability.data_quality.resolve") || busy || item.review_status === "VERIFIED"}
                  onClick={() => void prepareReview(item, "VERIFIED")}>Inspect / verify</button>
                <button disabled={!has("reliability.data_quality.resolve") || busy || item.review_status === "VERIFIED"}
                  onClick={() => void prepareReview(item, "RETURNED")}>Return</button>
                <button disabled={busy || !(has("reliability.data_quality.resolve") ||
                  (item.review_status !== "VERIFIED" && has("reliability.ingest")))}
                  onClick={() => chooseCorrection(item)}>{item.source_scope === "TECHLOG_PAGE" ? "Correct page" : "Correct"}</button>
                <button onClick={() => void showHistory(item)}>History</button>
              </div></td>
            </tr>)}</tbody></table></div>
          {!(view === "review" ? queue : filtered).length && <p>No source entries match the filter.</p>}
          <div className="octm__pagination">
            <span>{view === "review" ? summary.unverified : summary.total} source records · page
              {" "}{(view === "review" ? queuePage : registerPage) + 1} · filter applies to current page
            </span>
            <button type="button" className="btn btn-secondary" disabled={busy ||
                (view === "review" ? queuePage : registerPage) === 0}
              onClick={() => (view === "review" ? setQueuePage : setRegisterPage)((page) => Math.max(0, page - 1))}>
              Previous
            </button>
            <button type="button" className="btn btn-secondary" disabled={busy ||
                ((view === "review" ? queuePage : registerPage) + 1) * 200 >=
                 (view === "review" ? summary.unverified : summary.total)}
              onClick={() => (view === "review" ? setQueuePage : setRegisterPage)((page) => page + 1)}>
              Next
            </button>
          </div>
            </div>
            {(historyTarget || reviewTarget) && <aside className="octm__review-aside" aria-label="Selected OCTM record">
          {historyTarget && <div className="octm__review" role="region" aria-label="Source correction history">
            <h3>Correction history — {historyTarget.techsheet_ref} / {historyTarget.engine_serial_number}</h3>
            {!revisions.length && <p>No recorded corrections for this entry.</p>}
            {revisions.map((revision, index) => <details key={revision.changed_at + index}>
              <summary>{revision.changed_at} — {revision.reason}</summary>
              <div className="octm__table-wrap"><table><thead><tr><th>Field</th><th>Original value</th><th>Replacement value</th></tr></thead>
                <tbody>{Object.keys(revision.after).filter((name) =>
                  JSON.stringify(revision.before[name]) !== JSON.stringify(revision.after[name])).map((field) =>
                  <tr key={field}><td>{field.replaceAll("_", " ")}</td>
                    <td>{String(revision.before[field] ?? "Not recorded")}</td>
                    <td>{String(revision.after[field] ?? "Not recorded")}</td></tr>)}</tbody></table></div>
            </details>)}
            <button type="button" className="btn btn-secondary" onClick={() => setHistoryTarget(null)}>Close history</button>
          </div>}
          {reviewTarget && <div className="octm__review" role="region" aria-label="Source verification">
            <h3>Review {reviewTarget.techsheet_ref} · {reviewTarget.engine_serial_number}</h3>
            <p>Source evidence: <strong>{reviewTarget.source_evidence_ref || "Not provided"}</strong>.
              Sector: {reviewTarget.sector_ref || "Not entered"}.
              Oil reference: {reviewTarget.reference_method || "Not entered"} / {reviewTarget.reference_level || "Not entered"}.</p>
            {reviewTarget.source_evidence_ref?.startsWith("OCTM_ASSET:") &&
              <ReliabilityTechlogEvidence aircraft={reviewTarget.aircraft_serial_number}
                techsheet={reviewTarget.techsheet_ref}
                reference={reviewTarget.source_evidence_ref} />}
            <p>Maintenance completed: {reviewTarget.maintenance_complete}.
              Oil: {reviewTarget.oil_quantity ?? "not recorded"} {reviewTarget.oil_unit || ""}.
              Flight hours: {reviewTarget.flight_hours ?? "not recorded"}.</p>
            {reviewTarget.source_scope === "TECHLOG_PAGE" && reviewTarget.source_context && <div className="octm__review">
              <h4>Original SL/MCM/1 page details — distinct from sector oil uplift</h4>
              <p>Source Flight Time total: {reviewTarget.source_context.page_flight_hours ?? "not recorded"} FH.
                TTAF: {reviewTarget.source_context.ttaf_brought_forward ?? "—"} to
                {" "}{reviewTarget.source_context.ttaf_updated ?? "—"}.
                APU oil: {reviewTarget.source_context.apu_oil_added ?? "not recorded"}
                {" "}{reviewTarget.source_context.apu_oil_unit ?? ""} (excluded from engine OCR).</p>
              <p>Maintenance release reference: {reviewTarget.source_context.maintenance_release_ref || "Not provided"}.
                ADD links: {reviewTarget.source_context.deferred_defect_references?.join(", ") || "None entered"}.</p>
              <div className="octm__table-wrap"><table><thead><tr><th>Leg</th><th>From</th><th>To</th>
                <th>Flight time (FH)</th><th>L/H oil level</th><th>R/H oil level</th></tr></thead>
                <tbody>{reviewTarget.source_context.original_legs?.map((leg) => <tr key={leg.number}>
                  <td>{leg.number}</td><td>{leg.from_airport || "—"}</td><td>{leg.to_airport || "—"}</td>
                  <td>{leg.flight_hours}</td><td>{leg.left_oil_level || "Not recorded"}</td>
                  <td>{leg.right_oil_level || "Not recorded"}</td>
                </tr>)}</tbody></table></div>
            </div>}
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
              {reviewDecision === "VERIFIED" && <div className="octm__attestations">
                <label><input type="checkbox" checked={reviewChecks.source}
                  onChange={(event) => setReviewChecks((previous) => ({ ...previous, source: event.target.checked }))} />
                  I inspected the original techsheet and confirmed the source quantities and servicing event.</label>
                <label><input type="checkbox" checked={reviewChecks.engine}
                  onChange={(event) => setReviewChecks((previous) => ({ ...previous, engine: event.target.checked }))} />
                  I checked the physical engine serial, position and installation against technical records.</label>
                <label><input type="checkbox" checked={reviewChecks.exposure}
                  onChange={(event) => setReviewChecks((previous) => ({ ...previous, exposure: event.target.checked }))} />
                  I confirmed the flight-hour counter/sector exposure and checked duplicate servicing events.</label>
              </div>}
              <div className="octm__row-actions">
                <button type="submit" className="btn btn-primary" disabled={busy || reviewLoading ||
                  reviewNote.trim().length < 3 || (reviewDecision === "VERIFIED" &&
                    (!readiness?.ready_for_verification || !reviewChecks.source || !reviewChecks.engine || !reviewChecks.exposure))}>
                  {reviewDecision === "VERIFIED" ? "Confirm independent verification" : "Return for correction"}</button>
                <button type="button" className="btn btn-secondary" onClick={() => { setReviewTarget(null); setReadiness(null); }}>Cancel</button>
              </div>
            </form>
          </div>}
            </aside>}
          </div>
        </section>}
        {view === "coverage" && <section className="octm__panel">
          <h2>Daily data coverage reconciliation</h2>
          <p>Compare Oil Consumption entries with the engine-flight sectors already recorded in Reliability.
            This is a follow-up queue, not a substitute for actual techsheet receipt and utilization reconciliation.</p>
          <label>Operating date<input type="date" value={coverageDate} max={blankEntry().event_date}
            onChange={(event) => setCoverageDate(event.target.value)} /></label>
          {coverageLoading ? <p>Comparing registered engine sectors…</p> : coverage && <>
            <div className="octm__metrics">
              <div><strong>{coverage.registered_snapshot_sectors}</strong><span>Recorded engine sectors</span></div>
              <div><strong>{coverage.matched_sectors}</strong><span>Matched OCTM entries</span></div>
              <div><strong>{coverage.unmatched_sectors.length}</strong><span>Unmatched source sectors</span></div>
              <div><strong>{coverage.unverified_observations}</strong><span>Entries awaiting verification</span></div>
            </div>
            <p className="octm__hint">{coverage.important}</p>
            {coverage.truncated && <p className="octm__error">Daily reconciliation is truncated. Review the complete source dataset.</p>}
            <div className="octm__table-wrap"><table><thead><tr>
              <th>Aircraft</th><th>Engine position</th><th>Engine serial (source)</th><th>Flight sector not matched</th>
            </tr></thead><tbody>{coverage.unmatched_sectors.map((item, index) => <tr key={item.aircraft_serial_number + item.flight_leg + index}>
              <td>{item.aircraft_serial_number}</td><td>{item.engine_position}</td>
              <td>{item.engine_serial_number || "Not recorded"}</td><td>{item.flight_leg}</td>
            </tr>)}</tbody></table></div>
            {!coverage.registered_snapshot_sectors && <p>No engine-flight snapshots exist for this date.
              This does not confirm that no aircraft operated.</p>}
          </>}
        </section>}
        {view === "trends" && <section className="octm__panel">
          <h2>Verified engine monitoring intervals</h2>
          <p>{monitoring.verified_source_count} verified source entries. Rates are recomputed from matched quantities and flight hours, not an average of spreadsheet rates.</p>
          {monitoring.truncated && <p role="alert">Results are truncated at 20,000 observations. Do not use for formal reporting until the complete period is retrieved.</p>}
          <label>Engine <select value={selectedEngine} onChange={(event) => { setSelectedEngine(event.target.value); setTrendPage(0); }}>
            <option value="">All engines</option>{engines.map((e) => <option value={e} key={e}>{e}</option>)}</select></label>
          <p className="octm__hint">Trend chart shows up to the latest 180 complete intervals. The paged table below covers all loaded verified intervals.
            Open the source register to review individual techsheets and corrections.</p>
          {!!trendChart.length && <div className="octm__chart"><ResponsiveContainer width="100%" height={320}>
            <LineChart data={trendChart}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="window_end" /><YAxis />
              <Tooltip /><Legend /><Line dataKey="rate_qt_per_fh" name="Oil qt / FH" stroke="#0f766e" />
              <Line dataKey="manufacturer_limit_qt_per_fh" name="Approved limit qt / FH" stroke="#b45309" strokeDasharray="5 5" connectNulls={false} /></LineChart>
          </ResponsiveContainer></div>}
          <div className="octm__table-wrap"><table><thead><tr><th>Engine</th><th>Installation</th><th>Interval</th><th>Oil qt</th><th>FH</th><th>Rate qt/FH</th><th>Approved limit</th><th>Result</th></tr></thead>
            <tbody>{visibleTrendTable.map((item, index) => <tr key={item.engine_serial_number + item.window_end + index}>
              <td>{item.engine_serial_number}</td><td>{item.installation_ref}</td>
              <td>{item.window_start} – {item.window_end}</td><td>{item.oil_added_quarts}</td><td>{item.flight_hours}</td>
              <td>{item.rate_qt_per_fh ?? "Withheld"}</td><td>{item.manufacturer_limit_qt_per_fh ?? "Not approved"}</td>
              <td>{item.status === "OUT_OF_RANGE" ? "Interval outside 30–50 FH" : item.manufacturer_limit_exceeded ? "Manufacturer limit exceeded" : item.trend_alert ? "Trend alert" : item.manufacturer_limit_exceeded === null ? "Limit unverified" : "Within limit"}</td>
            </tr>)}</tbody></table></div>
          <div className="octm__pagination" aria-label="Oil consumption interval pagination">
            <span>{trendTable.length} verified interval records ·
              page {trendPage + 1} / {Math.max(1, Math.ceil(trendTable.length / trendPageSize))}</span>
            <label>Rows per page <select value={trendPageSize}
              onChange={(event) => { setTrendPageSize(Number(event.target.value)); setTrendPage(0); }}>
              <option value="25">25</option><option value="50">50</option><option value="100">100</option>
            </select></label>
            <button type="button" className="btn btn-secondary" disabled={trendPage === 0}
              onClick={() => setTrendPage((value) => Math.max(0, value - 1))}>Previous</button>
            <button type="button" className="btn btn-secondary" disabled={(trendPage + 1) * trendPageSize >= trendTable.length}
              onClick={() => setTrendPage((value) => value + 1)}>Next</button>
          </div>
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
                { setProfileApproval(profile); setProfileApprovalNote(""); setProfileDataConfirmed(false); }}>Review / approve</button></td>
            </tr>)}</tbody></table></div>
          {profileApproval && <form className="octm__review" onSubmit={(event) => { event.preventDefault();
            void run(() => apiRequest("/reliability/octm/profiles/" + encodeURIComponent(profileApproval.id) + "/approve", {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ confirmed_current_technical_data: profileDataConfirmed, note: profileApprovalNote.trim() }),
            }), () => { setProfileApproval(null); setProfileApprovalNote(""); setProfileDataConfirmed(false); });
          }}>
            <h3>Authorize engine limit — {profileApproval.engine_serial_number}, v{profileApproval.version}</h3>
            <p>Manufacturer reference: {profileApproval.technical_data_ref}, revision {profileApproval.technical_data_revision}.
              Limit: {profileApproval.limit_qt_per_fh} qt/FH.</p>
            <label className="octm__continue"><input type="checkbox" checked={profileDataConfirmed}
              onChange={(event) => setProfileDataConfirmed(event.target.checked)} />
              I checked the cited manufacturer technical data and confirmed the current limit and applicability.</label>
            <label>Independent approval basis<textarea required minLength={5} rows={2} value={profileApprovalNote}
              onChange={(event) => setProfileApprovalNote(event.target.value)} /></label>
            <div className="octm__row-actions">
              <button className="btn btn-primary" disabled={busy || !profileDataConfirmed ||
                profileApprovalNote.trim().length < 5}>Confirm profile approval</button>
              <button type="button" className="btn btn-secondary" onClick={() => setProfileApproval(null)}>Cancel</button>
            </div>
          </form>}
        </section>}
      </>}
  </main>;
}
