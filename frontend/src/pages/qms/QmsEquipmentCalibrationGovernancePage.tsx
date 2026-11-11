import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import DepartmentLayout from "../../components/Layout/DepartmentLayout";
import { getCachedUser } from "../../services/auth";
import {
  createCalibrationAsset, dispositionOutOfTolerance, getCalibrationParticipants,
  getInventorySerialChoices, listCalibrationAssets, readCalibrationAsset,
  releaseCalibratedEquipment, reportOutOfTolerance, submitCalibration, verifyCalibration,
  type CalibratedAsset, type EquipmentDetail,
} from "../../services/qmsEquipment";
import "./qms-management-review.css";

const split = (text: string) => text.split("\n").map((entry) => entry.trim()).filter(Boolean);
const message = (failure: unknown) => failure instanceof Error ? failure.message : "Equipment transaction failed.";
export default function QmsEquipmentCalibrationGovernancePage() {
  const { amoCode = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const assetId = params.get("asset") || "";
  const userId = getCachedUser()?.id || "";
  const [list, setList] = useState<Array<CalibratedAsset & { eligibility: { eligible: boolean; reason: string } }>>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [detail, setDetail] = useState<EquipmentDetail | null>(null);
  const [people, setPeople] = useState<Array<{ id: string; name: string }>>([]);
  const [serials, setSerials] = useState<Array<{ id: number; serial: string; part_number: string }>>([]);
  const [serialSearch, setSerialSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(true);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [assetRef, setAssetRef] = useState("");
  const [inventorySerial, setInventorySerial] = useState("");
  const [owner, setOwner] = useState("");
  const [due, setDue] = useState("");
  const [traceability, setTraceability] = useState("");
  const [calTitle, setCalTitle] = useState("");
  const [certNo, setCertNo] = useState("");
  const [lab, setLab] = useState("");
  const [standard, setStandard] = useState("");
  const [calDate, setCalDate] = useState("");
  const [nextDue, setNextDue] = useState("");
  const [result, setResult] = useState<"IN_TOLERANCE" | "OUT_OF_TOLERANCE">("IN_TOLERANCE");
  const [notes, setNotes] = useState("");
  const [evidence, setEvidence] = useState("");
  const [decisionReason, setDecisionReason] = useState("");
  const [ootDesc, setOotDesc] = useState("");
  const [ootDate, setOotDate] = useState("");
  const [lastGood, setLastGood] = useState("");
  const [affected, setAffected] = useState("");
  const [eventId, setEventId] = useState("");
  const [impact, setImpact] = useState("");
  const [disposition, setDisposition] = useState<"RECALIBRATE" | "REPAIR" | "SCRAP" | "NO_ADVERSE_IMPACT">("RECALIBRATE");
  const [releaseReason, setReleaseReason] = useState("");

  const refresh = useCallback(async () => {
    if (!amoCode) return;
    const [page, staff, chosen] = await Promise.all([
      listCalibrationAssets(amoCode, offset), getCalibrationParticipants(amoCode),
      assetId ? readCalibrationAsset(amoCode, assetId) : Promise.resolve(null),
    ]);
    setList(page.items); setTotal(page.total); setPeople(staff.items); setDetail(chosen);
  }, [amoCode, offset, assetId]);
  useEffect(() => {
    let active = true;
    setLoading(true); setError("");
    refresh().catch((failure) => { if (active) setError(message(failure)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [refresh]);
  useEffect(() => {
    let active = true;
    if (!amoCode) return;
    getInventorySerialChoices(amoCode, serialSearch).then((result) => {
      if (active) setSerials(result.items);
    }).catch((failure) => { if (active) setError(message(failure)); });
    return () => { active = false; };
  }, [amoCode, serialSearch]);

  const action = async (fn: () => Promise<unknown>, notice: string) => {
    if (busy) return;
    setBusy(true); setError(""); setSuccess("");
    try { await fn(); await refresh(); setSuccess(notice); }
    catch (failure) { setError(message(failure)); }
    finally { setBusy(false); }
  };
  const choose = (id: string) => {
    setParams((old) => {
      const current = new URLSearchParams(old);
      if (id) current.set("asset", id); else current.delete("asset");
      return current;
    });
  };
  const create = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void action(async () => {
      const response = await createCalibrationAsset(amoCode, {
        title: title.trim(), description: description.trim(),
        asset_reference: assetRef.trim(), inventory_serial_id: inventorySerial ? Number(inventorySerial) : null,
        owner_user_id: owner, calibration_due: due, traceability_policy: traceability.trim(),
      });
      choose(response.asset.id);
      setTitle(""); setDescription(""); setAssetRef("");
    }, "Equipment registered quarantined; proof and independent certificate verification are required.");
  };
  const row = detail?.asset;
  const version = row?.payload.version || 0;
  const pending = detail?.calibrations.find((cal) => cal.status === "PENDING_VERIFICATION");
  const openEvents = detail?.out_of_tolerance.filter((item) => item.status === "OPEN") || [];
  const disposedEvents = detail?.out_of_tolerance.filter((item) => item.status === "DISPOSITION_RECORDED") || [];
  const eligible = detail?.eligibility.eligible ?? false;

  return <DepartmentLayout amoCode={amoCode} activeDepartment="quality">
    <main className="qms-review">
      <header className="qms-review__header"><div><p>QUALITY MEASUREMENT ASSURANCE</p><h1>Equipment and Calibration</h1>
        <span>Verified certificates, overdue restrictions, quarantine, out-of-tolerance impact and independent release.</span></div>
      </header>
      {error ? <div className="qms-review__error" role="alert">{error} <button type="button" disabled={busy} onClick={() => void refresh()}>Reload</button></div> : null}
      {success ? <p role="status" className="qms-review__success">{success}</p> : null}
      <div className="qms-review__grid"><div>
        <section className="qms-review__panel"><h2>Controlled assets</h2>
          {loading ? <p role="status">Loading equipment status…</p> : null}
          <div className="qms-review__meeting-list">
            {list.map((item) => <button key={item.id} type="button" className={assetId === item.id ? "selected" : ""}
              aria-current={assetId === item.id ? "true" : undefined} onClick={() => choose(item.id)}>
              <strong>{item.title}</strong><small>{item.eligibility.eligible ? "SERVICEABLE" : item.eligibility.reason} · Due {item.due_date || "Not verified"}</small>
            </button>)}
          </div>
          <div className="qms-review__pager">
            <button type="button" disabled={offset === 0 || busy} onClick={() => setOffset(Math.max(0, offset - 25))}>Previous</button>
            <span>{total ? offset + 1 : 0}–{Math.min(offset + 25, total)} of {total}</span>
            <button type="button" disabled={offset + 25 >= total || busy} onClick={() => setOffset(offset + 25)}>Next</button>
          </div>
        </section>
        <form className="qms-review__panel qms-review__form" onSubmit={create}>
          <h3>Register equipment (quarantined initially)</h3>
          <label>Asset title<input required minLength={4} value={title} onChange={(e) => setTitle(e.target.value)} /></label>
          <label>Measuring equipment and purpose<textarea minLength={8} required value={description} onChange={(e) => setDescription(e.target.value)} /></label>
          <label>Equipment reference<input required minLength={2} value={assetRef} onChange={(e) => setAssetRef(e.target.value)} /></label>
          <label>Search Inventory serial numbers<input value={serialSearch} onChange={(e) => setSerialSearch(e.target.value)} /></label>
          <label>Authoritative Inventory serial (optional)<select value={inventorySerial} onChange={(e) => setInventorySerial(e.target.value)}>
            <option value="">Equipment without inventory serial</option>
            {serials.map((serial) => <option key={serial.id} value={serial.id}>{serial.part_number} / {serial.serial}</option>)}
          </select></label>
          <label>Equipment custodian<select required value={owner} onChange={(e) => setOwner(e.target.value)}>
            <option value="">Choose custodian</option>{people.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}
          </select></label>
          <label>Next calibration due<input required type="date" value={due} onChange={(e) => setDue(e.target.value)} /></label>
          <label>Traceability or calibration policy<textarea minLength={8} required value={traceability} onChange={(e) => setTraceability(e.target.value)} /></label>
          <button type="submit" disabled={busy || !owner}>Register in quarantine</button>
        </form>
      </div>
      {!row ? <div className="qms-review__panel">Select equipment to verify its calibration and impact history.</div> :
      <div>
        <section className="qms-review__panel">
          <h2>{row.title}</h2><p>{row.description}</p>
          <p>Status: <strong>{row.status}</strong> · Version {version} · Due {row.due_date || "Unknown"} · Inventory serial {row.payload.inventory_serial_id || "Not linked"}</p>
          <p role="status"><strong>{eligible ? "Eligible for governed use" : "NOT ELIGIBLE FOR USE"}</strong> · {detail?.eligibility.reason}</p>
          <p>Equipment eligibility is a server-side decision. Maintenance and Inventory assignment consumers must use the eligible/denied response, not infer serviceability from a displayed certificate.</p>
        </section>
        <div className="qms-review__record-grid">
          <section className="qms-review__records"><h3>Calibration history</h3>
            {detail?.calibrations.map((item) => <article key={item.id}><strong>{item.title} · {item.status}</strong>
              <p>{item.description}</p><small>{item.payload.certificate_number} · {item.payload.result}</small></article>)}
          </section>
          <section className="qms-review__records"><h3>Verified certificates</h3>
            {detail?.certificates.map((item) => <article key={item.id}><strong>{item.title} · {item.status}</strong>
              <small>Reference: {item.payload.certificate_evidence_ids?.join(", ")}</small></article>)}
          </section>
          <section className="qms-review__records"><h3>Out-of-tolerance history</h3>
            {detail?.out_of_tolerance.map((item) => <article key={item.id}><strong>{item.title} · {item.status}</strong>
              <p>{item.description}</p><small>Disposition: {item.payload.disposition || "Awaiting independent impact assessment"}</small></article>)}
          </section>
        </div>
        <div className="qms-review__forms qms-review__panel">
          <form className="qms-review__form" onSubmit={(event) => { event.preventDefault(); void action(() => submitCalibration(amoCode, row.id, {
            expected_version: version, title: calTitle.trim(), certificate_number: certNo.trim(),
            certificate_evidence_ids: split(evidence), calibration_date: calDate,
            next_due: nextDue, issuing_lab: lab.trim(), standard_reference: standard.trim(),
            result, notes: notes.trim(),
          }), "Calibration submitted for independent verification; unsafe outcomes remain quarantined."); }}>
            <h3>Submit calibration evidence</h3>
            <label>Calibration activity<input required minLength={4} value={calTitle} onChange={(e) => setCalTitle(e.target.value)} /></label>
            <label>Certificate number<input required minLength={3} value={certNo} onChange={(e) => setCertNo(e.target.value)} /></label>
            <label>Laboratory / provider<input required minLength={3} value={lab} onChange={(e) => setLab(e.target.value)} /></label>
            <label>Standard / traceability reference<input required minLength={3} value={standard} onChange={(e) => setStandard(e.target.value)} /></label>
            <label>Date calibrated<input type="date" required value={calDate} onChange={(e) => setCalDate(e.target.value)} /></label>
            <label>Next due<input type="date" required value={nextDue} onChange={(e) => setNextDue(e.target.value)} /></label>
            <label>Test result<select value={result} onChange={(e) => setResult(e.target.value as "IN_TOLERANCE" | "OUT_OF_TOLERANCE")}>
              <option value="IN_TOLERANCE">In tolerance</option><option value="OUT_OF_TOLERANCE">Out of tolerance (quarantine)</option>
            </select></label>
            <label>Notes<textarea minLength={8} required value={notes} onChange={(e) => setNotes(e.target.value)} /></label>
            <label>Retained certificate evidence IDs<textarea required value={evidence} onChange={(e) => setEvidence(e.target.value)} /></label>
            <button type="submit" disabled={busy || Boolean(pending) || !split(evidence).length}>Submit certification</button>
          </form>
          <form className="qms-review__form" onSubmit={(event) => { event.preventDefault(); if (!pending) return;
            void action(() => verifyCalibration(amoCode, row.id, {
              expected_version: version, calibration_id: pending.id, accepted: true, rationale: decisionReason.trim(),
            }), "Independent calibration verification recorded.");}}>
            <h3>Independently verify submitted calibration</h3>
            {pending ? <p>{pending.title} · Author {pending.created_by}</p> : <p>No pending certificate.</p>}
            <label>Decision rationale<textarea minLength={12} required value={decisionReason} onChange={(e) => setDecisionReason(e.target.value)} /></label>
            <button type="submit" disabled={busy || !pending || pending.created_by === userId || decisionReason.trim().length < 12}>Accept certificate</button>
            <button type="button" disabled={busy || !pending || pending.created_by === userId || decisionReason.trim().length < 12}
              onClick={() => pending && void action(() => verifyCalibration(amoCode, row.id, {
                expected_version: version, calibration_id: pending.id, accepted: false, rationale: decisionReason.trim(),
              }), "Certificate rejected; equipment remains quarantined.")}>Reject certificate</button>
          </form>
        </div>
        <div className="qms-review__forms qms-review__panel">
          <form className="qms-review__form" onSubmit={(event) => {event.preventDefault(); void action(() =>
            reportOutOfTolerance(amoCode, row.id, {
              expected_version: version, description: ootDesc.trim(), detected_on: ootDate,
              last_known_good: lastGood || null, affected_work_references: split(affected),
              evidence_record_ids: split(evidence),
            }), "Out-of-tolerance event recorded; equipment quarantined.");}}>
            <h3>Quarantine / report out-of-tolerance</h3>
            <label>Detected concern<textarea minLength={12} required value={ootDesc} onChange={(e) => setOotDesc(e.target.value)} /></label>
            <label>Detected on<input type="date" required value={ootDate} onChange={(e) => setOotDate(e.target.value)} /></label>
            <label>Last known good<input type="date" value={lastGood} onChange={(e) => setLastGood(e.target.value)} /></label>
            <label>Potentially affected maintenance records (one per line)<textarea value={affected} onChange={(e) => setAffected(e.target.value)} /></label>
            <label>Retained evidence IDs<textarea required value={evidence} onChange={(e) => setEvidence(e.target.value)} /></label>
            <button type="submit" disabled={busy || !split(evidence).length}>Record and quarantine</button>
          </form>
          <form className="qms-review__form" onSubmit={(event) => {event.preventDefault(); void action(() =>
            dispositionOutOfTolerance(amoCode, row.id, {
              expected_version: version, event_id: eventId,
              impact_assessment: impact.trim(), disposition,
              affected_work_references: split(affected), evidence_record_ids: split(evidence),
            }), "Impact disposition documented. Physical quarantine remains until separately released.");}}>
            <h3>Independent out-of-tolerance impact disposition</h3>
            <label>Open event<select required value={eventId} onChange={(e) => setEventId(e.target.value)}>
              <option value="">Choose unresolved event</option>
              {openEvents.map((item) => <option key={item.id} value={item.id}>{item.title} · {item.id}</option>)}
            </select></label>
            <label>Assessment of affected work<textarea minLength={20} required value={impact} onChange={(e) => setImpact(e.target.value)} /></label>
            <label>Disposition<select value={disposition} onChange={(e) => setDisposition(e.target.value as typeof disposition)}>
              <option value="RECALIBRATE">Recalibrate</option><option value="REPAIR">Repair</option>
              <option value="SCRAP">Scrap</option><option value="NO_ADVERSE_IMPACT">No adverse impact</option>
            </select></label>
            <label>Affected work references<textarea value={affected} onChange={(e) => setAffected(e.target.value)} /></label>
            <label>Evidence IDs<textarea required value={evidence} onChange={(e) => setEvidence(e.target.value)} /></label>
            <button type="submit" disabled={busy || !eventId || impact.trim().length < 20 || !split(evidence).length}>Record impact disposition</button>
          </form>
        </div>
        {row.status === "QUARANTINED" && disposedEvents.length ? <form className="qms-review__panel qms-review__form"
          onSubmit={(event) => {event.preventDefault(); void action(() =>
            releaseCalibratedEquipment(amoCode, row.id, {
              expected_version: version, rationale: releaseReason.trim(), closure_evidence_ids: split(evidence),
            }), "Independent release recorded after in-date post-event calibration.");}}>
          <h3>Controlled return to service</h3>
          <p>All out-of-tolerance events must have an independent disposition and a current verified calibration dated no earlier than the event.</p>
          <label>Release rationale<textarea minLength={12} required value={releaseReason} onChange={(e) => setReleaseReason(e.target.value)} /></label>
          <label>Retained release evidence IDs<textarea required value={evidence} onChange={(e) => setEvidence(e.target.value)} /></label>
          <button type="submit" disabled={busy || openEvents.length > 0 || row.owner_user_id === userId || !split(evidence).length}>
            Independently release equipment</button>
        </form> : null}
      </div>}
    </main>
  </DepartmentLayout>;
}
