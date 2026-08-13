import { useEffect, useMemo, useState } from "react";
import { Plane, Plus, RefreshCw, Trash2 } from "lucide-react";

import { listAircraft, type AircraftRead } from "../../../services/fleet";
import {
  createRosterAircraftAllocation,
  deleteRosterAircraftAllocation,
  listRosterAircraftAllocations,
  type RosterAircraftAllocationRead,
  type RosterAircraftAllocationType,
} from "../../../services/rosteringAircraftAllocations";
import { errorMessage } from "../rosterUi";

type Props = {
  assignmentId: string;
  editable: boolean;
};

const ALLOCATION_TYPES: Array<{ value: RosterAircraftAllocationType; label: string }> = [
  { value: "FLIGHT_ENGINEERING", label: "Flight engineering" },
  { value: "MAINTENANCE_SUPPORT", label: "Maintenance support" },
  { value: "OTHER", label: "Other" },
];

export function AircraftAllocationEditor({ assignmentId, editable }: Props) {
  const [aircraft, setAircraft] = useState<AircraftRead[]>([]);
  const [allocations, setAllocations] = useState<RosterAircraftAllocationRead[]>([]);
  const [serialNumber, setSerialNumber] = useState("");
  const [allocationType, setAllocationType] = useState<RosterAircraftAllocationType>("FLIGHT_ENGINEERING");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    if (assignmentId.startsWith("offline-")) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [fleetRows, allocationRows] = await Promise.all([
        listAircraft({ is_active: true }),
        listRosterAircraftAllocations(assignmentId),
      ]);
      setAircraft(fleetRows);
      setAllocations(allocationRows);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [assignmentId]);

  const availableAircraft = useMemo(() => {
    const allocated = new Set(allocations.map((row) => row.aircraft_serial_number));
    return aircraft.filter((row) => !allocated.has(row.serial_number));
  }, [aircraft, allocations]);

  useEffect(() => {
    if (serialNumber && !availableAircraft.some((row) => row.serial_number === serialNumber)) {
      setSerialNumber("");
    }
  }, [availableAircraft, serialNumber]);

  const add = async () => {
    if (!serialNumber || busy) return;
    setBusy(true);
    setError(null);
    try {
      const row = await createRosterAircraftAllocation(assignmentId, {
        aircraft_serial_number: serialNumber,
        allocation_type: allocationType,
        notes: notes.trim() || null,
      });
      setAllocations((current) => [...current, row]);
      setSerialNumber("");
      setNotes("");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (allocation: RosterAircraftAllocationRead) => {
    if (!allocation.can_delete || busy) return;
    setBusy(true);
    setError(null);
    try {
      await deleteRosterAircraftAllocation(assignmentId, allocation.id);
      setAllocations((current) => current.filter((row) => row.id !== allocation.id));
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="wr-span-2" aria-label="Aircraft allocation">
      <div className="wr-section-heading">
        <div>
          <span className="wr-eyebrow">Aircraft allocation</span>
          <h3>Assigned aircraft</h3>
        </div>
        <button type="button" className="wr-icon-button" onClick={() => void load()} disabled={loading || busy} aria-label="Refresh aircraft allocations">
          <RefreshCw size={15} className={loading ? "is-spinning" : ""} />
        </button>
      </div>

      {loading ? <div className="wr-inline-warning"><RefreshCw size={14} className="is-spinning" /> Loading aircraft allocation…</div> : null}
      {!loading && allocations.length === 0 ? <div className="wr-success-note"><Plane size={15} /> No aircraft assigned to this duty.</div> : null}
      {allocations.map((allocation) => (
        <div key={allocation.id} className="wr-inline-warning">
          <Plane size={15} />
          <span>
            <strong>{allocation.aircraft_display_code || allocation.aircraft_registration}</strong>
            {allocation.aircraft_display_code !== allocation.aircraft_registration ? ` · ${allocation.aircraft_registration}` : ""}
            {` · ${allocation.allocation_type.replace(/_/g, " ").toLowerCase()}`}
            {allocation.notes ? ` · ${allocation.notes}` : ""}
          </span>
          {editable && allocation.can_delete ? (
            <button type="button" className="wr-icon-button" onClick={() => void remove(allocation)} disabled={busy} aria-label={`Remove ${allocation.aircraft_registration}`}>
              <Trash2 size={15} />
            </button>
          ) : null}
        </div>
      ))}

      {editable && !assignmentId.startsWith("offline-") ? (
        <div className="wr-form-grid">
          <label>
            <span>Aircraft</span>
            <select value={serialNumber} onChange={(event) => setSerialNumber(event.target.value)} disabled={busy || availableAircraft.length === 0}>
              <option value="">Select aircraft</option>
              {availableAircraft.map((row) => <option key={row.serial_number} value={row.serial_number}>{row.registration} · {row.model || row.template || row.serial_number}</option>)}
            </select>
          </label>
          <label>
            <span>Allocation purpose</span>
            <select value={allocationType} onChange={(event) => setAllocationType(event.target.value as RosterAircraftAllocationType)} disabled={busy}>
              {ALLOCATION_TYPES.map((row) => <option key={row.value} value={row.value}>{row.label}</option>)}
            </select>
          </label>
          <label className="wr-span-2"><span>Aircraft note</span><input value={notes} onChange={(event) => setNotes(event.target.value)} maxLength={4000} disabled={busy} placeholder="Optional flight, sector or support note" /></label>
          <div className="wr-span-2 wr-actions">
            <button type="button" className="wr-button wr-button--secondary" onClick={() => void add()} disabled={busy || !serialNumber}>
              <Plus size={15} /> Assign aircraft
            </button>
          </div>
        </div>
      ) : null}
      {error ? <div className="wr-inline-error">{error}</div> : null}
    </section>
  );
}
