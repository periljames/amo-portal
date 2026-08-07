import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { listAircraft, type AircraftRead } from "../../services/fleet";
import {
  createDailyUtilisationDraft,
  getDailyUtilisationContext,
  listDailyUtilisationEntries,
  postDailyUtilisation,
  previewDailyUtilisation,
  type DailyComponentOverride,
  type DailyExposure,
  type DailyUtilisationContext,
  type DailyUtilisationEntry,
  type DailyUtilisationPayload,
  type DailyUtilisationPreview,
} from "../../services/dailyUtilisation";
import "../../styles/daily-utilisation.css";

type OverrideDraft = {
  enabled: boolean;
  hours: string;
  cycles: string;
  reason: string;
};

const today = () => new Date().toISOString().slice(0, 10);

function idempotency(serialNumber: string, operationDate: string, techlogNo: string): string {
  return `MANUAL:${serialNumber}:${operationDate}:${techlogNo.trim().toUpperCase()}`;
}

function formatHours(value: string | number | null | undefined): string {
  if (value == null || value === "") return "—";
  return Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatCycles(value: number | null | undefined): string {
  if (value == null) return "—";
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function exposureLabel(row: DailyExposure): string {
  if (row.derivation === "OVERRIDE") return "Override";
  if (row.derivation === "SHARED_DAILY") return "Shared daily value";
  return "No automatic increment";
}

const DailyAircraftUtilisationPage: React.FC = () => {
  const { amoCode } = useParams();
  const [aircraft, setAircraft] = useState<AircraftRead[]>([]);
  const [serialNumber, setSerialNumber] = useState("");
  const [context, setContext] = useState<DailyUtilisationContext | null>(null);
  const [entries, setEntries] = useState<DailyUtilisationEntry[]>([]);
  const [operationDate, setOperationDate] = useState(today());
  const [techlogNo, setTechlogNo] = useState("");
  const [station, setStation] = useState("");
  const [hours, setHours] = useState("");
  const [cycles, setCycles] = useState("");
  const [remarks, setRemarks] = useState("");
  const [nilOperation, setNilOperation] = useState(false);
  const [overrides, setOverrides] = useState<Record<number, OverrideDraft>>({});
  const [preview, setPreview] = useState<DailyUtilisationPreview | null>(null);
  const [draftId, setDraftId] = useState<string | null>(null);
  const [working, setWorking] = useState<"preview" | "draft" | "post" | null>(null);
  const [message, setMessage] = useState<{ tone: "success" | "danger" | "info"; text: string } | null>(null);

  useEffect(() => {
    void listAircraft({ is_active: true })
      .then((rows) => {
        setAircraft(rows);
        if (rows.length) setSerialNumber((current) => current || rows[0].serial_number);
      })
      .catch((error: unknown) => setMessage({ tone: "danger", text: error instanceof Error ? error.message : "Aircraft could not be loaded." }));
  }, []);

  const reloadAircraft = useCallback(async () => {
    if (!serialNumber) return;
    const [nextContext, nextEntries] = await Promise.all([
      getDailyUtilisationContext(serialNumber),
      listDailyUtilisationEntries(serialNumber),
    ]);
    setContext(nextContext);
    setEntries(nextEntries);
    setOverrides({});
    setPreview(null);
    setDraftId(null);
  }, [serialNumber]);

  useEffect(() => {
    void reloadAircraft().catch((error: unknown) => setMessage({ tone: "danger", text: error instanceof Error ? error.message : "Utilisation context could not be loaded." }));
  }, [reloadAircraft]);

  useEffect(() => {
    if (nilOperation) {
      setHours("0.00");
      setCycles("0");
    }
    setPreview(null);
    setDraftId(null);
  }, [nilOperation]);

  const payload = useMemo<DailyUtilisationPayload | null>(() => {
    if (!serialNumber || !operationDate || !techlogNo.trim()) return null;
    const parsedCycles = Number(cycles || 0);
    if (!Number.isInteger(parsedCycles) || parsedCycles < 0) return null;
    if (!/^\d+(?:\.\d{1,2})?$/.test(hours || "")) return null;
    const component_overrides: DailyComponentOverride[] = Object.entries(overrides)
      .filter(([, row]) => row.enabled)
      .map(([componentId, row]) => ({
        component_id: Number(componentId),
        hours_delta: row.hours,
        cycles_delta: Number(row.cycles),
        reason: row.reason.trim(),
      }));
    return {
      operation_date: operationDate,
      techlog_no: techlogNo.trim().toUpperCase(),
      station: station.trim().toUpperCase() || null,
      flight_hours: hours,
      cycles: parsedCycles,
      nil_operation: nilOperation,
      source_reference: null,
      remarks: remarks.trim() || null,
      idempotency_key: idempotency(serialNumber, operationDate, techlogNo),
      component_overrides,
    };
  }, [cycles, hours, nilOperation, operationDate, overrides, remarks, serialNumber, station, techlogNo]);

  const updateOverride = (componentId: number, patch: Partial<OverrideDraft>) => {
    setOverrides((current) => {
      const component = context?.installed_components.find((row) => row.component_id === componentId);
      const defaultHours = component?.target_type === "ENGINE" || component?.target_type === "PROPELLER" ? hours : "0.00";
      const defaultCycles = component?.target_type === "ENGINE" || component?.target_type === "PROPELLER" ? cycles : "0";
      return {
        ...current,
        [componentId]: {
          ...(current[componentId] ?? {
            enabled: false,
            hours: defaultHours || "0.00",
            cycles: defaultCycles || "0",
            reason: "",
          }),
          ...patch,
        },
      };
    });
    setPreview(null);
    setDraftId(null);
  };

  const runPreview = async () => {
    if (!payload) {
      setMessage({ tone: "danger", text: "Select an aircraft and enter a valid date, tech-log reference, hours and whole-number cycles." });
      return;
    }
    setWorking("preview");
    setMessage(null);
    try {
      setPreview(await previewDailyUtilisation(serialNumber, payload));
    } catch (error) {
      setMessage({ tone: "danger", text: error instanceof Error ? error.message : "Preview failed." });
    } finally {
      setWorking(null);
    }
  };

  const saveDraft = async (): Promise<string | null> => {
    if (!payload) {
      setMessage({ tone: "danger", text: "Complete the required daily-entry fields first." });
      return null;
    }
    setWorking("draft");
    setMessage(null);
    try {
      const result = await createDailyUtilisationDraft(serialNumber, payload);
      setDraftId(result.entry.id);
      setPreview(result.preview);
      setMessage({ tone: "info", text: `Draft ${result.entry.techlog_no} saved. Review the calculated allocation before posting.` });
      return result.entry.id;
    } catch (error) {
      setMessage({ tone: "danger", text: error instanceof Error ? error.message : "Draft could not be saved." });
      return null;
    } finally {
      setWorking(null);
    }
  };

  const postEntry = async () => {
    let entryId = draftId;
    if (!entryId) entryId = await saveDraft();
    if (!entryId) return;
    setWorking("post");
    setMessage(null);
    try {
      const result = await postDailyUtilisation(entryId);
      setMessage({
        tone: "success",
        text: `Posted ${result.entry.flight_hours} FH and ${result.entry.cycles} FC. Airframe totals are now ${result.aircraft_total_hours} FH / ${result.aircraft_total_cycles} FC; ${result.component_updates} installed component(s) increased.`,
      });
      setTechlogNo("");
      setHours("");
      setCycles("");
      setRemarks("");
      setNilOperation(false);
      await reloadAircraft();
    } catch (error) {
      setMessage({ tone: "danger", text: error instanceof Error ? error.message : "Daily utilization could not be posted." });
    } finally {
      setWorking(null);
    }
  };

  const selected = aircraft.find((row) => row.serial_number === serialNumber);
  const displayRows = preview?.exposures ?? [];

  return (
    <DepartmentLayout amoCode={amoCode || "UNKNOWN"} activeDepartment="planning">
      <div className="page daily-util-page">
        <header className="page-header daily-util-page__header">
          <div>
            <p className="daily-util-page__eyebrow">Technical Records · Manual source</p>
            <h1>Daily aircraft utilization</h1>
            <p className="page-header__subtitle">
              Enter one authoritative daily FH/FC value. The portal applies it to the airframe, installed engines and installed propellers, then updates planning and reliability.
            </p>
          </div>
          <button className="btn btn-secondary" type="button" onClick={() => void reloadAircraft()} disabled={!serialNumber || working !== null}>Refresh baselines</button>
        </header>

        {message ? <div className={`alert alert--${message.tone}`}>{message.text}</div> : null}

        <section className="daily-util-grid">
          <article className="card daily-util-form-card">
            <div className="daily-util-section-heading">
              <div><span>1</span><h2>Daily source entry</h2></div>
              <small>No EFB required</small>
            </div>

            <div className="daily-util-form-grid">
              <label className="form-field form-field--wide">
                <span>Aircraft</span>
                <select className="input" value={serialNumber} onChange={(event) => setSerialNumber(event.target.value)}>
                  {aircraft.map((row) => <option key={row.serial_number} value={row.serial_number}>{row.registration} · {row.model || row.template || row.serial_number}</option>)}
                </select>
              </label>
              <label className="form-field"><span>Operating date</span><input className="input" type="date" max={today()} value={operationDate} onChange={(event) => setOperationDate(event.target.value)} /></label>
              <label className="form-field"><span>Tech-log / journey-log no.</span><input className="input" value={techlogNo} onChange={(event) => setTechlogNo(event.target.value)} placeholder="e.g. 005487" /></label>
              <label className="form-field"><span>Station</span><input className="input" maxLength={16} value={station} onChange={(event) => setStation(event.target.value)} placeholder="HKJK" /></label>
              <label className="daily-util-nil"><input type="checkbox" checked={nilOperation} onChange={(event) => setNilOperation(event.target.checked)} /><span><strong>Nil operation</strong><small>Aircraft did not fly; record a controlled zero-use day.</small></span></label>
              <label className="form-field"><span>Daily flight hours (FH)</span><input className="input" inputMode="decimal" disabled={nilOperation} value={hours} onChange={(event) => setHours(event.target.value)} placeholder="0.00" /></label>
              <label className="form-field"><span>Daily cycles (FC)</span><input className="input" type="number" min={0} step={1} disabled={nilOperation} value={cycles} onChange={(event) => setCycles(event.target.value)} placeholder="0" /></label>
              <label className="form-field form-field--wide"><span>Remarks</span><textarea className="input" rows={3} value={remarks} onChange={(event) => setRemarks(event.target.value)} placeholder="Optional source or operational note" /></label>
            </div>

            <div className="daily-util-baseline">
              <div><span>Current airframe</span><strong>{formatHours(context?.current_hours)} FH</strong><small>{formatCycles(context?.current_cycles)} FC</small></div>
              <div><span>Last posted day</span><strong>{context?.last_posted_date || "No daily ledger entry"}</strong><small>{selected?.registration || "—"}</small></div>
            </div>
          </article>

          <article className="card daily-util-form-card">
            <div className="daily-util-section-heading">
              <div><span>2</span><h2>Component allocation</h2></div>
              <small>Shared by default</small>
            </div>
            <p className="text-muted">Engines and propellers inherit the daily FH/FC. Use an override only for a real exposure difference such as an engine change, ground run, or APU use.</p>
            <div className="daily-util-component-list">
              {(context?.installed_components ?? []).map((component) => {
                const id = component.component_id as number;
                const override = overrides[id];
                const shared = component.target_type === "ENGINE" || component.target_type === "PROPELLER";
                return (
                  <div className="daily-util-component" key={id}>
                    <div className="daily-util-component__identity">
                      <strong>{component.component_position}</strong>
                      <small>{component.target_type} · {component.component_description || "Installed component"}</small>
                    </div>
                    <div className="daily-util-component__default"><span>Default</span><strong>{shared ? `${hours || "0.00"} FH / ${cycles || "0"} FC` : "0.00 FH / 0 FC"}</strong></div>
                    <label className="daily-util-override-toggle"><input type="checkbox" checked={Boolean(override?.enabled)} onChange={(event) => updateOverride(id, { enabled: event.target.checked })} />Override</label>
                    {override?.enabled ? (
                      <div className="daily-util-override-fields">
                        <input className="input" value={override.hours} onChange={(event) => updateOverride(id, { hours: event.target.value })} aria-label={`${component.component_position} hours`} />
                        <input className="input" type="number" min={0} step={1} value={override.cycles} onChange={(event) => updateOverride(id, { cycles: event.target.value })} aria-label={`${component.component_position} cycles`} />
                        <input className="input" value={override.reason} onChange={(event) => updateOverride(id, { reason: event.target.value })} placeholder="Reason for different exposure" />
                      </div>
                    ) : null}
                  </div>
                );
              })}
              {!context?.installed_components.length ? <div className="daily-util-empty">No installed components are configured. Complete aircraft induction before daily posting.</div> : null}
            </div>
          </article>
        </section>

        <section className="card daily-util-preview-card">
          <div className="daily-util-section-heading">
            <div><span>3</span><h2>Calculated posting preview</h2></div>
            <div className="daily-util-actions">
              <button className="btn btn-secondary" type="button" onClick={() => void runPreview()} disabled={working !== null}>{working === "preview" ? "Calculating…" : "Preview allocation"}</button>
              <button className="btn btn-secondary" type="button" onClick={() => void saveDraft()} disabled={working !== null || !payload}>{working === "draft" ? "Saving…" : "Save draft"}</button>
              <button className="btn btn-primary" type="button" onClick={() => void postEntry()} disabled={working !== null || !payload || Boolean(preview && !preview.can_post)}>{working === "post" ? "Posting…" : "Post daily utilization"}</button>
            </div>
          </div>
          {preview?.blockers.length ? <div className="alert alert--danger"><strong>Posting blocked.</strong> {preview.blockers.join(" · ")}</div> : null}
          {displayRows.length ? (
            <div className="table-wrapper">
              <table className="table planning-table daily-util-preview-table">
                <thead><tr><th>Target</th><th>Basis</th><th>Before</th><th>Daily increase</th><th>After posting</th><th>Control</th></tr></thead>
                <tbody>
                  {displayRows.map((row) => (
                    <tr key={`${row.target_type}-${row.component_id ?? "airframe"}`}>
                      <td><strong>{row.component_position}</strong><small>{row.target_type}</small></td>
                      <td>{exposureLabel(row)}</td>
                      <td>{formatHours(row.before_hours)} FH<small>{formatCycles(row.before_cycles)} FC</small></td>
                      <td><strong>+{formatHours(row.hours_delta)} FH</strong><small>+{formatCycles(row.cycles_delta)} FC</small></td>
                      <td>{formatHours(row.after_hours)} FH<small>{formatCycles(row.after_cycles)} FC</small></td>
                      <td>{row.baseline_missing ? <span className="badge badge--danger">Baseline missing</span> : <span className="badge badge--success">Ready</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <div className="daily-util-empty">Enter the day’s utilization and preview the allocation before posting.</div>}
        </section>

        <section className="card daily-util-history">
          <div className="daily-util-section-heading"><div><span>4</span><h2>Recent daily postings</h2></div><small>{entries.length} record(s)</small></div>
          {entries.length ? (
            <div className="table-wrapper"><table className="table planning-table"><thead><tr><th>Date</th><th>Tech log</th><th>FH</th><th>FC</th><th>Status</th><th>Posted</th></tr></thead><tbody>{entries.map((row) => <tr key={row.id}><td>{row.operation_date}</td><td><strong>{row.techlog_no}</strong><small>{row.station || "No station"}</small></td><td>{formatHours(row.flight_hours)}</td><td>{formatCycles(row.cycles)}</td><td><span className={`badge ${row.status === "POSTED" ? "badge--success" : "badge--info"}`}>{row.status}</span></td><td>{row.posted_at ? new Date(row.posted_at).toLocaleString() : "Draft"}</td></tr>)}</tbody></table></div>
          ) : <div className="daily-util-empty">No daily ledger entries have been created for this aircraft.</div>}
        </section>
      </div>
    </DepartmentLayout>
  );
};

export { DailyAircraftUtilisationPage };
export default DailyAircraftUtilisationPage;
