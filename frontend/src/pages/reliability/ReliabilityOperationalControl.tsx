import React, { useEffect, useMemo, useState } from "react";

import { listAircraft, type AircraftRead } from "../../services/fleet";
import { apiRequest } from "../../services/apiClient";
import { qmsListFindingsBulk, type QMSFindingOut } from "../../services/qms";

import "./ReliabilityOperationalControl.css";

type View = "overview" | "flight" | "deferrals" | "shop" | "sms" | "qms" | "workbooks";
type StatusMap = Record<string, number>;
type RunMutation = (action: () => Promise<unknown>, success: string) => Promise<boolean>;

type Summary = {
  flight_operations: StatusMap;
  deferrals: StatusMap;
  component_shop: StatusMap;
  sms: StatusMap;
  workbooks: StatusMap;
  generated_at: string;
};

type ReadinessItem = {
  code: string;
  module: string;
  dataset: string;
  implementation_state: string;
  connection_state: string;
  available_record_count: number;
  ingested_record_count: number;
  latest_available_at?: string | null;
  last_success_at?: string | null;
  detail: string;
};

type Readiness = { generated_at: string; items: ReadinessItem[] };

type FlightOperation = {
  id: string;
  record_number: string;
  revision: number;
  event_type: string;
  occurred_at: string;
  aircraft_serial_number: string;
  flight_number: string;
  origin_station?: string | null;
  destination_station?: string | null;
  scheduled_departure_at?: string | null;
  actual_departure_at?: string | null;
  delay_minutes?: number | null;
  dispatch_impact?: string | null;
  severity: string;
  ata_chapter?: string | null;
  description: string;
  status: string;
  canonical_event_id?: number | null;
};

type Deferral = {
  id: string;
  deferral_number: string;
  revision: number;
  deferral_type: string;
  aircraft_serial_number: string;
  defect_reference: string;
  item_reference: string;
  category?: string | null;
  applied_at: string;
  expires_at: string;
  description: string;
  status: string;
  canonical_event_id?: number | null;
};

type ShopFinding = {
  id: string;
  shop_order_reference: string;
  revision: number;
  event_type: string;
  part_number: string;
  component_serial_number: string;
  aircraft_serial_number?: string | null;
  confirmed_failure?: boolean | null;
  disposition: string;
  status: string;
  canonical_event_id?: number | null;
};

type SmsOccurrence = {
  id: string;
  sms_reference: string;
  revision: number;
  occurred_at: string;
  aircraft_serial_number?: string | null;
  risk_classification: string;
  investigation_status: string;
  reliability_relevant: boolean;
  reliability_link_reason?: string | null;
  description: string;
  status: string;
  canonical_event_id?: number | null;
};

type WorkbookImport = {
  id: string;
  original_filename: string;
  revision: number;
  status: string;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  approved_rows: number;
  rejected_rows: number;
  ingested_rows: number;
  created_at: string;
};

type WorkbookRow = {
  id: string;
  sheet_name: string;
  source_row_number: number;
  raw_json: Record<string, unknown>;
  mapped_json: Record<string, unknown>;
  validation_errors_json: unknown[];
  status: string;
  decision_note?: string | null;
  canonical_event_id?: number | null;
};

type ActionRequest =
  | { kind: "FLIGHT_APPROVE"; row: FlightOperation }
  | { kind: "FLIGHT_CLOSE"; row: FlightOperation }
  | { kind: "DEFERRAL_APPROVE"; row: Deferral }
  | { kind: "DEFERRAL_EXTEND"; row: Deferral }
  | { kind: "DEFERRAL_CLOSE"; row: Deferral }
  | { kind: "SHOP_APPROVE"; row: ShopFinding }
  | { kind: "SHOP_RELEASE"; row: ShopFinding }
  | { kind: "SMS_ASSESS"; row: SmsOccurrence }
  | { kind: "WORKBOOK_APPROVE"; row: WorkbookImport }
  | { kind: "WORKBOOK_INGEST"; row: WorkbookImport }
  | { kind: "WORKBOOK_ROW_APPROVE"; workbook: WorkbookImport; row: WorkbookRow }
  | { kind: "WORKBOOK_ROW_REJECT"; workbook: WorkbookImport; row: WorkbookRow };

type ViewDefinition = {
  id: View;
  label: string;
  shortLabel: string;
  description: string;
};

const BASE = "/reliability/operational-sources";
const VIEW_DEFINITIONS: ViewDefinition[] = [
  { id: "overview", label: "Control overview", shortLabel: "Overview", description: "Attention, source health and pending lifecycle work." },
  { id: "flight", label: "Flight Operations", shortLabel: "Flight Ops", description: "Technical interruptions and operational consequences." },
  { id: "deferrals", label: "MEL / CDL control", shortLabel: "MEL / CDL", description: "Approved deferral application, expiry, extension and closure." },
  { id: "shop", label: "Component shop", shortLabel: "Shop", description: "Confirmed failures, NFF outcomes, disposition and release." },
  { id: "sms", label: "SMS relevance", shortLabel: "SMS", description: "Assess safety occurrences for technical Reliability relevance." },
  { id: "qms", label: "QMS linkage", shortLabel: "QMS", description: "Select controlled findings and preserve their objective evidence." },
  { id: "workbooks", label: "Historical migration", shortLabel: "Migration", description: "Map, reconcile, approve and ingest historical records." },
];

const SOURCE_LABELS: Record<string, string> = {
  "FLIGHT-OPERATIONS": "Flight Operations",
  "MEL-CDL": "MEL / CDL",
  "COMPONENT-SHOP-FINDINGS": "Component shop",
  "SMS-EVENTS": "SMS occurrences",
  "QMS-FINDINGS": "QMS findings",
  "WORKBOOK-HISTORY": "Historical workbooks",
};

const EVENT_LABELS: Record<string, string> = {
  TECHNICAL_DELAY: "Technical delay",
  TECHNICAL_CANCELLATION: "Technical cancellation",
  RETURN_TO_GATE: "Return to gate",
  AIR_TURNBACK: "Air turnback",
  DIVERSION: "Diversion",
  IN_FLIGHT_SHUTDOWN: "In-flight shutdown",
  ABORTED_TAKEOFF: "Aborted take-off",
  SHOP_FINDING: "Confirmed shop finding",
  NO_FAULT_FOUND: "No fault found",
};

const EVENT_IMPACT: Record<string, string> = {
  TECHNICAL_DELAY: "DELAYED_DEPARTURE",
  TECHNICAL_CANCELLATION: "CANCELLED",
  RETURN_TO_GATE: "RETURN_TO_GATE",
  AIR_TURNBACK: "AIR_TURNBACK",
  DIVERSION: "DIVERTED",
  IN_FLIGHT_SHUTDOWN: "IN_FLIGHT_SHUTDOWN",
  ABORTED_TAKEOFF: "ABORTED_TAKEOFF",
};

function displayDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function toLocalInput(value?: string | Date | null): string {
  const date = value instanceof Date ? value : value ? new Date(value) : new Date();
  if (Number.isNaN(date.getTime())) return "";
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

function localDateTime(offsetHours = 0): string {
  return toLocalInput(new Date(Date.now() + offsetHours * 60 * 60 * 1000));
}

function iso(value: string): string {
  return new Date(value).toISOString();
}

function formValue(data: FormData, key: string): string {
  return String(data.get(key) || "").trim();
}

function nullable(data: FormData, key: string): string | null {
  return formValue(data, key) || null;
}

function numberOrNull(data: FormData, key: string): number | null {
  const value = formValue(data, key);
  return value ? Number(value) : null;
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : "The operational Reliability request failed.";
}

function request<T>(path: string): Promise<T> {
  return apiRequest<T>(path, { cacheTtlMs: 0 });
}

function mutate<T>(path: string, payload?: unknown): Promise<T> {
  return apiRequest<T>(path, {
    method: "POST",
    headers: payload instanceof FormData ? undefined : { "Content-Type": "application/json", Accept: "application/json" },
    body: payload instanceof FormData ? payload : payload === undefined ? undefined : JSON.stringify(payload),
    cacheTtlMs: 0,
  });
}

function statusClass(value?: string | null): string {
  return `reliability-v2__status reliability-v2__status--${(value || "unknown").toLowerCase().replaceAll("_", "-").replaceAll(" ", "-")}`;
}

function statusCount(values: StatusMap | undefined, ...statuses: string[]): number {
  return statuses.reduce((total, status) => total + Number(values?.[status] || 0), 0);
}

function totalCount(values: StatusMap | undefined): number {
  return Object.values(values || {}).reduce((total, value) => total + Number(value || 0), 0);
}

function delayMinutes(scheduled: string, actual: string): number | null {
  if (!scheduled || !actual) return null;
  const scheduledTime = new Date(scheduled).getTime();
  const actualTime = new Date(actual).getTime();
  if (!Number.isFinite(scheduledTime) || !Number.isFinite(actualTime)) return null;
  return Math.round((actualTime - scheduledTime) / 60_000);
}

function recommendedSeverity(eventType: string, delay: number | null): string {
  if (["IN_FLIGHT_SHUTDOWN", "AIR_TURNBACK", "ABORTED_TAKEOFF"].includes(eventType)) return "HIGH";
  if (["DIVERSION", "RETURN_TO_GATE", "TECHNICAL_CANCELLATION"].includes(eventType)) return "MEDIUM";
  if (eventType === "TECHNICAL_DELAY") {
    if (delay != null && delay >= 120) return "HIGH";
    if (delay != null && delay < 15) return "LOW";
  }
  return "MEDIUM";
}

function relativeExpiry(value: string): string {
  const milliseconds = new Date(value).getTime() - Date.now();
  if (!Number.isFinite(milliseconds)) return "Unknown";
  const hours = Math.round(Math.abs(milliseconds) / 3_600_000);
  if (milliseconds < 0) return `${hours} h overdue`;
  if (hours < 48) return `${hours} h remaining`;
  return `${Math.round(hours / 24)} d remaining`;
}

function aircraftLabel(aircraft: AircraftRead): string {
  const identity = [aircraft.registration, aircraft.make, aircraft.model].filter(Boolean).join(" · ");
  return `${identity || aircraft.serial_number} — S/N ${aircraft.serial_number}`;
}

function fieldText(value: unknown): string {
  if (value == null || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default function ReliabilityOperationalControl(): React.ReactElement {
  const [view, setView] = useState<View>("overview");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [aircraft, setAircraft] = useState<AircraftRead[]>([]);
  const [flights, setFlights] = useState<FlightOperation[]>([]);
  const [deferrals, setDeferrals] = useState<Deferral[]>([]);
  const [shop, setShop] = useState<ShopFinding[]>([]);
  const [sms, setSms] = useState<SmsOccurrence[]>([]);
  const [qmsFindings, setQmsFindings] = useState<QMSFindingOut[]>([]);
  const [workbooks, setWorkbooks] = useState<WorkbookImport[]>([]);
  const [selectedWorkbook, setSelectedWorkbook] = useState<string>("");
  const [workbookRows, setWorkbookRows] = useState<WorkbookRow[]>([]);
  const [loadedViews, setLoadedViews] = useState<Partial<Record<View, boolean>>>({});
  const [pageLoading, setPageLoading] = useState(true);
  const [viewLoading, setViewLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [action, setAction] = useState<ActionRequest | null>(null);

  const loadOverview = async () => {
    const [nextSummary, nextReadiness] = await Promise.all([
      request<Summary>(`${BASE}/summary`),
      request<Readiness>("/reliability/authoritative-sources/readiness"),
    ]);
    setSummary(nextSummary);
    setReadiness(nextReadiness);
  };

  const loadWorkbookRows = async (importId: string) => {
    setSelectedWorkbook(importId);
    setWorkbookRows(importId ? await request<WorkbookRow[]>(`${BASE}/workbooks/${encodeURIComponent(importId)}/rows`) : []);
  };

  const loadView = async (target: View, force = false) => {
    if (target === "overview") return;
    if (loadedViews[target] && !force) return;
    setViewLoading(true);
    try {
      if (target === "flight") setFlights(await request<FlightOperation[]>(`${BASE}/flight-operations`));
      if (target === "deferrals") setDeferrals(await request<Deferral[]>(`${BASE}/deferrals`));
      if (target === "shop") setShop(await request<ShopFinding[]>(`${BASE}/component-shop`));
      if (target === "sms") setSms(await request<SmsOccurrence[]>(`${BASE}/sms`));
      if (target === "qms") setQmsFindings(await qmsListFindingsBulk({ limit: 250 }, { silent: true }));
      if (target === "workbooks") {
        const nextImports = await request<WorkbookImport[]>(`${BASE}/workbooks`);
        setWorkbooks(nextImports);
        const selectedStillExists = nextImports.some((item) => item.id === selectedWorkbook);
        const nextSelected = selectedStillExists ? selectedWorkbook : nextImports[0]?.id || "";
        setSelectedWorkbook(nextSelected);
        setWorkbookRows(nextSelected ? await request<WorkbookRow[]>(`${BASE}/workbooks/${encodeURIComponent(nextSelected)}/rows`) : []);
      }
      setLoadedViews((current) => ({ ...current, [target]: true }));
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setViewLoading(false);
    }
  };

  useEffect(() => {
    let active = true;
    const initialise = async () => {
      setPageLoading(true);
      setError(null);
      try {
        const [, nextAircraft] = await Promise.all([loadOverview(), listAircraft({ is_active: true })]);
        if (active) setAircraft(nextAircraft);
      } catch (caught) {
        if (active) setError(errorText(caught));
      } finally {
        if (active) setPageLoading(false);
      }
    };
    void initialise();
    return () => { active = false; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setError(null);
    setMessage(null);
    void loadView(view);
  }, [view]); // eslint-disable-line react-hooks/exhaustive-deps

  const run: RunMutation = async (operation, success) => {
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      await operation();
      setMessage(success);
      await Promise.all([loadOverview(), loadView(view, true)]);
      return true;
    } catch (caught) {
      setError(errorText(caught));
      return false;
    } finally {
      setSaving(false);
    }
  };

  const selectedImport = useMemo(
    () => workbooks.find((item) => item.id === selectedWorkbook) || null,
    [selectedWorkbook, workbooks],
  );

  const activeDefinition = VIEW_DEFINITIONS.find((item) => item.id === view) || VIEW_DEFINITIONS[0];

  return <div className="rel-ops">
    <header className="rel-ops__header">
      <div>
        <p className="reliability-v2__eyebrow">Authoritative operational evidence</p>
        <h2>Reliability source control</h2>
        <p>{activeDefinition.description}</p>
      </div>
      <button
        type="button"
        className="btn btn-secondary"
        disabled={saving}
        onClick={() => void run(
          () => mutate("/reliability/authoritative-sources/configure"),
          "Source definitions checked and repaired where required.",
        )}
      >Repair source connections</button>
    </header>

    <nav className="rel-ops__nav" aria-label="Reliability operational workspaces">
      {VIEW_DEFINITIONS.map((item) => <button
        key={item.id}
        type="button"
        className={view === item.id ? "is-active" : ""}
        aria-current={view === item.id ? "page" : undefined}
        onClick={() => setView(item.id)}
      >
        <span>{item.shortLabel}</span>
        <strong>{viewCount(item.id, summary)}</strong>
      </button>)}
    </nav>

    {(error || message) && <div className="rel-ops__notices" aria-live="polite">
      {error && <div className="reliability-v2__error" role="alert">{error}</div>}
      {message && <div className="reliability-v2__success" role="status">{message}</div>}
    </div>}

    {pageLoading && <div className="reliability-v2__loading" role="status">Loading Reliability source controls…</div>}
    {!pageLoading && viewLoading && <div className="rel-ops__view-loading" role="status">Loading {activeDefinition.label.toLowerCase()}…</div>}

    {!pageLoading && view === "overview" && <Overview summary={summary} readiness={readiness} onNavigate={setView} />}
    {!pageLoading && !viewLoading && view === "flight" && <FlightView rows={flights} aircraft={aircraft} run={run} saving={saving} onAction={setAction} />}
    {!pageLoading && !viewLoading && view === "deferrals" && <DeferralView rows={deferrals} aircraft={aircraft} run={run} saving={saving} onAction={setAction} />}
    {!pageLoading && !viewLoading && view === "shop" && <ShopView rows={shop} aircraft={aircraft} run={run} saving={saving} onAction={setAction} />}
    {!pageLoading && !viewLoading && view === "sms" && <SmsView rows={sms} aircraft={aircraft} run={run} saving={saving} onAction={setAction} />}
    {!pageLoading && !viewLoading && view === "qms" && <QmsLinkView findings={qmsFindings} aircraft={aircraft} run={run} saving={saving} />}
    {!pageLoading && !viewLoading && view === "workbooks" && <WorkbookView
      imports={workbooks}
      rows={workbookRows}
      selected={selectedImport}
      onSelect={loadWorkbookRows}
      run={run}
      saving={saving}
      onAction={setAction}
    />}

    {action && <ActionDialog action={action} run={run} saving={saving} onClose={() => setAction(null)} />}
  </div>;
}

function viewCount(view: View, summary: Summary | null): number {
  if (!summary) return 0;
  if (view === "flight") return totalCount(summary.flight_operations);
  if (view === "deferrals") return totalCount(summary.deferrals);
  if (view === "shop") return totalCount(summary.component_shop);
  if (view === "sms") return totalCount(summary.sms);
  if (view === "workbooks") return totalCount(summary.workbooks);
  if (view === "overview") {
    return statusCount(summary.flight_operations, "DRAFT")
      + statusCount(summary.deferrals, "DRAFT", "EXPIRED")
      + statusCount(summary.component_shop, "DRAFT")
      + statusCount(summary.sms, "DRAFT");
  }
  return 0;
}

function Overview({ summary, readiness, onNavigate }: { summary: Summary | null; readiness: Readiness | null; onNavigate: (view: View) => void }) {
  const pendingFlights = statusCount(summary?.flight_operations, "DRAFT");
  const pendingDeferrals = statusCount(summary?.deferrals, "DRAFT") + statusCount(summary?.deferrals, "EXPIRED");
  const pendingShop = statusCount(summary?.component_shop, "DRAFT", "APPROVED");
  const pendingSms = statusCount(summary?.sms, "DRAFT");
  const syncGap = (readiness?.items || []).reduce(
    (total, item) => total + Math.max(item.available_record_count - item.ingested_record_count, 0),
    0,
  );

  return <div className="rel-ops__workspace">
    <section className="rel-ops__attention" aria-labelledby="rel-ops-attention">
      <div className="rel-ops__section-head">
        <div><p className="reliability-v2__eyebrow">Work requiring action</p><h3 id="rel-ops-attention">Operational attention</h3></div>
        <span>Updated {displayDate(summary?.generated_at)}</span>
      </div>
      <div className="rel-ops__attention-grid">
        <AttentionItem value={pendingFlights} label="Flight Ops approvals" detail="Draft operational occurrences" onClick={() => onNavigate("flight")} tone={pendingFlights ? "warning" : "ok"} />
        <AttentionItem value={pendingDeferrals} label="Deferral actions" detail="Draft or expired MEL/CDL records" onClick={() => onNavigate("deferrals")} tone={statusCount(summary?.deferrals, "EXPIRED") ? "danger" : pendingDeferrals ? "warning" : "ok"} />
        <AttentionItem value={pendingShop} label="Shop decisions" detail="Approval or release still required" onClick={() => onNavigate("shop")} tone={pendingShop ? "warning" : "ok"} />
        <AttentionItem value={pendingSms} label="SMS assessments" detail="Awaiting Reliability relevance decision" onClick={() => onNavigate("sms")} tone={pendingSms ? "warning" : "ok"} />
        <AttentionItem value={syncGap} label="Canonical sync gap" detail="Approved source revisions not yet ingested" tone={syncGap ? "danger" : "ok"} />
      </div>
    </section>

    <section className="rel-ops__source-health" aria-labelledby="rel-ops-source-health">
      <div className="rel-ops__section-head">
        <div><p className="reliability-v2__eyebrow">Source assurance</p><h3 id="rel-ops-source-health">Authoritative feed health</h3></div>
        <span>Only approved or assessed source revisions count as available.</span>
      </div>
      <div className="rel-ops__health-list">
        {(readiness?.items || []).map((item) => {
          const pending = Math.max(item.available_record_count - item.ingested_record_count, 0);
          return <article key={item.code}>
            <div>
              <strong>{SOURCE_LABELS[item.code] || item.module}</strong>
              <small>{item.dataset}</small>
            </div>
            <span className={statusClass(item.connection_state)}>{item.connection_state.replaceAll("_", " ")}</span>
            <div className="rel-ops__health-count"><strong>{item.ingested_record_count}</strong><small>of {item.available_record_count} ingested</small></div>
            <div><strong>{pending ? `${pending} pending` : "Current"}</strong><small>Last sync {displayDate(item.last_success_at)}</small></div>
          </article>;
        })}
        {!readiness?.items.length && <p className="reliability-v2__empty">No source readiness records are available.</p>}
      </div>
    </section>
  </div>;
}

function AttentionItem({ value, label, detail, tone, onClick }: { value: number; label: string; detail: string; tone: "ok" | "warning" | "danger"; onClick?: () => void }) {
  const content = <><strong>{value}</strong><span>{label}</span><small>{detail}</small></>;
  const className = `rel-ops__attention-item is-${tone}`;
  if (onClick) return <button type="button" className={className} onClick={onClick}>{content}</button>;
  return <div className={className}>{content}</div>;
}

function AircraftSelect({ aircraft, required = false, allowFleet = false, name = "aircraft_serial_number", label = "Aircraft" }: { aircraft: AircraftRead[]; required?: boolean; allowFleet?: boolean; name?: string; label?: string }) {
  return <label>{label}
    <select name={name} required={required} defaultValue="">
      <option value="">{allowFleet ? "Fleet / not aircraft-specific" : "Select aircraft"}</option>
      {aircraft.map((item) => <option key={item.serial_number} value={item.serial_number}>{aircraftLabel(item)}</option>)}
    </select>
  </label>;
}

function FieldGroup({ title, detail, children }: { title: string; detail?: string; children: React.ReactNode }) {
  return <fieldset className="rel-ops__field-group">
    <legend>{title}</legend>
    {detail && <p>{detail}</p>}
    <div className="rel-ops__fields">{children}</div>
  </fieldset>;
}

function FlightView({ rows, aircraft, run, saving, onAction }: { rows: FlightOperation[]; aircraft: AircraftRead[]; run: RunMutation; saving: boolean; onAction: (action: ActionRequest) => void }) {
  const [eventType, setEventType] = useState("TECHNICAL_DELAY");
  const [scheduledDeparture, setScheduledDeparture] = useState(localDateTime());
  const [actualDeparture, setActualDeparture] = useState(localDateTime());
  const [occurrenceTime, setOccurrenceTime] = useState(localDateTime());
  const [severity, setSeverity] = useState("MEDIUM");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const calculatedDelay = delayMinutes(scheduledDeparture, actualDeparture);
  const isDelay = eventType === "TECHNICAL_DELAY";
  const isCancellation = eventType === "TECHNICAL_CANCELLATION";
  const timingInvalid = isDelay && calculatedDelay != null && calculatedDelay <= 0;

  useEffect(() => {
    setSeverity(recommendedSeverity(eventType, calculatedDelay));
  }, [eventType, calculatedDelay]);

  const filtered = useMemo(() => rows.filter((row) => {
    const haystack = `${row.record_number} ${row.flight_number} ${row.aircraft_serial_number} ${row.origin_station || ""} ${row.destination_station || ""} ${row.event_type}`.toLowerCase();
    return (statusFilter === "ALL" || row.status === statusFilter) && haystack.includes(query.toLowerCase());
  }), [query, rows, statusFilter]);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (timingInvalid || (isDelay && calculatedDelay == null)) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const payload: Record<string, unknown> = {
      record_number: formValue(data, "record_number"),
      event_type: eventType,
      occurred_at: isDelay ? null : iso(occurrenceTime),
      aircraft_serial_number: formValue(data, "aircraft_serial_number"),
      flight_number: formValue(data, "flight_number").toUpperCase(),
      origin_station: formValue(data, "origin_station").toUpperCase(),
      destination_station: formValue(data, "destination_station").toUpperCase(),
      scheduled_departure_at: scheduledDeparture ? iso(scheduledDeparture) : null,
      actual_departure_at: isCancellation || !actualDeparture ? null : iso(actualDeparture),
      dispatch_impact: EVENT_IMPACT[eventType],
      severity,
      ata_chapter: nullable(data, "ata_chapter"),
      description: formValue(data, "description"),
    };
    const completed = await run(() => mutate(`${BASE}/flight-operations`, payload), "Flight Operations occurrence created for approval.");
    if (completed) {
      form.reset();
      setEventType("TECHNICAL_DELAY");
      setScheduledDeparture(localDateTime());
      setActualDeparture(localDateTime());
      setOccurrenceTime(localDateTime());
    }
  };

  return <div className="rel-ops__workspace">
    <section className="rel-ops__editor">
      <div className="rel-ops__section-head"><div><p className="reliability-v2__eyebrow">New controlled occurrence</p><h3>Record the operational event once</h3></div><span>Delay is calculated from scheduled and actual departure.</span></div>
      <form className="rel-ops__form" onSubmit={(event) => void submit(event)}>
        <FieldGroup title="Event classification" detail="Choose the operational outcome first. The form only asks for timing that applies to that event.">
          <label>Occurrence type<select value={eventType} onChange={(event) => setEventType(event.target.value)}>
            {Object.keys(EVENT_IMPACT).map((value) => <option key={value} value={value}>{EVENT_LABELS[value]}</option>)}
          </select></label>
          <label>Ops report / event reference<input name="record_number" required maxLength={80} placeholder="e.g. OPS-2026-0148" /></label>
          <label>Reliability significance<select value={severity} onChange={(event) => setSeverity(event.target.value)}><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select><small>Suggested from the event type and delay; confirm before submission.</small></label>
        </FieldGroup>

        <FieldGroup title="Flight identity">
          <AircraftSelect aircraft={aircraft} required />
          <label>Flight number<input name="flight_number" required maxLength={24} placeholder="e.g. F2 101" /></label>
          <label>Origin<input name="origin_station" required maxLength={8} placeholder="NBO" /></label>
          <label>Destination<input name="destination_station" required maxLength={8} placeholder="MBA" /></label>
        </FieldGroup>

        <FieldGroup title="Timing and operational effect" detail={isDelay ? "The portal derives the controlled delay value. Users must not enter the same fact twice." : "Record when the event occurred. Departure times are shown only where they add operational context."}>
          {(isDelay || isCancellation) && <label>Scheduled departure<input type="datetime-local" value={scheduledDeparture} onChange={(event) => setScheduledDeparture(event.target.value)} required /></label>}
          {isDelay && <label>Actual departure<input type="datetime-local" value={actualDeparture} onChange={(event) => setActualDeparture(event.target.value)} required /></label>}
          {!isDelay && <label>{isCancellation ? "Cancellation decision time" : "Occurrence time"}<input type="datetime-local" value={occurrenceTime} onChange={(event) => setOccurrenceTime(event.target.value)} required /></label>}
          {!isDelay && !isCancellation && <label>Actual departure <span className="rel-ops__optional">optional context</span><input type="datetime-local" value={actualDeparture} onChange={(event) => setActualDeparture(event.target.value)} /></label>}
          {isDelay && <output className={`rel-ops__calculated ${timingInvalid ? "is-invalid" : ""}`}>
            <span>Calculated delay</span>
            <strong>{calculatedDelay == null ? "Enter both times" : timingInvalid ? "Actual departure must be later" : `${calculatedDelay} minutes`}</strong>
            <small>Actual departure minus scheduled departure. This value is recalculated and verified by the API.</small>
          </output>}
        </FieldGroup>

        <FieldGroup title="Technical context">
          <label>ATA chapter <span className="rel-ops__optional">optional</span><input name="ata_chapter" maxLength={20} placeholder="e.g. 32" /></label>
          <label className="rel-ops__span-2">Technical cause and operational consequence<textarea name="description" rows={4} required placeholder="State the technical issue, action taken and effect on the flight. Do not repeat the timing fields." /></label>
        </FieldGroup>
        <div className="rel-ops__form-actions"><button className="btn btn-primary" disabled={saving || timingInvalid || (isDelay && calculatedDelay == null)}>Create for approval</button></div>
      </form>
    </section>

    <RegisterSection title="Flight Operations register" count={filtered.length} query={query} onQuery={setQuery} statusFilter={statusFilter} onStatusFilter={setStatusFilter} statuses={["DRAFT", "APPROVED", "CLOSED"]}>
      <table className="reliability-v2__table rel-ops__table rel-ops__table--flight"><thead><tr><th>Event</th><th>Flight</th><th>Timing</th><th>Technical context</th><th>Status</th><th>Action</th></tr></thead><tbody>
        {filtered.map((row) => <tr key={row.id}>
          <td><strong>{row.record_number}</strong><small>{EVENT_LABELS[row.event_type] || row.event_type} · Rev {row.revision}</small></td>
          <td><strong>{row.flight_number}</strong><small>{row.origin_station || "—"} → {row.destination_station || "—"} · {row.aircraft_serial_number}</small></td>
          <td>{row.delay_minutes != null ? <><strong>{row.delay_minutes} min delay</strong><small>{displayDate(row.scheduled_departure_at)} → {displayDate(row.actual_departure_at)}</small></> : <><strong>{displayDate(row.occurred_at)}</strong><small>{row.dispatch_impact || "Operational event"}</small></>}</td>
          <td><strong>{row.ata_chapter ? `ATA ${row.ata_chapter}` : row.severity}</strong><details><summary>View occurrence</summary><p>{row.description}</p></details></td>
          <td><span className={statusClass(row.status)}>{row.status}</span><small>Event {row.canonical_event_id || "not ingested"}</small></td>
          <td><div className="rel-ops__row-actions">{row.status === "DRAFT" && <button className="btn btn-primary" type="button" onClick={() => onAction({ kind: "FLIGHT_APPROVE", row })}>Review & approve</button>}{row.status === "APPROVED" && <button className="btn btn-secondary" type="button" onClick={() => onAction({ kind: "FLIGHT_CLOSE", row })}>Close occurrence</button>}</div></td>
        </tr>)}
        {!filtered.length && <tr><td colSpan={6}>No Flight Operations records match the current filters.</td></tr>}
      </tbody></table>
    </RegisterSection>
  </div>;
}

function DeferralView({ rows, aircraft, run, saving, onAction }: { rows: Deferral[]; aircraft: AircraftRead[]; run: RunMutation; saving: boolean; onAction: (action: ActionRequest) => void }) {
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [repeatUnit, setRepeatUnit] = useState("HOURS");
  const filtered = useMemo(() => rows.filter((row) => {
    const haystack = `${row.deferral_number} ${row.aircraft_serial_number} ${row.defect_reference} ${row.item_reference} ${row.category || ""}`.toLowerCase();
    return (statusFilter === "ALL" || row.status === statusFilter) && haystack.includes(query.toLowerCase());
  }), [query, rows, statusFilter]);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const repeatValue = numberOrNull(data, "repeat_value");
    const repeatMinutes = repeatValue == null ? null : repeatUnit === "DAYS" ? repeatValue * 1440 : repeatUnit === "HOURS" ? repeatValue * 60 : repeatValue;
    const completed = await run(() => mutate(`${BASE}/deferrals`, {
      deferral_number: formValue(data, "deferral_number"),
      deferral_type: formValue(data, "deferral_type"),
      aircraft_serial_number: formValue(data, "aircraft_serial_number"),
      defect_reference: formValue(data, "defect_reference"),
      item_reference: formValue(data, "item_reference"),
      category: nullable(data, "category"),
      applied_at: iso(formValue(data, "applied_at")),
      expires_at: iso(formValue(data, "expires_at")),
      control_basis: formValue(data, "control_basis"),
      operational_procedure: nullable(data, "operational_procedure"),
      maintenance_procedure: nullable(data, "maintenance_procedure"),
      repetitive_inspection_minutes: repeatMinutes,
      flight_number: nullable(data, "flight_number"),
      ata_chapter: nullable(data, "ata_chapter"),
      description: formValue(data, "description"),
      severity: formValue(data, "severity"),
    }), "MEL/CDL deferral created for approval.");
    if (completed) form.reset();
  };

  return <div className="rel-ops__workspace">
    <section className="rel-ops__editor">
      <div className="rel-ops__section-head"><div><p className="reliability-v2__eyebrow">New controlled deferral</p><h3>Apply the approved MEL / CDL control</h3></div><span>Expiry is taken from the approved control basis, not guessed from a generic category.</span></div>
      <form className="rel-ops__form" onSubmit={(event) => void submit(event)}>
        <FieldGroup title="Defect and approved item">
          <label>Deferral number<input name="deferral_number" required maxLength={80} /></label>
          <label>Control type<select name="deferral_type"><option>MEL</option><option>CDL</option></select></label>
          <AircraftSelect aircraft={aircraft} required />
          <label>Defect / tech-log reference<input name="defect_reference" required /></label>
          <label>MEL / CDL item reference<input name="item_reference" required /></label>
          <label>Category<select name="category" defaultValue=""><option value="">Not category-controlled</option><option>A</option><option>B</option><option>C</option><option>D</option><option value="OTHER">Other approved basis</option></select></label>
        </FieldGroup>

        <FieldGroup title="Application and expiry" detail="Enter the exact dates established by the operator's approved MEL/CDL. Category A and local approval rules may not follow generic intervals.">
          <label>Applied at<input type="datetime-local" name="applied_at" defaultValue={localDateTime()} required /></label>
          <label>Approved expiry<input type="datetime-local" name="expires_at" required /></label>
          <label>Associated flight <span className="rel-ops__optional">optional</span><input name="flight_number" /></label>
          <label>ATA chapter <span className="rel-ops__optional">optional</span><input name="ata_chapter" /></label>
          <label>Reliability significance<select name="severity" defaultValue="MEDIUM"><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select></label>
          <div className="rel-ops__compound-field"><label>Repeat inspection <span className="rel-ops__optional">optional</span><input type="number" min="1" name="repeat_value" /></label><label>Unit<select value={repeatUnit} onChange={(event) => setRepeatUnit(event.target.value)}><option>MINUTES</option><option>HOURS</option><option>DAYS</option></select></label></div>
        </FieldGroup>

        <FieldGroup title="Approved control and procedures">
          <label className="rel-ops__span-2">Control basis<textarea name="control_basis" rows={3} required placeholder="Approved MEL/CDL revision, item, provisos and authorisation basis." /></label>
          <label>Operational procedure<textarea name="operational_procedure" rows={3} /></label>
          <label>Maintenance procedure<textarea name="maintenance_procedure" rows={3} /></label>
          <label className="rel-ops__span-2">Defect description<textarea name="description" rows={3} required /></label>
        </FieldGroup>
        <div className="rel-ops__form-actions"><button className="btn btn-primary" disabled={saving}>Create for approval</button></div>
      </form>
    </section>

    <RegisterSection title="MEL / CDL register" count={filtered.length} query={query} onQuery={setQuery} statusFilter={statusFilter} onStatusFilter={setStatusFilter} statuses={["DRAFT", "OPEN", "EXTENDED", "EXPIRED", "CLOSED"]}>
      <table className="reliability-v2__table rel-ops__table"><thead><tr><th>Deferral</th><th>Aircraft / defect</th><th>Control window</th><th>Status</th><th>Action</th></tr></thead><tbody>
        {filtered.map((row) => <tr key={row.id}>
          <td><strong>{row.deferral_number}</strong><small>{row.deferral_type} {row.category ? `Category ${row.category}` : ""} · Rev {row.revision}</small></td>
          <td><strong>{row.aircraft_serial_number}</strong><small>{row.item_reference} · {row.defect_reference}</small><details><summary>View defect</summary><p>{row.description}</p></details></td>
          <td><strong>{displayDate(row.expires_at)}</strong><small className={new Date(row.expires_at).getTime() < Date.now() && row.status !== "CLOSED" ? "rel-ops__text-danger" : ""}>{relativeExpiry(row.expires_at)}</small><small>Applied {displayDate(row.applied_at)}</small></td>
          <td><span className={statusClass(row.status)}>{row.status}</span><small>Event {row.canonical_event_id || "not ingested"}</small></td>
          <td><div className="rel-ops__row-actions">{row.status === "DRAFT" && <button className="btn btn-primary" type="button" onClick={() => onAction({ kind: "DEFERRAL_APPROVE", row })}>Review & approve</button>}{["OPEN", "EXTENDED"].includes(row.status) && <button className="btn btn-secondary" type="button" onClick={() => onAction({ kind: "DEFERRAL_EXTEND", row })}>Extend</button>}{["OPEN", "EXTENDED", "EXPIRED"].includes(row.status) && <button className="btn btn-secondary" type="button" onClick={() => onAction({ kind: "DEFERRAL_CLOSE", row })}>Close</button>}</div></td>
        </tr>)}
        {!filtered.length && <tr><td colSpan={5}>No deferrals match the current filters.</td></tr>}
      </tbody></table>
    </RegisterSection>
  </div>;
}

function ShopView({ rows, aircraft, run, saving, onAction }: { rows: ShopFinding[]; aircraft: AircraftRead[]; run: RunMutation; saving: boolean; onAction: (action: ActionRequest) => void }) {
  const [findingType, setFindingType] = useState("SHOP_FINDING");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const filtered = useMemo(() => rows.filter((row) => {
    const haystack = `${row.shop_order_reference} ${row.part_number} ${row.component_serial_number} ${row.aircraft_serial_number || ""} ${row.event_type}`.toLowerCase();
    return (statusFilter === "ALL" || row.status === statusFilter) && haystack.includes(query.toLowerCase());
  }), [query, rows, statusFilter]);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const confirmed = findingType === "NO_FAULT_FOUND" ? false : formValue(data, "confirmed_failure") === "true";
    const completed = await run(() => mutate(`${BASE}/component-shop`, {
      shop_order_reference: formValue(data, "shop_order_reference"),
      event_type: findingType,
      component_id: null,
      aircraft_serial_number: nullable(data, "aircraft_serial_number"),
      part_number: formValue(data, "part_number"),
      component_serial_number: formValue(data, "component_serial_number"),
      received_at: iso(formValue(data, "received_at")),
      inspected_at: iso(formValue(data, "inspected_at")),
      ata_chapter: nullable(data, "ata_chapter"),
      confirmed_failure: confirmed,
      test_result: formValue(data, "test_result"),
      disposition: formValue(data, "disposition"),
      release_reference: null,
      description: formValue(data, "description"),
      severity: formValue(data, "severity"),
    }), "Component-shop finding created for approval.");
    if (completed) form.reset();
  };

  return <div className="rel-ops__workspace">
    <section className="rel-ops__editor">
      <div className="rel-ops__section-head"><div><p className="reliability-v2__eyebrow">New shop outcome</p><h3>Record the test conclusion, not an assumed failure</h3></div><span>Release data is captured later, when the component is actually released.</span></div>
      <form className="rel-ops__form" onSubmit={(event) => void submit(event)}>
        <FieldGroup title="Component identity">
          <label>Shop order reference<input name="shop_order_reference" required /></label>
          <label>Outcome<select value={findingType} onChange={(event) => setFindingType(event.target.value)}><option value="SHOP_FINDING">Confirmed shop finding</option><option value="NO_FAULT_FOUND">No fault found</option></select></label>
          <AircraftSelect aircraft={aircraft} allowFleet label="Originating aircraft" />
          <label>Part number<input name="part_number" required /></label>
          <label>Serial number<input name="component_serial_number" required /></label>
          <label>ATA chapter <span className="rel-ops__optional">optional</span><input name="ata_chapter" /></label>
        </FieldGroup>

        <FieldGroup title="Inspection chronology">
          <label>Received at<input type="datetime-local" name="received_at" defaultValue={localDateTime(-2)} required /></label>
          <label>Inspection completed<input type="datetime-local" name="inspected_at" defaultValue={localDateTime()} required /></label>
          {findingType === "SHOP_FINDING" && <label>Failure confirmed<select name="confirmed_failure" defaultValue="true" required><option value="true">Yes — test evidence confirms failure</option><option value="false">No — finding did not confirm reported failure</option></select></label>}
          {findingType === "NO_FAULT_FOUND" && <div className="rel-ops__calculated"><span>Failure decision</span><strong>No confirmed failure</strong><small>NFF records are stored explicitly as confirmed_failure=false.</small></div>}
          <label>Reliability significance<select name="severity" defaultValue="MEDIUM"><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select></label>
        </FieldGroup>

        <FieldGroup title="Approved technical conclusion">
          <label>Test result<textarea name="test_result" rows={4} required /></label>
          <label>Disposition<textarea name="disposition" rows={4} required placeholder="Repair, overhaul, scrap, return serviceable, further investigation…" /></label>
          <label className="rel-ops__span-2">Finding narrative<textarea name="description" rows={3} required /></label>
        </FieldGroup>
        <div className="rel-ops__form-actions"><button className="btn btn-primary" disabled={saving}>Create for approval</button></div>
      </form>
    </section>

    <RegisterSection title="Component-shop register" count={filtered.length} query={query} onQuery={setQuery} statusFilter={statusFilter} onStatusFilter={setStatusFilter} statuses={["DRAFT", "APPROVED", "RELEASED"]}>
      <table className="reliability-v2__table rel-ops__table"><thead><tr><th>Shop order</th><th>Component</th><th>Conclusion</th><th>Disposition</th><th>Status</th><th>Action</th></tr></thead><tbody>
        {filtered.map((row) => <tr key={row.id}>
          <td><strong>{row.shop_order_reference}</strong><small>Rev {row.revision}{row.aircraft_serial_number ? ` · ${row.aircraft_serial_number}` : ""}</small></td>
          <td><strong>{row.part_number}</strong><small>S/N {row.component_serial_number}</small></td>
          <td><strong>{EVENT_LABELS[row.event_type] || row.event_type}</strong><small>{row.confirmed_failure == null ? "Decision not recorded" : row.confirmed_failure ? "Failure confirmed" : "Failure not confirmed"}</small></td>
          <td>{row.disposition}</td>
          <td><span className={statusClass(row.status)}>{row.status}</span><small>Event {row.canonical_event_id || "not ingested"}</small></td>
          <td><div className="rel-ops__row-actions">{row.status === "DRAFT" && <button className="btn btn-primary" type="button" onClick={() => onAction({ kind: "SHOP_APPROVE", row })}>Review & approve</button>}{row.status === "APPROVED" && <button className="btn btn-secondary" type="button" onClick={() => onAction({ kind: "SHOP_RELEASE", row })}>Record release</button>}</div></td>
        </tr>)}
        {!filtered.length && <tr><td colSpan={6}>No shop findings match the current filters.</td></tr>}
      </tbody></table>
    </RegisterSection>
  </div>;
}

function SmsView({ rows, aircraft, run, saving, onAction }: { rows: SmsOccurrence[]; aircraft: AircraftRead[]; run: RunMutation; saving: boolean; onAction: (action: ActionRequest) => void }) {
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const filtered = useMemo(() => rows.filter((row) => {
    const haystack = `${row.sms_reference} ${row.aircraft_serial_number || ""} ${row.risk_classification} ${row.description}`.toLowerCase();
    return (statusFilter === "ALL" || row.status === statusFilter) && haystack.includes(query.toLowerCase());
  }), [query, rows, statusFilter]);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const completed = await run(() => mutate(`${BASE}/sms`, {
      sms_reference: formValue(data, "sms_reference"),
      occurred_at: iso(formValue(data, "occurred_at")),
      aircraft_serial_number: nullable(data, "aircraft_serial_number"),
      hazard_reference: nullable(data, "hazard_reference"),
      risk_classification: formValue(data, "risk_classification"),
      investigation_status: formValue(data, "investigation_status"),
      ata_chapter: nullable(data, "ata_chapter"),
      description: formValue(data, "description"),
      severity: formValue(data, "severity"),
    }), "SMS source reference added to the Reliability assessment queue.");
    if (completed) form.reset();
  };

  return <div className="rel-ops__workspace">
    <section className="rel-ops__queue-intro">
      <div><p className="reliability-v2__eyebrow">Assessment queue</p><h3>Decide technical relevance; do not recreate the safety investigation</h3><p>SMS remains the owner of the occurrence and investigation. Reliability records only the accountable relevance decision and link reason.</p></div>
      <details className="rel-ops__fallback-entry"><summary>Add a missing SMS source reference</summary>
        <form className="rel-ops__form rel-ops__form--compact" onSubmit={(event) => void submit(event)}>
          <FieldGroup title="Source occurrence">
            <label>SMS reference<input name="sms_reference" required /></label>
            <label>Occurred at<input type="datetime-local" name="occurred_at" defaultValue={localDateTime()} required /></label>
            <AircraftSelect aircraft={aircraft} allowFleet />
            <label>Hazard reference<input name="hazard_reference" /></label>
            <label>Risk classification<input name="risk_classification" required /></label>
            <label>Investigation status<select name="investigation_status" defaultValue="OPEN"><option>OPEN</option><option>UNDER_INVESTIGATION</option><option>ACTIONS_OPEN</option><option>CLOSED</option></select></label>
            <label>ATA chapter<input name="ata_chapter" /></label>
            <label>Reliability significance<select name="severity" defaultValue="MEDIUM"><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select></label>
            <label className="rel-ops__span-2">Occurrence summary<textarea name="description" rows={3} required /></label>
          </FieldGroup>
          <div className="rel-ops__form-actions"><button className="btn btn-secondary" disabled={saving}>Add source reference</button></div>
        </form>
      </details>
    </section>

    <RegisterSection title="SMS relevance queue" count={filtered.length} query={query} onQuery={setQuery} statusFilter={statusFilter} onStatusFilter={setStatusFilter} statuses={["DRAFT", "ASSESSED"]}>
      <table className="reliability-v2__table rel-ops__table"><thead><tr><th>Occurrence</th><th>Risk / investigation</th><th>Technical context</th><th>Reliability decision</th><th>Action</th></tr></thead><tbody>
        {filtered.map((row) => <tr key={row.id}>
          <td><strong>{row.sms_reference}</strong><small>{displayDate(row.occurred_at)} · {row.aircraft_serial_number || "Fleet"}</small></td>
          <td><strong>{row.risk_classification}</strong><small>{row.investigation_status}</small></td>
          <td><details><summary>View source summary</summary><p>{row.description}</p></details></td>
          <td>{row.status === "DRAFT" ? <span className={statusClass("PENDING")}>Awaiting assessment</span> : <><strong>{row.reliability_relevant ? "Linked to Reliability" : "Not Reliability-relevant"}</strong><small>{row.reliability_link_reason || "Decision recorded without canonical event."}</small><small>Event {row.canonical_event_id || "not created"}</small></>}</td>
          <td><button className="btn btn-secondary" type="button" onClick={() => onAction({ kind: "SMS_ASSESS", row })}>{row.status === "DRAFT" ? "Assess relevance" : "Revise assessment"}</button></td>
        </tr>)}
        {!filtered.length && <tr><td colSpan={5}>No SMS occurrences match the current filters.</td></tr>}
      </tbody></table>
    </RegisterSection>
  </div>;
}

function QmsLinkView({ findings, aircraft, run, saving }: { findings: QMSFindingOut[]; aircraft: AircraftRead[]; run: RunMutation; saving: boolean }) {
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const filtered = useMemo(() => findings.filter((finding) => {
    const haystack = `${finding.finding_ref || ""} ${finding.description} ${finding.requirement_ref || ""} ${finding.severity} ${finding.level}`.toLowerCase();
    return haystack.includes(query.toLowerCase());
  }), [findings, query]);
  const selected = findings.find((finding) => finding.id === selectedId) || null;

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const completed = await run(() => mutate(`/reliability/authoritative-sources/qms/findings/${encodeURIComponent(selected.id)}/link`, {
      event_type: formValue(data, "event_type"),
      reliability_link_reason: formValue(data, "reliability_link_reason"),
      aircraft_serial_number: nullable(data, "aircraft_serial_number"),
      ata_chapter: nullable(data, "ata_chapter"),
      severity: nullable(data, "severity"),
    }), "QMS finding linked with its controlled objective evidence and provenance.");
    if (completed) {
      form.reset();
      setSelectedId("");
    }
  };

  return <div className="rel-ops__workspace rel-ops__qms-layout">
    <section className="rel-ops__selection-pane">
      <div className="rel-ops__section-head"><div><p className="reliability-v2__eyebrow">Controlled QMS findings</p><h3>Select the finding to link</h3></div><span>{filtered.length} shown</span></div>
      <label className="rel-ops__search"><span>Search findings</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Reference, requirement, evidence or description" /></label>
      <div className="rel-ops__finding-list">
        {filtered.map((finding) => <button key={finding.id} type="button" className={selectedId === finding.id ? "is-selected" : ""} onClick={() => setSelectedId(finding.id)}>
          <span><strong>{finding.finding_ref || finding.id}</strong><small>{finding.finding_type} · {finding.level} · {finding.severity}</small></span>
          <p>{finding.description}</p>
          <small>{finding.requirement_ref || "No requirement reference"}{finding.closed_at ? " · Closed" : " · Open"}</small>
        </button>)}
        {!filtered.length && <p className="reliability-v2__empty">No QMS findings match the search.</p>}
      </div>
    </section>

    <section className="rel-ops__link-pane">
      <div className="rel-ops__section-head"><div><p className="reliability-v2__eyebrow">Reliability linkage</p><h3>{selected ? selected.finding_ref || "Selected finding" : "Choose a QMS finding"}</h3></div></div>
      {!selected && <p className="rel-ops__placeholder">Select a finding from the controlled register. The portal will carry its description and objective evidence into the provenance chain; users do not retype them.</p>}
      {selected && <>
        <dl className="rel-ops__selected-evidence">
          <div><dt>Requirement</dt><dd>{selected.requirement_ref || "—"}</dd></div>
          <div><dt>Classification</dt><dd>{selected.finding_type} · {selected.level} · {selected.severity}</dd></div>
          <div><dt>Description</dt><dd>{selected.description}</dd></div>
          <div><dt>Objective evidence</dt><dd>{selected.objective_evidence || "No objective evidence text recorded."}</dd></div>
        </dl>
        <form className="rel-ops__form" onSubmit={(event) => void submit(event)}>
          <FieldGroup title="Technical classification">
            <label>Reliability event type<select name="event_type"><option>MAINTENANCE_ERROR</option><option>SUPPLIER_ESCAPE</option><option>SAFETY_EVENT</option><option>OTHER</option></select></label>
            <AircraftSelect aircraft={aircraft} allowFleet />
            <label>ATA chapter<input name="ata_chapter" /></label>
            <label>Severity override<select name="severity"><option value="">Use QMS classification</option><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select></label>
            <label className="rel-ops__span-2">Why this finding belongs in Reliability analysis<textarea name="reliability_link_reason" rows={4} required placeholder="State the technical failure, recurrence, maintenance or supplier mechanism that requires Reliability trending." /></label>
          </FieldGroup>
          <div className="rel-ops__form-actions"><button className="btn btn-primary" disabled={saving}>Link selected finding</button></div>
        </form>
      </>}
    </section>
  </div>;
}

const WORKBOOK_FIELDS: Array<{ key: string; label: string; required?: boolean }> = [
  { key: "event_type", label: "Event type", required: true },
  { key: "occurred_at", label: "Occurrence date/time", required: true },
  { key: "description", label: "Description", required: true },
  { key: "aircraft_serial_number", label: "Aircraft serial" },
  { key: "ata_chapter", label: "ATA chapter" },
  { key: "reference_code", label: "Source reference" },
  { key: "severity", label: "Severity" },
];

function WorkbookView({ imports, rows, selected, onSelect, run, saving, onAction }: { imports: WorkbookImport[]; rows: WorkbookRow[]; selected: WorkbookImport | null; onSelect: (id: string) => Promise<void>; run: RunMutation; saving: boolean; onAction: (action: ActionRequest) => void }) {
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const sourceColumns = useMemo(() => Object.keys(rows[0]?.raw_json || {}), [rows]);
  const filteredRows = useMemo(() => rows.filter((row) => {
    const haystack = `${row.sheet_name} ${row.source_row_number} ${JSON.stringify(row.raw_json)} ${JSON.stringify(row.mapped_json)}`.toLowerCase();
    return (statusFilter === "ALL" || row.status === statusFilter) && haystack.includes(query.toLowerCase());
  }), [query, rows, statusFilter]);
  const unresolved = rows.filter((row) => ["PENDING", "VALID", "INVALID"].includes(row.status)).length;

  const upload = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const completed = await run(() => mutate(`${BASE}/workbooks/upload`, new FormData(form)), "Workbook uploaded and source rows preserved.");
    if (completed) form.reset();
  };

  const map = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected) return;
    const data = new FormData(event.currentTarget);
    const mapping: Record<string, string> = {};
    const defaults: Record<string, unknown> = {};
    WORKBOOK_FIELDS.forEach(({ key }) => {
      const column = formValue(data, `mapping_${key}`);
      const defaultValue = formValue(data, `default_${key}`);
      if (column) mapping[key] = column;
      else if (defaultValue) defaults[key] = defaultValue;
    });
    await run(() => mutate(`${BASE}/workbooks/${selected.id}/map`, { mapping, defaults }), "Workbook mapped and validated at row level.");
  };

  return <div className="rel-ops__workspace">
    <section className="rel-ops__migration-head">
      <form className="rel-ops__upload" onSubmit={(event) => void upload(event)}>
        <div><p className="reliability-v2__eyebrow">Step 1</p><h3>Upload the original source</h3><p>The file, hash, sheets and raw rows are preserved before transformation.</p></div>
        <label>Workbook (.xlsx or .csv)<input type="file" name="file" accept=".xlsx,.csv" required /></label>
        <label>Header row<input type="number" name="header_row" min="1" max="100" defaultValue="1" /></label>
        <button className="btn btn-primary" disabled={saving}>Upload workbook</button>
      </form>
      <div className="rel-ops__import-list">
        <div className="rel-ops__section-head"><div><p className="reliability-v2__eyebrow">Imports</p><h3>Select a workbook</h3></div><span>{imports.length} registered</span></div>
        {imports.map((item) => <button key={item.id} type="button" className={selected?.id === item.id ? "is-selected" : ""} onClick={() => void onSelect(item.id)}>
          <span><strong>{item.original_filename}</strong><small>Rev {item.revision} · {displayDate(item.created_at)}</small></span>
          <span className={statusClass(item.status)}>{item.status}</span>
          <small>{item.approved_rows}/{item.total_rows} approved · {item.ingested_rows} ingested</small>
        </button>)}
        {!imports.length && <p className="reliability-v2__empty">No historical workbooks are registered.</p>}
      </div>
    </section>

    {selected && <>
      <section className="rel-ops__mapping">
        <div className="rel-ops__section-head"><div><p className="reliability-v2__eyebrow">Step 2</p><h3>Map source columns to canonical fields</h3></div><span>{sourceColumns.length} source columns detected</span></div>
        {!sourceColumns.length && <p className="rel-ops__placeholder">No row columns are available. Check the selected header row or upload a workbook containing visible data rows.</p>}
        {!!sourceColumns.length && <form className="rel-ops__mapping-form" onSubmit={(event) => void map(event)}>
          <div className="rel-ops__mapping-header"><span>Canonical field</span><span>Source column</span><span>Static default when no column applies</span></div>
          {WORKBOOK_FIELDS.map((field) => <div className="rel-ops__mapping-row" key={field.key}>
            <label htmlFor={`mapping_${field.key}`}>{field.label}{field.required ? " *" : ""}</label>
            <select id={`mapping_${field.key}`} name={`mapping_${field.key}`} defaultValue=""><option value="">Do not map from a column</option>{sourceColumns.map((column) => <option key={column} value={column}>{column}</option>)}</select>
            <input name={`default_${field.key}`} placeholder={field.key === "event_type" ? "e.g. TECHNICAL_DELAY" : field.key === "severity" ? "e.g. MEDIUM" : "Optional default"} />
          </div>)}
          <p className="rel-ops__form-note">Required fields must be supplied by either a source column or a static default. Row-level validation runs before any approval.</p>
          <div className="rel-ops__form-actions"><button className="btn btn-primary" disabled={saving}>Map and validate rows</button></div>
        </form>}
      </section>

      <section className="rel-ops__reconciliation">
        <div className="rel-ops__section-head">
          <div><p className="reliability-v2__eyebrow">Steps 3–5</p><h3>Reconcile, approve and ingest</h3><p>{unresolved ? `${unresolved} rows still require an approve or reject decision.` : "Every mapped row has a recorded decision."}</p></div>
          <div className="rel-ops__row-actions">
            {selected.status !== "APPROVED" && selected.status !== "INGESTED" && <button className="btn btn-secondary" type="button" disabled={saving || unresolved > 0 || selected.approved_rows === 0} onClick={() => onAction({ kind: "WORKBOOK_APPROVE", row: selected })}>Approve reconciled workbook</button>}
            {selected.status === "APPROVED" && <button className="btn btn-primary" type="button" disabled={saving} onClick={() => onAction({ kind: "WORKBOOK_INGEST", row: selected })}>Ingest approved rows</button>}
          </div>
        </div>
        <div className="rel-ops__stage-line" aria-label="Workbook workflow">
          {workbookStages(selected.status).map((stage) => <span key={stage.label} className={stage.state}>{stage.label}</span>)}
        </div>
        <RegisterSection title={`${selected.original_filename} rows`} count={filteredRows.length} query={query} onQuery={setQuery} statusFilter={statusFilter} onStatusFilter={setStatusFilter} statuses={["PENDING", "VALID", "INVALID", "APPROVED", "REJECTED", "INGESTED"]} embedded>
          <table className="reliability-v2__table rel-ops__table rel-ops__table--workbook"><thead><tr><th>Source row</th><th>Mapped occurrence</th><th>Validation</th><th>Decision</th></tr></thead><tbody>
            {filteredRows.map((row) => <tr key={row.id}>
              <td><strong>{row.sheet_name} · row {row.source_row_number}</strong><details><summary>View raw values</summary><dl className="rel-ops__raw-values">{Object.entries(row.raw_json).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{fieldText(value)}</dd></div>)}</dl></details></td>
              <td><strong>{fieldText(row.mapped_json.event_type)}</strong><small>{fieldText(row.mapped_json.occurred_at)} · {fieldText(row.mapped_json.aircraft_serial_number)}</small><p>{fieldText(row.mapped_json.description)}</p></td>
              <td><span className={statusClass(row.status)}>{row.status}</span>{row.validation_errors_json.length ? <ul className="rel-ops__validation-list">{row.validation_errors_json.map((issue, index) => <li key={`${row.id}-${index}`}>{fieldText(issue)}</li>)}</ul> : <small>Canonical validation passed.</small>}</td>
              <td><div className="rel-ops__row-actions"><button type="button" className="btn btn-primary" disabled={!['VALID', 'APPROVED'].includes(row.status)} onClick={() => onAction({ kind: "WORKBOOK_ROW_APPROVE", workbook: selected, row })}>Approve</button><button type="button" className="btn btn-secondary" disabled={row.status === "INGESTED"} onClick={() => onAction({ kind: "WORKBOOK_ROW_REJECT", workbook: selected, row })}>Reject</button></div>{row.decision_note && <small>{row.decision_note}</small>}{row.canonical_event_id && <small>Event {row.canonical_event_id}</small>}</td>
            </tr>)}
            {!filteredRows.length && <tr><td colSpan={4}>No workbook rows match the current filters.</td></tr>}
          </tbody></table>
        </RegisterSection>
      </section>
    </>}
  </div>;
}

function workbookStages(status: string): Array<{ label: string; state: string }> {
  const order = ["UPLOADED", "MAPPED", "IN_REVIEW", "APPROVED", "INGESTED"];
  const aliases: Record<string, string> = { UPLOADED: "Uploaded", MAPPED: "Mapped", IN_REVIEW: "Reconciled", APPROVED: "Approved", INGESTED: "Ingested" };
  const current = Math.max(order.indexOf(status), 0);
  return order.map((item, index) => ({ label: aliases[item], state: index < current ? "is-complete" : index === current ? "is-current" : "" }));
}

function RegisterSection({ title, count, query, onQuery, statusFilter, onStatusFilter, statuses, children, embedded = false }: { title: string; count: number; query: string; onQuery: (value: string) => void; statusFilter: string; onStatusFilter: (value: string) => void; statuses: string[]; children: React.ReactNode; embedded?: boolean }) {
  return <section className={embedded ? "rel-ops__register rel-ops__register--embedded" : "rel-ops__register"}>
    <div className="rel-ops__register-head">
      <div><h3>{title}</h3><span>{count} records shown</span></div>
      <div className="rel-ops__filters">
        <label><span>Search</span><input type="search" value={query} onChange={(event) => onQuery(event.target.value)} placeholder="Reference, aircraft or description" /></label>
        <label><span>Status</span><select value={statusFilter} onChange={(event) => onStatusFilter(event.target.value)}><option value="ALL">All statuses</option>{statuses.map((status) => <option key={status}>{status}</option>)}</select></label>
      </div>
    </div>
    <div className="reliability-v2__table-wrap rel-ops__table-wrap">{children}</div>
  </section>;
}

function ActionDialog({ action, run, saving, onClose }: { action: ActionRequest; run: RunMutation; saving: boolean; onClose: () => void }) {
  const [smsRelevant, setSmsRelevant] = useState(action.kind === "SMS_ASSESS" ? action.row.reliability_relevant : true);
  const descriptor = actionDescriptor(action);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    let completed = false;
    if (action.kind === "FLIGHT_APPROVE") completed = await run(() => mutate(`${BASE}/flight-operations/${action.row.id}/approve`), "Flight Operations occurrence approved and ingested.");
    if (action.kind === "FLIGHT_CLOSE") {
      const evidenceReference = formValue(data, "evidence_reference");
      completed = await run(() => mutate(`${BASE}/flight-operations/${action.row.id}/close`, {
        note: formValue(data, "note"),
        evidence: evidenceReference ? [{ reference: evidenceReference, description: formValue(data, "evidence_description") }] : [],
      }), "Flight Operations occurrence closed with controlled evidence.");
    }
    if (action.kind === "DEFERRAL_APPROVE") completed = await run(() => mutate(`${BASE}/deferrals/${action.row.id}/approve`), "Deferral approved and ingested.");
    if (action.kind === "DEFERRAL_EXTEND") completed = await run(() => mutate(`${BASE}/deferrals/${action.row.id}/extend`, {
      new_expires_at: iso(formValue(data, "new_expires_at")),
      reason: formValue(data, "reason"),
      approval_reference: formValue(data, "approval_reference"),
    }), "Deferral extension recorded and ingested.");
    if (action.kind === "DEFERRAL_CLOSE") {
      const evidenceReference = formValue(data, "evidence_reference");
      completed = await run(() => mutate(`${BASE}/deferrals/${action.row.id}/close`, {
        note: formValue(data, "note"),
        evidence: evidenceReference ? [{ reference: evidenceReference, description: formValue(data, "evidence_description") }] : [],
      }), "Deferral closed with rectification evidence.");
    }
    if (action.kind === "SHOP_APPROVE") completed = await run(() => mutate(`${BASE}/component-shop/${action.row.id}/approve`), "Shop finding approved and ingested.");
    if (action.kind === "SHOP_RELEASE") completed = await run(() => mutate(`${BASE}/component-shop/${action.row.id}/release`, {
      release_reference: formValue(data, "release_reference"),
      note: formValue(data, "note"),
    }), "Component-shop release recorded and ingested.");
    if (action.kind === "SMS_ASSESS") completed = await run(() => mutate(`${BASE}/sms/${action.row.id}/assess`, {
      reliability_relevant: smsRelevant,
      reliability_link_reason: smsRelevant ? formValue(data, "reliability_link_reason") : null,
      investigation_status: formValue(data, "investigation_status"),
    }), smsRelevant ? "SMS occurrence linked to Reliability with an accountable reason." : "SMS occurrence assessed as not Reliability-relevant.");
    if (action.kind === "WORKBOOK_APPROVE") completed = await run(() => mutate(`${BASE}/workbooks/${action.row.id}/approve`), "Workbook reconciliation approved.");
    if (action.kind === "WORKBOOK_INGEST") completed = await run(() => mutate(`${BASE}/workbooks/${action.row.id}/ingest`), "Approved workbook rows ingested into canonical Reliability evidence.");
    if (action.kind === "WORKBOOK_ROW_APPROVE") completed = await run(() => mutate(`${BASE}/workbooks/${action.workbook.id}/rows/${action.row.id}/decision`, { decision: "APPROVE", note: formValue(data, "note") }), "Workbook row approved.");
    if (action.kind === "WORKBOOK_ROW_REJECT") completed = await run(() => mutate(`${BASE}/workbooks/${action.workbook.id}/rows/${action.row.id}/decision`, { decision: "REJECT", note: formValue(data, "note") }), "Workbook row rejected with reason.");
    if (completed) onClose();
  };

  return <div className="rel-ops__dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !saving) onClose(); }}>
    <section className="rel-ops__dialog" role="dialog" aria-modal="true" aria-labelledby="rel-ops-dialog-title">
      <header><div><p className="reliability-v2__eyebrow">Controlled lifecycle action</p><h3 id="rel-ops-dialog-title">{descriptor.title}</h3><p>{descriptor.detail}</p></div><button type="button" className="rel-ops__dialog-close" onClick={onClose} disabled={saving} aria-label="Close dialog">×</button></header>
      <form className="rel-ops__dialog-form" onSubmit={(event) => void submit(event)}>
        <ActionFields action={action} smsRelevant={smsRelevant} onSmsRelevant={setSmsRelevant} />
        <footer><button type="button" className="btn btn-secondary" onClick={onClose} disabled={saving}>Cancel</button><button type="submit" className="btn btn-primary" disabled={saving}>{saving ? "Saving…" : descriptor.confirmLabel}</button></footer>
      </form>
    </section>
  </div>;
}

function actionDescriptor(action: ActionRequest): { title: string; detail: string; confirmLabel: string } {
  if (action.kind === "FLIGHT_APPROVE") return { title: `Approve ${action.row.record_number}`, detail: "Confirm the flight identity, calculated timing and technical narrative. Approval creates the canonical occurrence.", confirmLabel: "Approve occurrence" };
  if (action.kind === "FLIGHT_CLOSE") return { title: `Close ${action.row.record_number}`, detail: "Record the technical resolution and supporting reference. Closure creates a new controlled revision.", confirmLabel: "Close occurrence" };
  if (action.kind === "DEFERRAL_APPROVE") return { title: `Approve ${action.row.deferral_number}`, detail: "Confirm the approved item, application time and exact expiry before opening the deferral lifecycle.", confirmLabel: "Approve deferral" };
  if (action.kind === "DEFERRAL_EXTEND") return { title: `Extend ${action.row.deferral_number}`, detail: `Current expiry: ${displayDate(action.row.expires_at)}. The new expiry requires a reason and approval reference.`, confirmLabel: "Record extension" };
  if (action.kind === "DEFERRAL_CLOSE") return { title: `Close ${action.row.deferral_number}`, detail: "Record rectification and release evidence. Do not close a deferral from a bare confirmation prompt.", confirmLabel: "Close deferral" };
  if (action.kind === "SHOP_APPROVE") return { title: `Approve ${action.row.shop_order_reference}`, detail: "Confirm the test result, failure decision and disposition before canonical ingestion.", confirmLabel: "Approve finding" };
  if (action.kind === "SHOP_RELEASE") return { title: `Release ${action.row.shop_order_reference}`, detail: "Add the actual release reference and release note. This data belongs to the release action, not the initial finding.", confirmLabel: "Record release" };
  if (action.kind === "SMS_ASSESS") return { title: `Assess ${action.row.sms_reference}`, detail: "Decide whether a technical mechanism requires Reliability trending. The safety investigation remains in SMS.", confirmLabel: "Save assessment" };
  if (action.kind === "WORKBOOK_APPROVE") return { title: `Approve ${action.row.original_filename}`, detail: "Every source row must already have an explicit decision and at least one validated row must be approved.", confirmLabel: "Approve workbook" };
  if (action.kind === "WORKBOOK_INGEST") return { title: `Ingest ${action.row.original_filename}`, detail: `Only the ${action.row.approved_rows} approved rows will create canonical Reliability events.`, confirmLabel: "Ingest approved rows" };
  if (action.kind === "WORKBOOK_ROW_APPROVE") return { title: `Approve row ${action.row.source_row_number}`, detail: "Record why the mapped values were accepted against the preserved source workbook.", confirmLabel: "Approve row" };
  return { title: `Reject row ${action.row.source_row_number}`, detail: "Record the specific reason this source row must not enter canonical Reliability evidence.", confirmLabel: "Reject row" };
}

function ActionFields({ action, smsRelevant, onSmsRelevant }: { action: ActionRequest; smsRelevant: boolean; onSmsRelevant: (value: boolean) => void }) {
  if (["FLIGHT_APPROVE", "DEFERRAL_APPROVE", "SHOP_APPROVE", "WORKBOOK_APPROVE", "WORKBOOK_INGEST"].includes(action.kind)) {
    return <div className="rel-ops__confirmation"><strong>Review completed</strong><p>This action is revision controlled and attributed to the current user.</p></div>;
  }
  if (action.kind === "FLIGHT_CLOSE") return <>
    <label>Resolution / closure note<textarea name="note" rows={4} required minLength={5} /></label>
    <label>Evidence reference <span className="rel-ops__optional">optional</span><input name="evidence_reference" placeholder="Work order, tech log, report or release reference" /></label>
    <label>Evidence description <span className="rel-ops__optional">optional</span><textarea name="evidence_description" rows={2} /></label>
  </>;
  if (action.kind === "DEFERRAL_EXTEND") return <>
    <label>New approved expiry<input type="datetime-local" name="new_expires_at" defaultValue={toLocalInput(action.row.expires_at)} required /></label>
    <label>Extension approval reference<input name="approval_reference" required /></label>
    <label>Extension reason<textarea name="reason" rows={4} required minLength={5} /></label>
  </>;
  if (action.kind === "DEFERRAL_CLOSE") return <>
    <label>Rectification and release note<textarea name="note" rows={4} required minLength={5} /></label>
    <label>Work order / tech-log reference<input name="evidence_reference" required /></label>
    <label>Evidence description<textarea name="evidence_description" rows={2} required /></label>
  </>;
  if (action.kind === "SHOP_RELEASE") return <>
    <label>Release reference<input name="release_reference" required /></label>
    <label>Release note<textarea name="note" rows={4} required minLength={3} /></label>
  </>;
  if (action.kind === "SMS_ASSESS") return <>
    <fieldset className="rel-ops__choice"><legend>Reliability relevance</legend><label><input type="radio" name="relevant" checked={smsRelevant} onChange={() => onSmsRelevant(true)} /> Relevant — create or update the canonical Reliability link</label><label><input type="radio" name="relevant" checked={!smsRelevant} onChange={() => onSmsRelevant(false)} /> Not relevant — retain the assessment without a Reliability event</label></fieldset>
    <label>Investigation status<select name="investigation_status" defaultValue={action.row.investigation_status}><option>OPEN</option><option>UNDER_INVESTIGATION</option><option>ACTIONS_OPEN</option><option>CLOSED</option></select></label>
    {smsRelevant && <label>Technical Reliability link reason<textarea name="reliability_link_reason" rows={4} required minLength={5} defaultValue={action.row.reliability_link_reason || ""} /></label>}
  </>;
  if (action.kind === "WORKBOOK_ROW_APPROVE") return <label>Approval note<textarea name="note" rows={4} required minLength={3} defaultValue="Source values verified against the preserved controlled workbook." /></label>;
  return <label>Rejection reason<textarea name="note" rows={4} required minLength={3} /></label>;
}
