import React, { useCallback, useEffect, useMemo, useState } from "react";

import { apiRequest } from "../../services/apiClient";


type View = "overview" | "flight" | "deferrals" | "shop" | "sms" | "qms" | "workbooks";
type StatusMap = Record<string, number>;

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

const BASE = "/reliability/operational-sources";
const VIEWS: Array<[View, string]> = [
  ["overview", "Control overview"],
  ["flight", "Flight Ops"],
  ["deferrals", "MEL / CDL"],
  ["shop", "Component shop"],
  ["sms", "SMS linkage"],
  ["qms", "QMS linkage"],
  ["workbooks", "Workbook migration"],
];

function displayDate(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function statusClass(value?: string | null): string {
  return `reliability-v2__status reliability-v2__status--${(value || "unknown").toLowerCase().replaceAll("_", "-").replaceAll(" ", "-")}`;
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

function iso(value: string): string {
  return new Date(value).toISOString();
}

function localDateTime(offsetHours = 0): string {
  const date = new Date(Date.now() + offsetHours * 60 * 60 * 1000);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
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

function StatusStrip({ values }: { values: StatusMap }) {
  const entries = Object.entries(values);
  return (
    <div className="reliability-v2__metric-strip">
      {entries.length === 0 && <div className="reliability-v2__metric"><span>Records</span><strong>0</strong></div>}
      {entries.map(([key, count]) => <div className="reliability-v2__metric" key={key}><span>{key.replaceAll("_", " ")}</span><strong>{count}</strong></div>)}
    </div>
  );
}

function SectionHeading({ eyebrow, title, detail, actions }: { eyebrow: string; title: string; detail: string; actions?: React.ReactNode }) {
  return <div className="reliability-v2__section-heading reliability-v2__section-heading--page"><div><p className="reliability-v2__eyebrow">{eyebrow}</p><h2>{title}</h2><p>{detail}</p></div>{actions && <div className="reliability-v2__actions">{actions}</div>}</div>;
}

function StateMessage({ loading, error, message }: { loading: boolean; error: string | null; message: string | null }) {
  return <>{loading && <div className="reliability-v2__loading" role="status">Loading controlled operational records…</div>}{error && <div className="reliability-v2__error" role="alert">{error}</div>}{message && <div className="reliability-v2__success" role="status">{message}</div>}</>;
}

export default function ReliabilityOperationalControl(): React.ReactElement {
  const [view, setView] = useState<View>("overview");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [flights, setFlights] = useState<FlightOperation[]>([]);
  const [deferrals, setDeferrals] = useState<Deferral[]>([]);
  const [shop, setShop] = useState<ShopFinding[]>([]);
  const [sms, setSms] = useState<SmsOccurrence[]>([]);
  const [workbooks, setWorkbooks] = useState<WorkbookImport[]>([]);
  const [selectedWorkbook, setSelectedWorkbook] = useState<string>("");
  const [workbookRows, setWorkbookRows] = useState<WorkbookRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextSummary, nextReadiness, nextFlights, nextDeferrals, nextShop, nextSms, nextWorkbooks] = await Promise.all([
        request<Summary>(`${BASE}/summary`),
        request<Readiness>("/reliability/authoritative-sources/readiness"),
        request<FlightOperation[]>(`${BASE}/flight-operations`),
        request<Deferral[]>(`${BASE}/deferrals`),
        request<ShopFinding[]>(`${BASE}/component-shop`),
        request<SmsOccurrence[]>(`${BASE}/sms`),
        request<WorkbookImport[]>(`${BASE}/workbooks`),
      ]);
      setSummary(nextSummary);
      setReadiness(nextReadiness);
      setFlights(nextFlights);
      setDeferrals(nextDeferrals);
      setShop(nextShop);
      setSms(nextSms);
      setWorkbooks(nextWorkbooks);
      const chosen = selectedWorkbook || nextWorkbooks[0]?.id || "";
      setSelectedWorkbook(chosen);
      if (chosen) setWorkbookRows(await request<WorkbookRow[]>(`${BASE}/workbooks/${encodeURIComponent(chosen)}/rows`));
      else setWorkbookRows([]);
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setLoading(false);
    }
  }, [selectedWorkbook]);

  useEffect(() => { void refresh(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const run = async (action: () => Promise<unknown>, success: string) => {
    setError(null);
    setMessage(null);
    try {
      await action();
      setMessage(success);
      await refresh();
    } catch (caught) {
      setError(errorText(caught));
    }
  };

  const selectedImport = useMemo(() => workbooks.find((item) => item.id === selectedWorkbook) || null, [selectedWorkbook, workbooks]);

  return <>
    <section className="reliability-v2__section">
      <SectionHeading eyebrow="Authoritative source control" title="Operational Reliability control centre" detail="Record, approve, reconcile and trace the operational evidence that drives Reliability calculations and investigations." actions={<button type="button" className="btn btn-secondary" onClick={() => void run(() => mutate("/reliability/authoritative-sources/configure"), "Authoritative source configuration refreshed.")}>Configure authoritative sources</button>} />
      <div className="reliability-v2__actions" role="tablist" aria-label="Operational Reliability workspaces">
        {VIEWS.map(([id, label]) => <button key={id} type="button" className={view === id ? "btn btn-primary" : "btn btn-secondary"} onClick={() => setView(id)}>{label}</button>)}
      </div>
      <StateMessage loading={loading} error={error} message={message} />
    </section>

    {!loading && view === "overview" && <Overview summary={summary} readiness={readiness} />}
    {!loading && view === "flight" && <FlightView rows={flights} run={run} />}
    {!loading && view === "deferrals" && <DeferralView rows={deferrals} run={run} />}
    {!loading && view === "shop" && <ShopView rows={shop} run={run} />}
    {!loading && view === "sms" && <SmsView rows={sms} run={run} />}
    {!loading && view === "qms" && <QmsLinkView run={run} />}
    {!loading && view === "workbooks" && <WorkbookView imports={workbooks} rows={workbookRows} selected={selectedImport} onSelect={async (id) => { setSelectedWorkbook(id); setWorkbookRows(id ? await request<WorkbookRow[]>(`${BASE}/workbooks/${encodeURIComponent(id)}/rows`) : []); }} run={run} />}
  </>;
}

function Overview({ summary, readiness }: { summary: Summary | null; readiness: Readiness | null }) {
  return <>
    <section className="reliability-v2__section"><SectionHeading eyebrow="Operational registers" title="Controlled lifecycle counts" detail={`Snapshot generated ${displayDate(summary?.generated_at)}`} />
      <div className="reliability-v2__split">
        <div><h3>Flight Operations</h3><StatusStrip values={summary?.flight_operations || {}} /></div>
        <div><h3>MEL / CDL</h3><StatusStrip values={summary?.deferrals || {}} /></div>
      </div>
      <div className="reliability-v2__split">
        <div><h3>Component shop</h3><StatusStrip values={summary?.component_shop || {}} /></div>
        <div><h3>SMS relevance</h3><StatusStrip values={summary?.sms || {}} /></div>
      </div>
      <h3>Workbook migration</h3><StatusStrip values={summary?.workbooks || {}} />
    </section>
    <section className="reliability-v2__section"><SectionHeading eyebrow="Canonical feed assurance" title="Authoritative source readiness" detail="Available and ingested counts are compared per source; empty registers remain visible rather than appearing healthy." />
      <div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>Source</th><th>Module</th><th>State</th><th>Available</th><th>Ingested</th><th>Latest source</th><th>Last canonical sync</th><th>Control detail</th></tr></thead><tbody>
        {(readiness?.items || []).map((item) => <tr key={item.code}><td><strong>{item.code}</strong><small>{item.dataset}</small></td><td>{item.module}</td><td><span className={statusClass(item.connection_state)}>{item.connection_state.replaceAll("_", " ")}</span></td><td>{item.available_record_count}</td><td>{item.ingested_record_count}</td><td>{displayDate(item.latest_available_at)}</td><td>{displayDate(item.last_success_at)}</td><td>{item.detail}</td></tr>)}
        {!readiness?.items.length && <tr><td colSpan={8}>No source readiness records are available.</td></tr>}
      </tbody></table></div>
    </section>
  </>;
}

function FlightView({ rows, run }: { rows: FlightOperation[]; run: (action: () => Promise<unknown>, success: string) => Promise<void> }) {
  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void run(() => mutate(`${BASE}/flight-operations`, {
      record_number: formValue(data, "record_number"), event_type: formValue(data, "event_type"), occurred_at: iso(formValue(data, "occurred_at")), aircraft_serial_number: formValue(data, "aircraft_serial_number"), flight_number: formValue(data, "flight_number"), origin_station: nullable(data, "origin_station"), destination_station: nullable(data, "destination_station"), scheduled_departure_at: formValue(data, "scheduled_departure_at") ? iso(formValue(data, "scheduled_departure_at")) : null, actual_departure_at: formValue(data, "actual_departure_at") ? iso(formValue(data, "actual_departure_at")) : null, delay_minutes: numberOrNull(data, "delay_minutes"), dispatch_impact: nullable(data, "dispatch_impact"), severity: formValue(data, "severity"), ata_chapter: nullable(data, "ata_chapter"), description: formValue(data, "description"),
    }), "Flight Operations record created for approval.");
  };
  return <>
    <section className="reliability-v2__section"><SectionHeading eyebrow="Operational interruption register" title="Flight Operations occurrence" detail="Technical delay, cancellation, return-to-gate, turnback, diversion, in-flight shutdown and aborted take-off records are revision controlled before canonical ingestion." />
      <form className="reliability-v2__form" onSubmit={submit}><div className="reliability-v2__form-grid">
        <label>Controlled reference<input name="record_number" required /></label><label>Occurrence type<select name="event_type"><option>TECHNICAL_DELAY</option><option>TECHNICAL_CANCELLATION</option><option>RETURN_TO_GATE</option><option>AIR_TURNBACK</option><option>DIVERSION</option><option>IN_FLIGHT_SHUTDOWN</option><option>ABORTED_TAKEOFF</option></select></label><label>Occurred at<input type="datetime-local" name="occurred_at" defaultValue={localDateTime()} required /></label><label>Aircraft serial<input name="aircraft_serial_number" required /></label><label>Flight number<input name="flight_number" required /></label><label>Origin<input name="origin_station" maxLength={8} /></label><label>Destination<input name="destination_station" maxLength={8} /></label><label>Scheduled departure<input type="datetime-local" name="scheduled_departure_at" /></label><label>Actual departure<input type="datetime-local" name="actual_departure_at" /></label><label>Delay minutes<input type="number" min="0" name="delay_minutes" /></label><label>Dispatch impact<input name="dispatch_impact" /></label><label>Severity<select name="severity" defaultValue="MEDIUM"><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select></label><label>ATA<input name="ata_chapter" /></label>
      </div><label>Description<textarea name="description" rows={3} required /></label><button className="btn btn-primary">Create controlled occurrence</button></form>
    </section>
    <Register headers={["Reference", "Flight", "Aircraft", "Occurrence", "When", "Impact", "Status", "Canonical event", "Actions"]} empty="No Flight Operations records are available.">{rows.map((row) => <tr key={row.id}><td><strong>{row.record_number}</strong><small>Rev {row.revision}</small></td><td>{row.flight_number}<small>{row.origin_station || "—"} → {row.destination_station || "—"}</small></td><td>{row.aircraft_serial_number}</td><td>{row.event_type}</td><td>{displayDate(row.occurred_at)}</td><td>{row.delay_minutes == null ? row.dispatch_impact || "—" : `${row.delay_minutes} min`}</td><td><span className={statusClass(row.status)}>{row.status}</span></td><td>{row.canonical_event_id || "—"}</td><td><div className="reliability-v2__actions">{row.status === "DRAFT" && <button className="btn btn-primary" type="button" onClick={() => void run(() => mutate(`${BASE}/flight-operations/${row.id}/approve`), "Flight Operations record approved and ingested.")}>Approve</button>}{row.status === "APPROVED" && <button className="btn btn-secondary" type="button" onClick={() => { const note = window.prompt("Closure note"); if (note) void run(() => mutate(`${BASE}/flight-operations/${row.id}/close`, { note, evidence: [] }), "Flight Operations record closed with a new canonical revision."); }}>Close</button>}</div></td></tr>)}</Register>
  </>;
}

function DeferralView({ rows, run }: { rows: Deferral[]; run: (action: () => Promise<unknown>, success: string) => Promise<void> }) {
  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void run(() => mutate(`${BASE}/deferrals`, {
      deferral_number: formValue(data, "deferral_number"), deferral_type: formValue(data, "deferral_type"), aircraft_serial_number: formValue(data, "aircraft_serial_number"), defect_reference: formValue(data, "defect_reference"), item_reference: formValue(data, "item_reference"), category: nullable(data, "category"), applied_at: iso(formValue(data, "applied_at")), expires_at: iso(formValue(data, "expires_at")), control_basis: formValue(data, "control_basis"), operational_procedure: nullable(data, "operational_procedure"), maintenance_procedure: nullable(data, "maintenance_procedure"), repetitive_inspection_minutes: numberOrNull(data, "repetitive_inspection_minutes"), flight_number: nullable(data, "flight_number"), ata_chapter: nullable(data, "ata_chapter"), description: formValue(data, "description"), severity: formValue(data, "severity"),
    }), "MEL/CDL deferral created for approval.");
  };
  return <>
    <section className="reliability-v2__section"><SectionHeading eyebrow="Defect control" title="MEL / CDL lifecycle" detail="Application, approved control basis, procedures, repeat inspections, expiry, extension and closure evidence are held as one controlled lifecycle." />
      <form className="reliability-v2__form" onSubmit={submit}><div className="reliability-v2__form-grid">
        <label>Deferral number<input name="deferral_number" required /></label><label>Type<select name="deferral_type"><option>MEL</option><option>CDL</option></select></label><label>Aircraft serial<input name="aircraft_serial_number" required /></label><label>Defect reference<input name="defect_reference" required /></label><label>MEL/CDL item reference<input name="item_reference" required /></label><label>Category<input name="category" /></label><label>Applied at<input type="datetime-local" name="applied_at" defaultValue={localDateTime()} required /></label><label>Expiry<input type="datetime-local" name="expires_at" defaultValue={localDateTime(72)} required /></label><label>Repeat inspection minutes<input type="number" min="1" name="repetitive_inspection_minutes" /></label><label>Flight number<input name="flight_number" /></label><label>ATA<input name="ata_chapter" /></label><label>Severity<select name="severity" defaultValue="MEDIUM"><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select></label>
      </div><label>Approved control basis<textarea name="control_basis" rows={2} required /></label><label>Operational procedure<textarea name="operational_procedure" rows={2} /></label><label>Maintenance procedure<textarea name="maintenance_procedure" rows={2} /></label><label>Defect description<textarea name="description" rows={3} required /></label><button className="btn btn-primary">Create controlled deferral</button></form>
    </section>
    <Register headers={["Deferral", "Aircraft", "Item", "Applied", "Expiry", "Status", "Canonical event", "Actions"]} empty="No MEL/CDL deferrals are available.">{rows.map((row) => <tr key={row.id}><td><strong>{row.deferral_number}</strong><small>{row.deferral_type} · Rev {row.revision}</small></td><td>{row.aircraft_serial_number}</td><td>{row.item_reference}<small>{row.defect_reference}</small></td><td>{displayDate(row.applied_at)}</td><td>{displayDate(row.expires_at)}</td><td><span className={statusClass(row.status)}>{row.status}</span></td><td>{row.canonical_event_id || "—"}</td><td><div className="reliability-v2__actions">{row.status === "DRAFT" && <button className="btn btn-primary" type="button" onClick={() => void run(() => mutate(`${BASE}/deferrals/${row.id}/approve`), "Deferral approved and ingested.")}>Approve</button>}{["OPEN", "EXTENDED"].includes(row.status) && <button className="btn btn-secondary" type="button" onClick={() => { const next = window.prompt("New expiry (ISO date/time)"); const reason = window.prompt("Extension reason"); const reference = window.prompt("Approval reference"); if (next && reason && reference) void run(() => mutate(`${BASE}/deferrals/${row.id}/extend`, { new_expires_at: new Date(next).toISOString(), reason, approval_reference: reference }), "Deferral extension recorded and ingested."); }}>Extend</button>}{["OPEN", "EXTENDED", "EXPIRED"].includes(row.status) && <button className="btn btn-secondary" type="button" onClick={() => { const note = window.prompt("Closure and rectification evidence"); if (note) void run(() => mutate(`${BASE}/deferrals/${row.id}/close`, { note, evidence: [] }), "Deferral closed with controlled evidence."); }}>Close</button>}</div></td></tr>)}</Register>
  </>;
}

function ShopView({ rows, run }: { rows: ShopFinding[]; run: (action: () => Promise<unknown>, success: string) => Promise<void> }) {
  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const eventType = formValue(data, "event_type");
    void run(() => mutate(`${BASE}/component-shop`, {
      shop_order_reference: formValue(data, "shop_order_reference"), event_type: eventType, component_id: numberOrNull(data, "component_id"), aircraft_serial_number: nullable(data, "aircraft_serial_number"), part_number: formValue(data, "part_number"), component_serial_number: formValue(data, "component_serial_number"), received_at: iso(formValue(data, "received_at")), inspected_at: iso(formValue(data, "inspected_at")), ata_chapter: nullable(data, "ata_chapter"), confirmed_failure: eventType === "NO_FAULT_FOUND" ? false : formValue(data, "confirmed_failure") === "true" ? true : null, test_result: formValue(data, "test_result"), disposition: formValue(data, "disposition"), release_reference: nullable(data, "release_reference"), description: formValue(data, "description"), severity: formValue(data, "severity"),
    }), "Component-shop finding created for approval.");
  };
  return <>
    <section className="reliability-v2__section"><SectionHeading eyebrow="Component investigation" title="Shop findings and NFF disposition" detail="Incoming identity, approved testing, confirmed-failure decision, disposition and release references remain linked to the canonical occurrence." />
      <form className="reliability-v2__form" onSubmit={submit}><div className="reliability-v2__form-grid">
        <label>Shop order<input name="shop_order_reference" required /></label><label>Finding type<select name="event_type"><option>SHOP_FINDING</option><option>NO_FAULT_FOUND</option></select></label><label>Component ID<input type="number" min="1" name="component_id" /></label><label>Aircraft serial<input name="aircraft_serial_number" /></label><label>Part number<input name="part_number" required /></label><label>Serial number<input name="component_serial_number" required /></label><label>Received at<input type="datetime-local" name="received_at" defaultValue={localDateTime(-2)} required /></label><label>Inspected at<input type="datetime-local" name="inspected_at" defaultValue={localDateTime()} required /></label><label>ATA<input name="ata_chapter" /></label><label>Confirmed failure<select name="confirmed_failure"><option value="">Undetermined</option><option value="true">Yes</option><option value="false">No</option></select></label><label>Release reference<input name="release_reference" /></label><label>Severity<select name="severity" defaultValue="MEDIUM"><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select></label>
      </div><label>Approved test result<textarea name="test_result" rows={3} required /></label><label>Disposition<textarea name="disposition" rows={3} required /></label><label>Finding description<textarea name="description" rows={3} required /></label><button className="btn btn-primary">Create shop finding</button></form>
    </section>
    <Register headers={["Shop order", "Component", "Finding", "Disposition", "Status", "Canonical event", "Actions"]} empty="No component-shop findings are available.">{rows.map((row) => <tr key={row.id}><td><strong>{row.shop_order_reference}</strong><small>Rev {row.revision}</small></td><td>{row.part_number}<small>{row.component_serial_number}</small></td><td>{row.event_type}<small>{row.confirmed_failure == null ? "Failure undetermined" : row.confirmed_failure ? "Confirmed failure" : "No confirmed failure"}</small></td><td>{row.disposition}</td><td><span className={statusClass(row.status)}>{row.status}</span></td><td>{row.canonical_event_id || "—"}</td><td><div className="reliability-v2__actions">{row.status === "DRAFT" && <button className="btn btn-primary" type="button" onClick={() => void run(() => mutate(`${BASE}/component-shop/${row.id}/approve`), "Shop finding approved and ingested.")}>Approve</button>}{row.status === "APPROVED" && <button className="btn btn-secondary" type="button" onClick={() => { const reference = window.prompt("Release reference"); const note = window.prompt("Release note"); if (reference && note) void run(() => mutate(`${BASE}/component-shop/${row.id}/release`, { release_reference: reference, note }), "Component-shop release recorded and ingested."); }}>Release</button>}</div></td></tr>)}</Register>
  </>;
}

function SmsView({ rows, run }: { rows: SmsOccurrence[]; run: (action: () => Promise<unknown>, success: string) => Promise<void> }) {
  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void run(() => mutate(`${BASE}/sms`, {
      sms_reference: formValue(data, "sms_reference"), occurred_at: iso(formValue(data, "occurred_at")), aircraft_serial_number: nullable(data, "aircraft_serial_number"), hazard_reference: nullable(data, "hazard_reference"), risk_classification: formValue(data, "risk_classification"), investigation_status: formValue(data, "investigation_status"), ata_chapter: nullable(data, "ata_chapter"), description: formValue(data, "description"), severity: formValue(data, "severity"),
    }), "SMS occurrence registered for Reliability relevance assessment.");
  };
  return <>
    <section className="reliability-v2__section"><SectionHeading eyebrow="Safety–Reliability boundary" title="SMS occurrence assessment" detail="Safety occurrences remain source-owned; only an accountable positive Reliability relevance assessment creates a canonical Reliability event." />
      <form className="reliability-v2__form" onSubmit={submit}><div className="reliability-v2__form-grid">
        <label>SMS reference<input name="sms_reference" required /></label><label>Occurred at<input type="datetime-local" name="occurred_at" defaultValue={localDateTime()} required /></label><label>Aircraft serial<input name="aircraft_serial_number" /></label><label>Hazard reference<input name="hazard_reference" /></label><label>Risk classification<input name="risk_classification" required /></label><label>Investigation status<input name="investigation_status" defaultValue="OPEN" required /></label><label>ATA<input name="ata_chapter" /></label><label>Severity<select name="severity" defaultValue="MEDIUM"><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select></label>
      </div><label>Occurrence description<textarea name="description" rows={3} required /></label><button className="btn btn-primary">Register SMS occurrence</button></form>
    </section>
    <Register headers={["SMS reference", "Occurred", "Aircraft", "Risk", "Investigation", "Reliability relevance", "Status", "Canonical event", "Actions"]} empty="No SMS occurrences are available.">{rows.map((row) => <tr key={row.id}><td><strong>{row.sms_reference}</strong><small>Rev {row.revision}</small></td><td>{displayDate(row.occurred_at)}</td><td>{row.aircraft_serial_number || "Fleet"}</td><td>{row.risk_classification}</td><td>{row.investigation_status}</td><td>{row.reliability_relevant ? row.reliability_link_reason || "Relevant" : "Not linked"}</td><td><span className={statusClass(row.status)}>{row.status}</span></td><td>{row.canonical_event_id || "—"}</td><td><button className="btn btn-secondary" type="button" onClick={() => { const relevant = window.confirm("Is this occurrence relevant to technical Reliability analysis?"); const reason = relevant ? window.prompt("Reliability link reason") : null; const investigationStatus = window.prompt("Investigation status", row.investigation_status) || row.investigation_status; if (!relevant || reason) void run(() => mutate(`${BASE}/sms/${row.id}/assess`, { reliability_relevant: relevant, reliability_link_reason: reason, investigation_status: investigationStatus }), relevant ? "SMS occurrence assessed and linked to Reliability." : "SMS occurrence assessed without creating a Reliability event."); }}>Assess</button></td></tr>)}</Register>
  </>;
}

function QmsLinkView({ run }: { run: (action: () => Promise<unknown>, success: string) => Promise<void> }) {
  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const findingId = formValue(data, "finding_id");
    void run(() => mutate(`/reliability/authoritative-sources/qms/findings/${encodeURIComponent(findingId)}/link`, {
      event_type: formValue(data, "event_type"), reliability_link_reason: formValue(data, "reliability_link_reason"), aircraft_serial_number: nullable(data, "aircraft_serial_number"), ata_chapter: nullable(data, "ata_chapter"), severity: nullable(data, "severity"),
    }), "QMS finding linked with preserved objective evidence and provenance.");
  };
  return <section className="reliability-v2__section"><SectionHeading eyebrow="Quality–Reliability boundary" title="Explicit QMS finding linkage" detail="Only a selected finding with a documented technical relevance reason is copied into the canonical Reliability occurrence stream." />
    <form className="reliability-v2__form" onSubmit={submit}><div className="reliability-v2__form-grid"><label>QMS finding ID<input name="finding_id" required /></label><label>Reliability classification<select name="event_type"><option>MAINTENANCE_ERROR</option><option>SUPPLIER_ESCAPE</option><option>SAFETY_EVENT</option><option>OTHER</option></select></label><label>Aircraft serial<input name="aircraft_serial_number" /></label><label>ATA<input name="ata_chapter" /></label><label>Severity override<select name="severity"><option value="">Use QMS classification</option><option>LOW</option><option>MEDIUM</option><option>HIGH</option><option>CRITICAL</option></select></label></div><label>Reliability relevance reason<textarea name="reliability_link_reason" rows={4} required /></label><button className="btn btn-primary">Link controlled finding</button></form>
  </section>;
}

function WorkbookView({ imports, rows, selected, onSelect, run }: { imports: WorkbookImport[]; rows: WorkbookRow[]; selected: WorkbookImport | null; onSelect: (id: string) => Promise<void>; run: (action: () => Promise<unknown>, success: string) => Promise<void> }) {
  const upload = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void run(() => mutate(`${BASE}/workbooks/upload`, data), "Workbook uploaded and its source rows preserved.");
  };
  const map = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected) return;
    const data = new FormData(event.currentTarget);
    try {
      const mapping = JSON.parse(formValue(data, "mapping")) as Record<string, string>;
      const defaults = formValue(data, "defaults") ? JSON.parse(formValue(data, "defaults")) as Record<string, unknown> : {};
      void run(() => mutate(`${BASE}/workbooks/${selected.id}/map`, { mapping, defaults }), "Workbook mapped and validated at row level.");
    } catch (caught) {
      window.alert(`Mapping JSON is invalid: ${errorText(caught)}`);
    }
  };
  return <>
    <section className="reliability-v2__section"><SectionHeading eyebrow="Controlled historical migration" title="Workbook upload and reconciliation" detail="The original workbook, row values, mapping profile, validation outcome, human decision and canonical event remain traceable." />
      <div className="reliability-v2__split reliability-v2__split--forms"><form className="reliability-v2__form" onSubmit={upload}><h3>Upload source workbook</h3><label>Workbook (.xlsx or .csv)<input type="file" name="file" accept=".xlsx,.csv" required /></label><label>Header row<input type="number" name="header_row" min="1" max="100" defaultValue="1" /></label><button className="btn btn-primary">Upload and preserve rows</button></form>
        <form className="reliability-v2__form" onSubmit={map}><h3>Map selected workbook</h3><label>Workbook<select value={selected?.id || ""} onChange={(event) => void onSelect(event.target.value)}><option value="">Select workbook</option>{imports.map((item) => <option key={item.id} value={item.id}>{item.original_filename} · {item.status}</option>)}</select></label><label>Canonical field → source column JSON<textarea name="mapping" rows={9} defaultValue={'{\n  "event_type": "Event Type",\n  "occurred_at": "Date",\n  "description": "Description",\n  "aircraft_serial_number": "Aircraft",\n  "ata_chapter": "ATA",\n  "reference_code": "Reference",\n  "severity": "Severity"\n}'} /></label><label>Static defaults JSON<textarea name="defaults" rows={3} defaultValue="{}" /></label><button className="btn btn-primary" disabled={!selected}>Map and validate</button></form></div>
    </section>
    <section className="reliability-v2__section"><SectionHeading eyebrow="Import register" title="Historical workbook controls" detail="Approval is blocked until each row has an explicit approve or reject decision." actions={selected && <><button className="btn btn-secondary" type="button" onClick={() => void run(() => mutate(`${BASE}/workbooks/${selected.id}/approve`), "Workbook reconciliation approved.")}>Approve workbook</button><button className="btn btn-primary" type="button" onClick={() => void run(() => mutate(`${BASE}/workbooks/${selected.id}/ingest`), "Approved workbook rows ingested into canonical Reliability evidence.")}>Ingest approved rows</button></>} />
      <div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>Workbook</th><th>Status</th><th>Total</th><th>Valid</th><th>Invalid</th><th>Approved</th><th>Rejected</th><th>Ingested</th></tr></thead><tbody>{imports.map((item) => <tr key={item.id} onClick={() => void onSelect(item.id)}><td><strong>{item.original_filename}</strong><small>Rev {item.revision} · {displayDate(item.created_at)}</small></td><td><span className={statusClass(item.status)}>{item.status}</span></td><td>{item.total_rows}</td><td>{item.valid_rows}</td><td>{item.invalid_rows}</td><td>{item.approved_rows}</td><td>{item.rejected_rows}</td><td>{item.ingested_rows}</td></tr>)}{imports.length === 0 && <tr><td colSpan={8}>No historical workbooks are registered.</td></tr>}</tbody></table></div>
    </section>
    {selected && <section className="reliability-v2__section"><SectionHeading eyebrow="Row reconciliation" title={`${selected.original_filename} source rows`} detail="Review mapped values and validation errors before committing each row." />
      <div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr><th>Source row</th><th>Status</th><th>Mapped occurrence</th><th>Validation</th><th>Canonical event</th><th>Decision</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td>{row.sheet_name} · {row.source_row_number}<details><summary>Raw values</summary><pre>{JSON.stringify(row.raw_json, null, 2)}</pre></details></td><td><span className={statusClass(row.status)}>{row.status}</span></td><td><pre>{JSON.stringify(row.mapped_json, null, 2)}</pre></td><td>{row.validation_errors_json.length ? <pre>{JSON.stringify(row.validation_errors_json, null, 2)}</pre> : "Validated"}</td><td>{row.canonical_event_id || "—"}</td><td><div className="reliability-v2__actions"><button type="button" className="btn btn-primary" disabled={!['VALID', 'APPROVED'].includes(row.status)} onClick={() => { const note = window.prompt("Approval note", "Source values verified against the controlled workbook."); if (note) void run(() => mutate(`${BASE}/workbooks/${selected.id}/rows/${row.id}/decision`, { decision: "APPROVE", note }), "Workbook row approved."); }}>Approve</button><button type="button" className="btn btn-secondary" disabled={row.status === "INGESTED"} onClick={() => { const note = window.prompt("Rejection reason"); if (note) void run(() => mutate(`${BASE}/workbooks/${selected.id}/rows/${row.id}/decision`, { decision: "REJECT", note }), "Workbook row rejected with reason."); }}>Reject</button></div></td></tr>)}{rows.length === 0 && <tr><td colSpan={6}>No source rows are available for this workbook.</td></tr>}</tbody></table></div>
    </section>}
  </>;
}

function Register({ headers, empty, children }: { headers: string[]; empty: string; children: React.ReactNode }) {
  const hasChildren = React.Children.count(children) > 0;
  return <section className="reliability-v2__section"><div className="reliability-v2__table-wrap"><table className="reliability-v2__table"><thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead><tbody>{children}{!hasChildren && <tr><td colSpan={headers.length}>{empty}</td></tr>}</tbody></table></div></section>;
}
