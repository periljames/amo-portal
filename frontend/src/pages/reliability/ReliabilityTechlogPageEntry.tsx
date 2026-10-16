import React, { useEffect, useMemo, useState } from "react";
import { apiRequest } from "../../services/apiClient";
import ReliabilityTechlogEvidence from "./ReliabilityTechlogEvidence";

type Aircraft = { serial_number: string; registration: string; is_active: boolean };
type EngineHint = { engine_position: string; engine_serial_number: string; installation_ref: string; last_observed: string };
type Leg = { number: number; from_airport: string; to_airport: string; flight_hours: string;
  left_oil_level: string; right_oil_level: string; comment: string };
type Engine = { position: "1" | "2"; engine_serial_number: string; installation_ref: string;
  observation: "TOP_UP" | "CHECK_ZERO" | "MISSING"; quantity_added: string; original_unit: string;
  oil_specification: string; reference_method: string; reference_level: string };
type Preview = { candidates: Array<{ engine_position: string; event_type: string; oil_quantity: number | null;
  flight_hours: number; source_scope: string; techsheet_ref: string }>; warnings: string[] };
type SourceType = "PAPER_TECHSHEET" | "REVIEWED_OCR";
const today = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
const blankEngine = (position: "1" | "2"): Engine => ({
  position, engine_serial_number: "", installation_ref: "", observation: "MISSING",
  quantity_added: "", original_unit: "", oil_specification: "", reference_method: "", reference_level: "",
});
const blankLeg = (number: number): Leg => ({ number, from_airport: "", to_airport: "", flight_hours: "",
  left_oil_level: "", right_oil_level: "", comment: "" });
const numeric = (v: string): number | null => v.trim() ? Number(v) : null;
const durationHours = (value: string): number | null => {
  const text = value.trim();
  if (!text) return null;
  const match = /^(\d+):([0-5]\d)$/.exec(text);
  if (match) return Number(match[1]) + Number(match[2]) / 60;
  if (!/^\d+(?:\.\d+)?$/.test(text)) return null;
  const number = Number(text);
  return Number.isFinite(number) ? number : null;
};
const nonempty = (v: string): string | null => v.trim() || null;
const sourceError = (e: unknown) => e instanceof Error ? e.message : String(e);
type PageEdit = { aircraft: string; techsheet: string };
type RestoredPage = {
  aircraft_serial_number: string; techsheet_ref: string; event_date: string;
  source_evidence_ref: string; source_type: SourceType;
  legs: Array<{ number: number; from_airport: string | null; to_airport: string | null;
    flight_hours: number; left_oil_level: string | null; right_oil_level: string | null; comment: string | null }>;
  page_flight_hours: number;
  ttaf_brought_forward: number | null; ttaf_updated: number | null;
  tcsn_brought_forward: number | null; tcsn_updated: number | null;
  maintenance_complete: "YES" | "NO" | "UNKNOWN"; maintenance_release_ref: string | null;
  check_24h_ref: string | null; defect_references: string[]; deferred_defect_references: string[];
  apu_oil_added: number | null; apu_oil_unit: string | null;
  engines: Array<{ position: "1" | "2"; engine_serial_number: string; installation_ref: string;
    observation: "TOP_UP" | "CHECK_ZERO" | "MISSING"; quantity_added: number | null;
    original_unit: string | null; oil_specification: string | null;
    reference_method: string | null; reference_level: string | null }>;
};
type Props = { aircraftOptions: Aircraft[]; canCreate: boolean; onSaved: () => Promise<unknown> | void;
  editPage: PageEdit | null; onExitEdit: () => void };

export default function ReliabilityTechlogPageEntry({ aircraftOptions, canCreate, onSaved, editPage, onExitEdit }: Props): React.ReactElement {
  const [aircraft, setAircraft] = useState("");
  const [pageNumber, setPageNumber] = useState("");
  const [eventDate, setEventDate] = useState(today);
  const [sourceEvidence, setSourceEvidence] = useState("");
  const [sourceType, setSourceType] = useState<SourceType>("PAPER_TECHSHEET");
  const [legs, setLegs] = useState<Leg[]>([blankLeg(1)]);
  const [totalFlightHours, setTotalFlightHours] = useState("");
  const [ttafBefore, setTtafBefore] = useState("");
  const [ttafAfter, setTtafAfter] = useState("");
  const [tcsnBefore, setTcsnBefore] = useState("");
  const [tcsnAfter, setTcsnAfter] = useState("");
  const [maintenanceComplete, setMaintenanceComplete] = useState<"YES" | "NO" | "UNKNOWN">("UNKNOWN");
  const [maintenanceRelease, setMaintenanceRelease] = useState("");
  const [check24h, setCheck24h] = useState("");
  const [defectRefs, setDefectRefs] = useState("");
  const [deferredRefs, setDeferredRefs] = useState("");
  const [apuOil, setApuOil] = useState("");
  const [apuOilUnit, setApuOilUnit] = useState("");
  const [twinEngine, setTwinEngine] = useState(true);
  const [left, setLeft] = useState<Engine>(blankEngine("1"));
  const [right, setRight] = useState<Engine>(blankEngine("2"));
  const [hints, setHints] = useState<EngineHint[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [correctionReason, setCorrectionReason] = useState("");
  const [sourceLoading, setSourceLoading] = useState(false);

  useEffect(() => {
    if (!editPage) return;
    let active = true;
    setSourceLoading(true); setError(""); setPreview(null); setConfirmed(false);
    void apiRequest<RestoredPage>("/reliability/octm/techlog-pages/detail?aircraft=" +
      encodeURIComponent(editPage.aircraft) + "&techsheet_ref=" + encodeURIComponent(editPage.techsheet),
      { cacheTtlMs: 0 })
      .then((page) => {
        if (!active) return;
        setAircraft(page.aircraft_serial_number); setPageNumber(page.techsheet_ref);
        setEventDate(page.event_date); setSourceEvidence(page.source_evidence_ref);
        setSourceType(page.source_type);
        setLegs(page.legs.map((leg) => ({
          number: leg.number, from_airport: leg.from_airport || "", to_airport: leg.to_airport || "",
          flight_hours: String(leg.flight_hours), left_oil_level: leg.left_oil_level || "",
          right_oil_level: leg.right_oil_level || "", comment: leg.comment || "",
        })));
        setTotalFlightHours(String(page.page_flight_hours));
        setTtafBefore(page.ttaf_brought_forward === null ? "" : String(page.ttaf_brought_forward));
        setTtafAfter(page.ttaf_updated === null ? "" : String(page.ttaf_updated));
        setTcsnBefore(page.tcsn_brought_forward === null ? "" : String(page.tcsn_brought_forward));
        setTcsnAfter(page.tcsn_updated === null ? "" : String(page.tcsn_updated));
        setMaintenanceComplete(page.maintenance_complete);
        setMaintenanceRelease(page.maintenance_release_ref || "");
        setCheck24h(page.check_24h_ref || "");
        setDefectRefs(page.defect_references.join(", "));
        setDeferredRefs(page.deferred_defect_references.join(", "));
        setApuOil(page.apu_oil_added === null ? "" : String(page.apu_oil_added));
        setApuOilUnit(page.apu_oil_unit || "");
        setTwinEngine(page.engines.some((engine) => engine.position === "2"));
        for (const record of page.engines) {
          const result: Engine = {
            ...record, quantity_added: record.quantity_added === null ? "" : String(record.quantity_added),
            original_unit: record.original_unit || "", oil_specification: record.oil_specification || "",
            reference_method: record.reference_method || "", reference_level: record.reference_level || "",
          };
          if (record.position === "1") setLeft(result);
          else setRight(result);
        }
      }).catch((cause) => { if (active) setError(sourceError(cause)); })
      .finally(() => { if (active) setSourceLoading(false); });
    return () => { active = false; };
  }, [editPage]);

  const invalidate = () => { setPreview(null); setConfirmed(false); setError(""); setSuccess(""); };
  const patchLeg = (index: number, key: keyof Leg, value: string) => {
    invalidate();
    setLegs((old) => old.map((row, i) => i === index ? { ...row, [key]: value } : row));
  };
  const patchEngine = (position: "1" | "2", key: keyof Engine, value: string) => {
    invalidate();
    const setter = position === "1" ? setLeft : setRight;
    setter((old) => ({ ...old, [key]: value }));
  };
  useEffect(() => {
    if (!aircraft) { setHints([]); return; }
    let active = true;
    void apiRequest<EngineHint[]>("/reliability/octm/engine-hints?aircraft=" +
      encodeURIComponent(aircraft) + "&event_date=" + eventDate)
      .then((list) => { if (active) setHints(list); })
      .catch(() => { if (active) setHints([]); });
    return () => { active = false; };
  }, [aircraft, eventDate]);

  const sumHours = useMemo(() => legs.reduce((sum, leg) => sum +
    (durationHours(leg.flight_hours) ?? 0), 0), [legs]);
  const invalidDuration = legs.some((leg) => durationHours(leg.flight_hours) === null) ||
    (totalFlightHours.trim() !== "" && durationHours(totalFlightHours) === null);
  const pageHoursMismatch = totalFlightHours.trim() !== "" && durationHours(totalFlightHours) !== null &&
    Math.abs(sumHours - (durationHours(totalFlightHours) ?? 0)) > 0.02;
  const build = () => ({
    aircraft_serial_number: aircraft, techsheet_ref: pageNumber.trim(), event_date: eventDate,
    source_evidence_ref: sourceEvidence.trim(), source_type: sourceType,
    legs: legs.map((leg) => ({
      ...leg, flight_hours: durationHours(leg.flight_hours),
      from_airport: nonempty(leg.from_airport), to_airport: nonempty(leg.to_airport),
      left_oil_level: nonempty(leg.left_oil_level), right_oil_level: nonempty(leg.right_oil_level),
      comment: nonempty(leg.comment),
    })),
    page_flight_hours: durationHours(totalFlightHours),
    ttaf_brought_forward: numeric(ttafBefore), ttaf_updated: numeric(ttafAfter),
    tcsn_brought_forward: numeric(tcsnBefore), tcsn_updated: numeric(tcsnAfter),
    maintenance_complete: maintenanceComplete, maintenance_release_ref: nonempty(maintenanceRelease),
    check_24h_ref: nonempty(check24h),
    defect_references: defectRefs.split(",").map((v) => v.trim()).filter(Boolean),
    deferred_defect_references: deferredRefs.split(",").map((v) => v.trim()).filter(Boolean),
    apu_oil_added: numeric(apuOil), apu_oil_unit: nonempty(apuOilUnit),
    engines: (twinEngine ? [left, right] : [left]).map((engine) => ({
      ...engine, quantity_added: engine.observation === "TOP_UP" ? numeric(engine.quantity_added) : null,
      original_unit: engine.observation === "TOP_UP" ? nonempty(engine.original_unit) : null,
      oil_specification: nonempty(engine.oil_specification),
      reference_method: nonempty(engine.reference_method),
      reference_level: nonempty(engine.reference_level),
    })),
  });

  const previewPage = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true); setError(""); setPreview(null); setConfirmed(false);
    try {
      const response = await apiRequest<Preview>("/reliability/octm/techlog-pages/preview", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(build()),
      });
      setPreview(response);
    } catch (cause) { setError(sourceError(cause)); } finally { setBusy(false); }
  };
  const savePage = async () => {
    if (!preview || !confirmed || (editPage && correctionReason.trim().length < 8)) return;
    setBusy(true); setError("");
    try {
      await apiRequest(editPage ? "/reliability/octm/techlog-pages/correct" : "/reliability/octm/techlog-pages", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(editPage ? {
          aircraft_serial_number: editPage.aircraft, techsheet_ref: editPage.techsheet,
          replacement: build(), reason: correctionReason.trim(),
        } : build()),
      });
      setSuccess(editPage
        ? "All affected engine observations were returned to draft; original values are retained in correction history."
        : "Page-level engine observations saved as drafts; these are not verified or included in formal trends.");
      setPreview(null); setConfirmed(false);
      if (editPage) onExitEdit();
      try { await onSaved(); } catch { setError("Entries were saved, but the main register could not refresh. Check the source register before retrying."); }
    } catch (cause) { setError(sourceError(cause)); } finally { setBusy(false); }
  };
  const engineEditor = (data: Engine, label: string) => <fieldset className="octm__engine-fieldset">
    <legend>{label} engine · SL/MCM/1 OIL Added</legend>
    <div className="octm__form">
      <label>Historic engine serial number<input required value={data.engine_serial_number}
        onChange={(event) => patchEngine(data.position, "engine_serial_number", event.target.value)} /></label>
      <label>Confirmed installation reference<input required value={data.installation_ref}
        onChange={(event) => patchEngine(data.position, "installation_ref", event.target.value)} /></label>
      <label>Existing engine hints (not installation proof)<select value="" onChange={(event) => {
        const found = hints[Number(event.target.value)];
        if (found && found.engine_position === data.position) {
          invalidate();
          const setter = data.position === "1" ? setLeft : setRight;
          setter((old) => ({ ...old, engine_serial_number: found.engine_serial_number, installation_ref: found.installation_ref }));
        }
      }}>
        <option value="">Select a previous engine if relevant…</option>
        {hints.filter((h) => h.engine_position === data.position).map((h) => <option
          key={h.engine_serial_number + h.installation_ref} value={hints.indexOf(h)}>
          {h.engine_serial_number} · {h.installation_ref}, last recorded {h.last_observed}</option>)}
      </select></label>
      <label>Source oil-added entry<select value={data.observation}
        onChange={(event) => patchEngine(data.position, "observation", event.target.value)}>
        <option value="MISSING">Not recorded / blank — not zero</option>
        <option value="TOP_UP">Positive oil uplift</option>
        <option value="CHECK_ZERO">Explicitly checked, no oil added</option>
      </select></label>
      {data.observation === "TOP_UP" && <>
        <label>Quantity added (from page)<input required type="number" min="0.001" step="any"
          value={data.quantity_added} onChange={(event) => patchEngine(data.position, "quantity_added", event.target.value)} /></label>
        <label>Original unit (do not assume)<select required value={data.original_unit}
          onChange={(event) => patchEngine(data.position, "original_unit", event.target.value)}>
          <option value="">Choose recorded unit…</option><option value="QT">US quarts</option><option value="L">Litres</option>
          <option value="US_GAL">US gallons</option></select></label>
      </>}
      <label>Oil specification<input value={data.oil_specification}
        onChange={(event) => patchEngine(data.position, "oil_specification", event.target.value)} /></label>
      <label>Reference method / dipstick or sight-glass<input value={data.reference_method}
        onChange={(event) => patchEngine(data.position, "reference_method", event.target.value)} /></label>
      <label>Reference level used consistently<input value={data.reference_level}
        onChange={(event) => patchEngine(data.position, "reference_level", event.target.value)} /></label>
    </div>
  </fieldset>;

  return <section className="octm__panel">
    <h2>{editPage ? "Correct SL/MCM/1 source page" : "Technical Logbook page entry — SL/MCM/1"}</h2>
    {sourceLoading && <p>Loading original page and engine records…</p>}
    {editPage && <p className="octm__hint">All linked engine records will be returned to draft
      if this page is corrected, including an engine with unchanged oil values.</p>}
    <p>Copy the original paper page. Its flight legs have individual engine <strong>oil LEVEL</strong> fields,
      but <strong>OIL ADDED</strong> is one total per engine for the whole page. Do not allocate that oil to a specific leg.
      A blank oil-added box is not a confirmed zero.</p>
    {error && <p className="octm__error" role="alert">{error}</p>}
    {success && <p className="octm__message" role="status">{success}</p>}
    <form onSubmit={(event) => void previewPage(event)}>
      <fieldset>
        <legend>1. Source technical-log page</legend>
        <div className="octm__form">
          <label>Registered aircraft<select required disabled={!!editPage} value={aircraft}
            onChange={(event) => { invalidate(); setAircraft(event.target.value); }}>
            <option value="">Choose aircraft…</option>
            {aircraftOptions.map((item) => <option key={item.serial_number} value={item.serial_number}>
              {item.registration} · {item.serial_number}{item.is_active ? "" : " (historical)"}</option>)}</select></label>
          <label>Page / techsheet number<input required readOnly={!!editPage} maxLength={160} value={pageNumber}
            onChange={(event) => { invalidate(); setPageNumber(event.target.value); }} /></label>
          <label>Date on original page<input type="date" required max={today()} value={eventDate}
            onChange={(event) => { invalidate(); setEventDate(event.target.value); }} /></label>
          <label>Controlled source evidence reference<input required minLength={3} value={sourceEvidence}
            placeholder="DMS / Technical Records document ID"
            onChange={(event) => { invalidate(); setSourceEvidence(event.target.value); }} /></label>
          <label>Source type<select value={sourceType} onChange={(event) => { invalidate(); setSourceType(event.target.value as SourceType); }}>
            <option value="PAPER_TECHSHEET">Original paper techlog</option>
            <option value="REVIEWED_OCR">Human-checked OCR draft</option></select></label>
          <label>Maintenance information complete?<select value={maintenanceComplete}
            onChange={(event) => { invalidate(); setMaintenanceComplete(event.target.value as "YES" | "NO" | "UNKNOWN"); }}>
            <option value="UNKNOWN">Unknown</option><option value="NO">Not complete</option><option value="YES">Confirmed complete</option>
          </select></label>
          <label>CRS / maintenance release record reference<input value={maintenanceRelease}
            onChange={(event) => { invalidate(); setMaintenanceRelease(event.target.value); }} /></label>
          <label>24-hour checks signature/reference<input value={check24h}
            onChange={(event) => { invalidate(); setCheck24h(event.target.value); }} /></label>
        </div>
        <ReliabilityTechlogEvidence aircraft={aircraft} techsheet={pageNumber}
          reference={sourceEvidence} canUpload={canCreate}
          onReference={(reference) => { invalidate(); setSourceEvidence(reference); }} />
      </fieldset>
      <fieldset>
        <legend>2. Flight leg grid (up to nine legs on the original page)</legend>
        <div className="octm__table-wrap"><table><thead><tr><th>Leg</th><th>From</th><th>To</th>
          <th>Flight Time (HH:MM or decimal FH)</th><th>L/H oil level</th><th>R/H oil level</th><th>Comments</th><th></th>
        </tr></thead><tbody>{legs.map((leg, index) => <tr key={leg.number}>
          <td>{leg.number}</td>
          {(["from_airport", "to_airport", "flight_hours", "left_oil_level", "right_oil_level", "comment"] as const)
            .map((field) => <td key={field}><input aria-label={"Leg " + leg.number + " " + field.replaceAll("_", " ")}
              type="text" inputMode={field === "flight_hours" ? "decimal" : undefined}
              placeholder={field === "flight_hours" ? "01:30 or 1.5" : undefined}
              required={field === "flight_hours"}
              value={leg[field]} onChange={(event) => patchLeg(index, field, event.target.value)} /></td>)}
          <td><button type="button" disabled={legs.length === 1}
            onClick={() => { invalidate(); setLegs((rows) => rows.filter((_, i) => i !== index)); }}>Remove</button></td>
        </tr>)}</tbody></table></div>
        <div className="octm__actions">
          <button type="button" className="btn btn-secondary" disabled={legs.length >= 9}
            onClick={() => { invalidate(); setLegs((rows) =>
              [...rows, blankLeg(Math.min(...Array.from({ length: 9 }, (_, i) => i + 1).filter((v) => !rows.some((x) => x.number === v))))].sort((a, b) => a.number - b.number)); }}>
            Add flight leg</button>
        </div>
        <p>Entered Flight Time sum: <strong>{sumHours.toFixed(2)} FH</strong>.
          Do not substitute Airtime, and never infer oil uplift from oil levels.</p>
        <div className="octm__form">
          <label>Page TOTAL Flight Time (HH:MM or decimal FH)<input required type="text" inputMode="decimal" placeholder="03:15 or 3.25"
            value={totalFlightHours} onChange={(event) => { invalidate(); setTotalFlightHours(event.target.value); }} /></label>
          <label>TTAF brought forward<input type="number" min="0" step="any" value={ttafBefore}
            onChange={(event) => { invalidate(); setTtafBefore(event.target.value); }} /></label>
          <label>Updated TTAF<input type="number" min="0" step="any" value={ttafAfter}
            onChange={(event) => { invalidate(); setTtafAfter(event.target.value); }} /></label>
          <label>TCSN brought forward<input type="number" min="0" step="any" value={tcsnBefore}
            onChange={(event) => { invalidate(); setTcsnBefore(event.target.value); }} /></label>
          <label>Updated TCSN<input type="number" min="0" step="any" value={tcsnAfter}
            onChange={(event) => { invalidate(); setTcsnAfter(event.target.value); }} /></label>
        </div>
        {invalidDuration && <p role="alert" className="octm__error">Use HH:MM (minutes 00–59) or nonnegative decimal flight hours for every Flight Time.</p>}
        {pageHoursMismatch && <p role="alert" className="octm__error">Leg Flight Time sum does not match page TOTAL.
          Reconcile against the original technical log.</p>}
      </fieldset>
      <fieldset>
        <legend>3. PAGE-level oil additions (not individual sectors)</legend>
        <label className="octm__continue"><input type="checkbox" checked={twinEngine}
          onChange={(event) => { invalidate(); setTwinEngine(event.target.checked); }} />
          Two engine positions on this aircraft</label>
        {engineEditor(left, "L/H")}
        {twinEngine && engineEditor(right, "R/H")}
        <div className="octm__form">
          <label>APU oil added (separate; never counted as engine oil)<input type="number" min="0" step="any"
            value={apuOil} onChange={(event) => { invalidate(); setApuOil(event.target.value); }} /></label>
          <label>APU oil unit (only when quantity recorded)<select value={apuOilUnit}
            onChange={(event) => { invalidate(); setApuOilUnit(event.target.value); }}>
            <option value="">No APU oil recorded</option><option value="QT">US quarts</option>
            <option value="L">Litres</option><option value="US_GAL">US gallons</option></select></label>
        </div>
      </fieldset>
      <fieldset>
        <legend>4. Source defect / deferred-defect links</legend>
        <p>The Technical Logbook has a defect and rectification table. SL/MCM/1B
          records transferred deferred defects and clearances. References here
          do not constitute rectification, MEL authorization or maintenance release.</p>
        <div className="octm__form">
          <label>Techlog defect references (comma-separated)<input value={defectRefs}
            onChange={(event) => { invalidate(); setDefectRefs(event.target.value); }} /></label>
          <label>Deferred-defect ADD numbers (comma-separated)<input value={deferredRefs}
            onChange={(event) => { invalidate(); setDeferredRefs(event.target.value); }} /></label>
        </div>
      </fieldset>
      <div className="octm__actions">
        <button type="submit" className="btn btn-primary" disabled={busy || !canCreate || pageHoursMismatch || invalidDuration || totalFlightHours.trim() === ""}>
          {busy ? "Validating…" : "Review calculated source drafts"}</button>
      </div>
    </form>
    {editPage && <div className="octm__review">
      <label>Reason for correcting the original page (required)
        <textarea minLength={8} required rows={2} value={correctionReason}
          onChange={(event) => { invalidate(); setCorrectionReason(event.target.value); }} />
      </label>
      <button type="button" className="btn btn-secondary" onClick={onExitEdit}>Cancel page correction</button>
    </div>}
    {preview && <div className="octm__review" role="region" aria-label="Page import confirmation">
      <h3>Page-level draft preview</h3>
      <div className="octm__table-wrap"><table><thead><tr><th>Engine</th><th>Observation</th><th>Oil added</th>
        <th>Flight hours</th><th>Source scope</th></tr></thead><tbody>
        {preview.candidates.map((item) => <tr key={item.engine_position}>
          <td>{item.engine_position}</td><td>{item.event_type}</td>
          <td>{item.oil_quantity ?? "Not recorded"}</td><td>{item.flight_hours}</td>
          <td>{item.source_scope}</td></tr>)}</tbody></table></div>
      <ul>{preview.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
      <label className="octm__continue"><input type="checkbox" checked={confirmed}
        onChange={(event) => setConfirmed(event.target.checked)} />
        I compared this preview with SL/MCM/1 and understand that these are unverified page-level records,
        not individual sector oil additions or a signed maintenance release.</label>
      <button type="button" className="btn btn-primary" disabled={busy || !canCreate || !confirmed || (editPage !== null && correctionReason.trim().length < 8)}
        onClick={() => void savePage()}>{editPage ? "Record page correction and reopen both engine reviews"
          : "Save page as draft for Reliability review"}</button>
    </div>}
  </section>;
}
