import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  CheckCircle2,
  Crosshair,
  Database,
  LocateFixed,
  MapPin,
  RefreshCw,
  Save,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";

import { Button, InlineAlert } from "../../components/UI/Admin";
import {
  approveBaseLocationConsensus,
  clearBaseLocationObservations,
  contributeBaseLocation,
  getBaseLocationConsensus,
  searchAirportCatalog,
} from "../../services/foundations";
import type {
  AirportCatalogItem,
  BaseLocationConsensusRead,
  BaseLocationSource,
  BaseStationType,
} from "../../types/foundations";

export type BaseDraft = {
  code: string;
  name: string;
  icao_code: string;
  iata_code: string;
  base_type: BaseStationType;
  time_zone: string;
  description: string;
  aliases: string;
  latitude: string;
  longitude: string;
  coordinate_accuracy_m: string;
  location_source: BaseLocationSource | "";
  airport_reference_ident: string;
  geofence_radius_m: string;
  checkin_prompt_enabled: boolean;
  checkout_reminder_enabled: boolean;
  suspicious_location_review_enabled: boolean;
  is_active: boolean;
};

export type BaseEditorState = {
  id?: string;
  draft: BaseDraft;
};

type Props = {
  editor: BaseEditorState;
  saving: boolean;
  onChange: (draft: BaseDraft) => void;
  onClose: () => void;
  onSave: () => void;
  onLocationChanged: () => Promise<void> | void;
};

type CapturedPosition = {
  latitude: number;
  longitude: number;
  accuracy: number;
  capturedAt: string;
};

const BASE_TYPES: BaseStationType[] = [
  "MAIN_BASE",
  "LINE_STATION",
  "OUTSTATION",
  "WORKSHOP",
  "HANGAR",
  "TRAINING_SITE",
  "OTHER",
];

function errorText(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  if (error && typeof error === "object") {
    const detail = (error as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return fallback;
}

function captureCurrentPosition(): Promise<CapturedPosition> {
  if (!window.isSecureContext) {
    return Promise.reject(new Error("Device location requires HTTPS or a trusted local development origin."));
  }
  if (!navigator.geolocation) {
    return Promise.reject(new Error("This browser does not provide geolocation."));
  }
  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(
      (position) => resolve({
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        accuracy: position.coords.accuracy,
        capturedAt: new Date(position.timestamp || Date.now()).toISOString(),
      }),
      (error) => {
        const message = error.code === error.PERMISSION_DENIED
          ? "Location permission was denied. You can enter coordinates manually or use the aerodrome lookup."
          : error.code === error.TIMEOUT
            ? "The device could not produce a location within 15 seconds. Try again outdoors or enter coordinates manually."
            : "The device location could not be determined.";
        reject(new Error(message));
      },
      { enableHighAccuracy: true, timeout: 15_000, maximumAge: 0 },
    );
  });
}

function coordinateLabel(item: AirportCatalogItem): string {
  const codes = [item.icao_code, item.iata_code].filter(Boolean).join(" / ");
  const place = [item.municipality, item.iso_country].filter(Boolean).join(", ");
  return `${codes ? `${codes} · ` : ""}${item.name}${place ? ` · ${place}` : ""}`;
}

const BaseStationEditorDialog: React.FC<Props> = ({
  editor,
  saving,
  onChange,
  onClose,
  onSave,
  onLocationChanged,
}) => {
  const draft = editor.draft;
  const [airportQuery, setAirportQuery] = useState("");
  const [airportResults, setAirportResults] = useState<AirportCatalogItem[]>([]);
  const [airportAdvisory, setAirportAdvisory] = useState("");
  const [searchingAirports, setSearchingAirports] = useState(false);
  const [capturing, setCapturing] = useState<"draft" | "contribution" | null>(null);
  const [consensus, setConsensus] = useState<BaseLocationConsensusRead | null>(null);
  const [consensusBusy, setConsensusBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "danger" | "success" | "info"; text: string } | null>(null);
  const searchRequestRef = useRef(0);

  const timeZones = useMemo(() => {
    try {
      const values = (Intl as typeof Intl & { supportedValuesOf?: (key: "timeZone") => string[] }).supportedValuesOf?.("timeZone");
      return values || ["Africa/Nairobi", "UTC"];
    } catch {
      return ["Africa/Nairobi", "UTC"];
    }
  }, []);

  const hasCoordinates = draft.latitude.trim() !== "" && draft.longitude.trim() !== "";

  useEffect(() => {
    const requestId = ++searchRequestRef.current;
    const query = airportQuery.trim();
    if (query.length < 2) {
      setAirportResults([]);
      setAirportAdvisory("");
      setSearchingAirports(false);
      return;
    }
    setSearchingAirports(true);
    const timer = window.setTimeout(() => {
      void searchAirportCatalog({
        q: query,
        latitude: draft.latitude ? Number(draft.latitude) : null,
        longitude: draft.longitude ? Number(draft.longitude) : null,
        limit: 8,
      })
        .then((result) => {
          if (requestId !== searchRequestRef.current) return;
          setAirportResults(result.items);
          setAirportAdvisory(result.advisory);
        })
        .catch((error) => {
          if (requestId !== searchRequestRef.current) return;
          setAirportResults([]);
          setMessage({ tone: "info", text: `${errorText(error, "Aerodrome suggestions are temporarily unavailable.")} Manual entry remains available.` });
        })
        .finally(() => {
          if (requestId === searchRequestRef.current) setSearchingAirports(false);
        });
    }, 320);
    return () => window.clearTimeout(timer);
  }, [airportQuery, draft.latitude, draft.longitude]);

  const refreshConsensus = async () => {
    if (!editor.id) return;
    setConsensusBusy(true);
    try {
      setConsensus(await getBaseLocationConsensus(editor.id));
    } catch (error) {
      setMessage({ tone: "danger", text: errorText(error, "Could not load location verification status.") });
    } finally {
      setConsensusBusy(false);
    }
  };

  useEffect(() => {
    if (editor.id) void refreshConsensus();
    // The station ID defines the consensus scope; draft edits must not refetch it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editor.id]);

  const chooseAirport = (item: AirportCatalogItem) => {
    const code = draft.code.trim() || item.iata_code || item.icao_code || item.ident;
    onChange({
      ...draft,
      code,
      name: item.name,
      icao_code: item.icao_code || "",
      iata_code: item.iata_code || "",
      latitude: String(item.latitude),
      longitude: String(item.longitude),
      coordinate_accuracy_m: "",
      location_source: "AERODROME_DATASET",
      airport_reference_ident: item.ident,
    });
    setAirportQuery(coordinateLabel(item));
    setAirportResults([]);
    setMessage({
      tone: "info",
      text: "Aerodrome data populated the draft. Confirm the current codes and coordinates against the applicable authority or AIP before saving.",
    });
  };

  const useDeviceForDraft = async () => {
    setCapturing("draft");
    setMessage(null);
    try {
      const position = await captureCurrentPosition();
      onChange({
        ...draft,
        latitude: position.latitude.toFixed(7),
        longitude: position.longitude.toFixed(7),
        coordinate_accuracy_m: position.accuracy.toFixed(1),
        location_source: "DEVICE_SINGLE",
        airport_reference_ident: "",
      });
      setMessage({
        tone: position.accuracy <= 150 ? "success" : "info",
        text: `One-time device position captured with ±${Math.round(position.accuracy)} m reported accuracy. Review the point before saving.`,
      });
    } catch (error) {
      setMessage({ tone: "danger", text: errorText(error, "Could not capture this device's location.") });
    } finally {
      setCapturing(null);
    }
  };

  const contributeDeviceSample = async () => {
    if (!editor.id) return;
    setCapturing("contribution");
    setMessage(null);
    try {
      const position = await captureCurrentPosition();
      const nextConsensus = await contributeBaseLocation(editor.id, {
        latitude: position.latitude,
        longitude: position.longitude,
        accuracy_m: position.accuracy,
        captured_at: position.capturedAt,
      });
      setConsensus(nextConsensus);
      setMessage({
        tone: "success",
        text: "The one-time observation was added to the private tenant consensus. Other contributors cannot view this raw point or your identity.",
      });
    } catch (error) {
      setMessage({ tone: "danger", text: errorText(error, "Could not contribute the location observation.") });
    } finally {
      setCapturing(null);
    }
  };

  const approveConsensus = async () => {
    if (!editor.id || !consensus?.ready_for_approval) return;
    setConsensusBusy(true);
    setMessage(null);
    try {
      await approveBaseLocationConsensus(editor.id, consensus.sample_count);
      setMessage({ tone: "success", text: "Independent observations were aggregated and approved. Raw observations were deleted after approval." });
      setConsensus(null);
      await onLocationChanged();
      onClose();
    } catch (error) {
      setMessage({ tone: "danger", text: errorText(error, "Could not approve the location consensus.") });
    } finally {
      setConsensusBusy(false);
    }
  };

  const clearConsensus = async () => {
    if (!editor.id || !window.confirm("Delete all unapproved location observations for this base?")) return;
    setConsensusBusy(true);
    try {
      await clearBaseLocationObservations(editor.id);
      setConsensus(null);
      setMessage({ tone: "success", text: "Unapproved location observations were deleted." });
      await refreshConsensus();
    } catch (error) {
      setMessage({ tone: "danger", text: errorText(error, "Could not clear location observations.") });
    } finally {
      setConsensusBusy(false);
    }
  };

  return (
    <div className="setup-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="setup-dialog setup-dialog--wide" role="dialog" aria-modal="true" aria-labelledby="baseEditorTitle">
        <div className="setup-dialog__header">
          <div><span>Canonical operating structure</span><h2 id="baseEditorTitle">{editor.id ? "Edit base or station" : "Add base or station"}</h2></div>
          <button type="button" aria-label="Close base editor" onClick={onClose}><X size={18} /></button>
        </div>

        {message ? <InlineAlert tone={message.tone} title={message.tone === "danger" ? "Location action needs attention" : "Location status"}><span>{message.text}</span></InlineAlert> : null}

        <div className="setup-location-lookup">
          <div>
            <Database size={18} />
            <div><strong>Find an aerodrome or place</strong><span>Type an ICAO/IATA code, aerodrome name or municipality. Suggestions never overwrite the draft until selected.</span></div>
          </div>
          <div className="setup-location-lookup__input">
            <input
              value={airportQuery}
              onChange={(event) => setAirportQuery(event.target.value)}
              placeholder="NBO, HKJK, Nairobi, Jomo Kenyatta…"
              autoComplete="off"
            />
            {searchingAirports ? <RefreshCw size={17} className="is-spinning" aria-label="Searching aerodromes" /> : <MapPin size={17} />}
          </div>
          {airportResults.length ? (
            <div className="setup-location-results" role="listbox" aria-label="Aerodrome suggestions">
              {airportResults.map((item) => (
                <button key={item.ident} type="button" onClick={() => chooseAirport(item)}>
                  <strong>{coordinateLabel(item)}</strong>
                  <span>{item.latitude.toFixed(5)}, {item.longitude.toFixed(5)}{item.distance_km != null ? ` · ${item.distance_km} km away` : ""}</span>
                </button>
              ))}
            </div>
          ) : null}
          {airportAdvisory ? <small>{airportAdvisory}</small> : null}
        </div>

        <div className="setup-dialog__grid">
          <label><span>Base code *</span><input value={draft.code} onChange={(event) => onChange({ ...draft, code: event.target.value })} placeholder="NBO-HQ" /></label>
          <label><span>Name *</span><input value={draft.name} onChange={(event) => onChange({ ...draft, name: event.target.value })} placeholder="Nairobi Main Base" /></label>
          <label><span>Facility type</span><select value={draft.base_type} onChange={(event) => onChange({ ...draft, base_type: event.target.value as BaseStationType })}>{BASE_TYPES.map((type) => <option key={type} value={type}>{type.replaceAll("_", " ")}</option>)}</select></label>
          <label><span>Time zone</span><input list="setup-time-zones" value={draft.time_zone} onChange={(event) => onChange({ ...draft, time_zone: event.target.value })} placeholder="Africa/Nairobi" /><datalist id="setup-time-zones">{timeZones.map((zone) => <option key={zone} value={zone} />)}</datalist></label>
          <label><span>ICAO code</span><input value={draft.icao_code} onChange={(event) => onChange({ ...draft, icao_code: event.target.value })} maxLength={8} placeholder="HKJK" /></label>
          <label><span>IATA code</span><input value={draft.iata_code} onChange={(event) => onChange({ ...draft, iata_code: event.target.value })} maxLength={8} placeholder="NBO" /></label>
          <label className="is-wide"><span>Aliases</span><input value={draft.aliases} onChange={(event) => onChange({ ...draft, aliases: event.target.value })} placeholder="HQ, Nairobi Hangar (comma separated)" /></label>
          <label className="is-wide"><span>Description</span><textarea rows={3} value={draft.description} onChange={(event) => onChange({ ...draft, description: event.target.value })} placeholder="Scope, location notes or operating limitations" /></label>
        </div>

        <fieldset className="setup-location-fieldset">
          <legend><LocateFixed size={17} /> Approved location and geofence</legend>
          <div className="setup-location-consent">
            <ShieldCheck size={19} />
            <p><strong>Privacy rule:</strong> location is requested only after an explicit button click. A draft capture is saved only when you submit this form. Independent verification stores short-lived raw observations server-side, returns only an aggregate, and deletes the points after approval.</p>
          </div>
          <div className="setup-location-actions">
            <Button type="button" variant="secondary" disabled={capturing !== null} onClick={() => void useDeviceForDraft()}>
              <Crosshair size={16} /> {capturing === "draft" ? "Locating…" : "Use this device once"}
            </Button>
            {editor.id ? (
              <Button type="button" variant="secondary" disabled={capturing !== null} onClick={() => void contributeDeviceSample()}>
                <ShieldCheck size={16} /> {capturing === "contribution" ? "Contributing…" : "Contribute independent sample"}
              </Button>
            ) : null}
          </div>
          <div className="setup-dialog__grid">
            <label><span>Latitude</span><input inputMode="decimal" value={draft.latitude} onChange={(event) => onChange({ ...draft, latitude: event.target.value, location_source: draft.location_source || "MANUAL" })} placeholder="-1.319167" /></label>
            <label><span>Longitude</span><input inputMode="decimal" value={draft.longitude} onChange={(event) => onChange({ ...draft, longitude: event.target.value, location_source: draft.location_source || "MANUAL" })} placeholder="36.927778" /></label>
            <label><span>Reported accuracy (metres)</span><input inputMode="decimal" value={draft.coordinate_accuracy_m} onChange={(event) => onChange({ ...draft, coordinate_accuracy_m: event.target.value })} placeholder="25" /></label>
            <label><span>Geofence radius (metres)</span><input type="number" min={50} max={5000} step={10} value={draft.geofence_radius_m} onChange={(event) => onChange({ ...draft, geofence_radius_m: event.target.value })} /></label>
          </div>
          <div className="setup-location-policy">
            <label><input type="checkbox" disabled={!hasCoordinates} checked={draft.checkin_prompt_enabled} onChange={(event) => onChange({ ...draft, checkin_prompt_enabled: event.target.checked })} /><span>Allow HR/Rostering to prompt check-in when a user enters this approved geofence</span></label>
            <label><input type="checkbox" disabled={!hasCoordinates} checked={draft.checkout_reminder_enabled} onChange={(event) => onChange({ ...draft, checkout_reminder_enabled: event.target.checked })} /><span>Allow a checkout reminder after the duty system confirms duty has ended</span></label>
            <label><input type="checkbox" disabled={!hasCoordinates} checked={draft.suspicious_location_review_enabled} onChange={(event) => onChange({ ...draft, suspicious_location_review_enabled: event.target.checked })} /><span>Flag high-confidence, materially distant submissions for human review; never determine misconduct automatically</span></label>
          </div>

          {editor.id ? (
            <div className="setup-consensus-card">
              <div className="setup-consensus-card__heading">
                <div><strong>Independent device consensus</strong><span>Only aggregate quality and spread are shown.</span></div>
                <button type="button" onClick={() => void refreshConsensus()} disabled={consensusBusy} aria-label="Refresh location consensus"><RefreshCw size={16} className={consensusBusy ? "is-spinning" : ""} /></button>
              </div>
              {consensus ? (
                <>
                  <div className="setup-consensus-metrics">
                    <span><strong>{consensus.sample_count}</strong> samples</span>
                    <span><strong>{consensus.distinct_contributor_count}</strong> contributors</span>
                    <span><strong>{consensus.max_spread_m == null ? "—" : `${Math.round(consensus.max_spread_m)} m`}</strong> max spread</span>
                    <span><strong>{consensus.median_accuracy_m == null ? "—" : `±${Math.round(consensus.median_accuracy_m)} m`}</strong> median accuracy</span>
                  </div>
                  <p className={consensus.ready_for_approval ? "is-ready" : ""}>{consensus.ready_for_approval ? <CheckCircle2 size={16} /> : <ShieldCheck size={16} />}{consensus.reason}</p>
                  <div className="setup-location-actions">
                    <Button type="button" disabled={!consensus.ready_for_approval || consensusBusy} onClick={() => void approveConsensus()}><CheckCircle2 size={16} /> Approve aggregate</Button>
                    <Button type="button" variant="secondary" disabled={!consensus.sample_count || consensusBusy} onClick={() => void clearConsensus()}><Trash2 size={15} /> Clear observations</Button>
                  </div>
                </>
              ) : <p>No unapproved observations are available.</p>}
            </div>
          ) : null}
        </fieldset>

        <label className="setup-dialog__check"><input type="checkbox" checked={draft.is_active} onChange={(event) => onChange({ ...draft, is_active: event.target.checked })} /><span>Active and available to portal modules</span></label>
        <div className="setup-dialog__actions"><Button type="button" variant="secondary" onClick={onClose}>Cancel</Button><Button type="button" disabled={saving} onClick={onSave}><Save size={16} /> {saving ? "Saving…" : editor.id ? "Save changes" : "Create base"}</Button></div>
      </section>
    </div>
  );
};

export default BaseStationEditorDialog;
