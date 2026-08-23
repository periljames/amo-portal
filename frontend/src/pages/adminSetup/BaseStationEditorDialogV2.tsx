import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Crosshair,
  Database,
  LocateFixed,
  MapPin,
  RefreshCw,
  Save,
  ShieldCheck,
  Trash2,
  TriangleAlert,
  X,
} from "lucide-react";

import { Button, InlineAlert } from "../../components/UI/Admin";
import GoogleBaseLocationPicker, {
  type GooglePlaceSelection,
} from "./GoogleBaseLocationPicker";
import {
  approveBaseLocationConsensus,
  clearBaseLocationObservations,
  contributeBaseLocation,
  getBaseLocationConsensus,
  searchAirportCatalog,
} from "../../services/foundations";
import "../../styles/admin-setup-location-v2.css";

import type {
  AirportCatalogItem,
  BaseLocationConsensusRead,
  BaseLocationSource,
  BaseStationRead,
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
  existingBases: BaseStationRead[];
  saving: boolean;
  onEditExisting: (base: BaseStationRead) => void;
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

const TYPE_SUFFIX: Record<BaseStationType, string> = {
  MAIN_BASE: "HQ",
  LINE_STATION: "LINE",
  OUTSTATION: "STN",
  WORKSHOP: "WS",
  HANGAR: "HGR",
  TRAINING_SITE: "TRG",
  OTHER: "FAC",
};

function errorText(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  if (error && typeof error === "object") {
    const detail = (error as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return fallback;
}

function identityKey(value: string | null | undefined): string {
  return String(value || "").trim().toUpperCase();
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
          ? "Location permission was denied. Use the map, enter coordinates manually or select an aerodrome."
          : error.code === error.TIMEOUT
            ? "The device could not produce a location within 15 seconds. Try again outdoors or use the map."
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

function facilityTypeLabel(type: BaseStationType): string {
  return type.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function airportMatch(item: AirportCatalogItem, base: BaseStationRead): boolean {
  const identifiers = [item.ident, item.icao_code, item.iata_code].map(identityKey).filter(Boolean);
  return identifiers.some((identifier) => (
    identityKey(base.airport_reference_ident) === identifier
    || identityKey(base.icao_code) === identifier
    || identityKey(base.iata_code) === identifier
  ));
}

export function uniqueFacilityCode(
  item: AirportCatalogItem,
  type: BaseStationType,
  bases: readonly BaseStationRead[],
): string {
  const prefix = identityKey(item.iata_code || item.icao_code || item.ident).replace(/[^A-Z0-9]/g, "").slice(0, 12) || "BASE";
  const root = `${prefix}-${TYPE_SUFFIX[type]}`;
  const used = new Set(bases.map((base) => identityKey(base.code)));
  if (!used.has(root)) return root;
  for (let index = 2; index < 100; index += 1) {
    const candidate = `${root}-${index}`;
    if (!used.has(candidate)) return candidate;
  }
  return `${root}-${Date.now().toString().slice(-4)}`;
}

const BaseStationEditorDialog: React.FC<Props> = ({
  editor,
  existingBases,
  saving,
  onEditExisting,
  onChange,
  onClose,
  onSave,
  onLocationChanged,
}) => {
  const draft = editor.draft;
  const [identityExpanded, setIdentityExpanded] = useState(!editor.id);
  const [airportQuery, setAirportQuery] = useState("");
  const [airportResults, setAirportResults] = useState<AirportCatalogItem[]>([]);
  const [airportAdvisory, setAirportAdvisory] = useState("");
  const [searchingAirports, setSearchingAirports] = useState(false);
  const [capturing, setCapturing] = useState<"draft" | "contribution" | null>(null);
  const [consensus, setConsensus] = useState<BaseLocationConsensusRead | null>(null);
  const [consensusBusy, setConsensusBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "danger" | "success" | "info"; text: string } | null>(null);
  const [matchingBase, setMatchingBase] = useState<BaseStationRead | null>(null);
  const searchRequestRef = useRef(0);
  const locationSectionRef = useRef<HTMLElement | null>(null);

  const timeZones = useMemo(() => {
    try {
      const values = (Intl as typeof Intl & { supportedValuesOf?: (key: "timeZone") => string[] }).supportedValuesOf?.("timeZone");
      return values || ["Africa/Nairobi", "UTC"];
    } catch {
      return ["Africa/Nairobi", "UTC"];
    }
  }, []);

  const hasCoordinates = draft.latitude.trim() !== "" && draft.longitude.trim() !== "";
  const latitude = hasCoordinates && Number.isFinite(Number(draft.latitude)) ? Number(draft.latitude) : null;
  const longitude = hasCoordinates && Number.isFinite(Number(draft.longitude)) ? Number(draft.longitude) : null;
  const codeConflict = useMemo(() => {
    const requestedCode = identityKey(draft.code);
    if (!requestedCode) return null;
    return existingBases.find((base) => base.id !== editor.id && identityKey(base.code) === requestedCode) || null;
  }, [draft.code, editor.id, existingBases]);

  const scrollLocationIntoView = () => {
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    window.setTimeout(() => {
      locationSectionRef.current?.scrollIntoView({
        behavior: reduceMotion ? "auto" : "smooth",
        block: "start",
      });
    }, 80);
  };

  useEffect(() => {
    setIdentityExpanded(!editor.id || !(editor.draft.latitude.trim() && editor.draft.longitude.trim()));
    setMatchingBase(null);
    setAirportQuery("");
    setMessage(null);
    // A new editor identity resets the workflow; draft keystrokes must not reopen the collapsed section.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editor.id]);

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
        latitude,
        longitude,
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
          setMessage({
            tone: "info",
            text: `${errorText(error, "Aerodrome suggestions are temporarily unavailable.")} Google Maps and manual entry remain available.`,
          });
        })
        .finally(() => {
          if (requestId === searchRequestRef.current) setSearchingAirports(false);
        });
    }, 320);
    return () => window.clearTimeout(timer);
  }, [airportQuery, latitude, longitude]);

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
    const match = existingBases.find((base) => base.id !== editor.id && airportMatch(item, base)) || null;
    const generatedCode = editor.id || draft.code.trim()
      ? draft.code
      : uniqueFacilityCode(item, draft.base_type, existingBases);
    const generatedName = draft.name.trim()
      ? draft.name
      : `${item.name} — ${facilityTypeLabel(draft.base_type)}`;

    onChange({
      ...draft,
      code: generatedCode,
      name: generatedName,
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
    setMatchingBase(match);
    setIdentityExpanded(false);
    setMessage({
      tone: "info",
      text: match
        ? `${item.name} is already linked to ${match.code} · ${match.name}. Edit that record to complete its location, or keep the generated facility code for a genuinely separate hangar, station or workshop.`
        : "Aerodrome coordinates were applied. Confirm the exact facility point on the map and drag the pin when necessary.",
    });
    scrollLocationIntoView();
  };

  const applyGooglePlace = (selection: GooglePlaceSelection) => {
    onChange({
      ...draft,
      name: draft.name.trim() || selection.displayName || selection.formattedAddress || "",
      latitude: String(selection.latitude),
      longitude: String(selection.longitude),
      coordinate_accuracy_m: "",
      location_source: "MANUAL",
    });
    setIdentityExpanded(false);
    setMessage({
      tone: "success",
      text: selection.displayName || selection.formattedAddress
        ? `${selection.displayName || selection.formattedAddress} selected from Google Maps. Drag the pin to the exact approved facility point.`
        : "The approved point was moved on Google Maps.",
    });
  };

  const captureDeviceLocationForDraft = async () => {
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
      setIdentityExpanded(false);
      setMessage({
        tone: position.accuracy <= 150 ? "success" : "info",
        text: `One-time device position captured with ±${Math.round(position.accuracy)} m reported accuracy. Review the pin before saving.`,
      });
      scrollLocationIntoView();
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

  const identitySummary = [draft.code, draft.name, draft.icao_code || draft.iata_code]
    .map((value) => value.trim())
    .filter(Boolean)
    .join(" · ") || "Facility identity not completed";

  return (
    <div className="setup-dialog-backdrop setup-base-editor-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="setup-dialog setup-dialog--wide setup-base-editor" role="dialog" aria-modal="true" aria-labelledby="baseEditorTitle">
        <div className="setup-dialog__header">
          <div>
            <span>Canonical operating structure</span>
            <h2 id="baseEditorTitle">{editor.id ? `Edit ${draft.code || "base or station"}` : "Add base or station"}</h2>
          </div>
          <button type="button" aria-label="Close base editor" onClick={onClose}><X size={18} /></button>
        </div>

        {message ? (
          <InlineAlert tone={message.tone} title={message.tone === "danger" ? "Action required" : "Location status"}>
            <span>{message.text}</span>
          </InlineAlert>
        ) : null}

        {codeConflict ? (
          <div className="setup-base-editor__conflict" role="alert">
            <TriangleAlert size={18} />
            <div>
              <strong>Base code {draft.code.trim().toUpperCase()} is already in use</strong>
              <span>{codeConflict.code} · {codeConflict.name}. Airport codes may be shared; the facility code must be unique.</span>
            </div>
            <Button type="button" size="sm" variant="secondary" onClick={() => onEditExisting(codeConflict)}>
              Edit existing
            </Button>
          </div>
        ) : null}

        {matchingBase && matchingBase.id !== codeConflict?.id ? (
          <div className="setup-base-editor__existing-match">
            <MapPin size={18} />
            <div>
              <strong>This aerodrome already has a base record</strong>
              <span>{matchingBase.code} · {matchingBase.name}{matchingBase.location_configured ? " · location already configured" : " · location still missing"}</span>
            </div>
            <div>
              <Button type="button" size="sm" onClick={() => onEditExisting(matchingBase)}>Edit existing base</Button>
              <button type="button" onClick={() => setMatchingBase(null)}>Keep separate facility</button>
            </div>
          </div>
        ) : null}

        <section className={`setup-base-editor__identity ${identityExpanded ? "is-expanded" : "is-collapsed"}`}>
          <button
            type="button"
            className="setup-base-editor__section-toggle"
            aria-expanded={identityExpanded}
            onClick={() => setIdentityExpanded((value) => !value)}
          >
            <span>
              <strong>Facility identity</strong>
              <small>{identitySummary}</small>
            </span>
            {identityExpanded ? <ChevronUp size={17} /> : <ChevronDown size={17} />}
          </button>

          {identityExpanded ? (
            <div className="setup-base-editor__identity-body">
              <div className="setup-location-lookup">
                <div>
                  <Database size={18} />
                  <div>
                    <strong>Find an aerodrome</strong>
                    <span>ICAO/IATA identify the aerodrome. A separate unique facility code identifies your base, hangar, workshop or station.</span>
                  </div>
                </div>
                <div className="setup-location-lookup__input">
                  <input
                    value={airportQuery}
                    onChange={(event) => setAirportQuery(event.target.value)}
                    placeholder="Search HKJK, NBO, Nairobi or Jomo Kenyatta"
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

              <div className="setup-dialog__grid setup-base-editor__identity-grid">
                <label>
                  <span>Facility code *</span>
                  <input value={draft.code} onChange={(event) => onChange({ ...draft, code: event.target.value })} placeholder="Example: NBO-HQ or NBO-HGR" />
                  <small>Unique portal identifier. Do not use the airport IATA code alone for every facility.</small>
                </label>
                <label>
                  <span>Facility name *</span>
                  <input value={draft.name} onChange={(event) => onChange({ ...draft, name: event.target.value })} placeholder="Example: JKIA Main Base" />
                </label>
                <label>
                  <span>Facility type</span>
                  <select value={draft.base_type} onChange={(event) => onChange({ ...draft, base_type: event.target.value as BaseStationType })}>
                    {BASE_TYPES.map((type) => <option key={type} value={type}>{type.replaceAll("_", " ")}</option>)}
                  </select>
                </label>
                <label>
                  <span>Time zone</span>
                  <input list="setup-time-zones" value={draft.time_zone} onChange={(event) => onChange({ ...draft, time_zone: event.target.value })} placeholder="Africa/Nairobi" />
                  <datalist id="setup-time-zones">{timeZones.map((zone) => <option key={zone} value={zone} />)}</datalist>
                </label>
                <label><span>ICAO aerodrome code</span><input value={draft.icao_code} onChange={(event) => onChange({ ...draft, icao_code: event.target.value })} maxLength={8} placeholder="HKJK" /></label>
                <label><span>IATA aerodrome code</span><input value={draft.iata_code} onChange={(event) => onChange({ ...draft, iata_code: event.target.value })} maxLength={8} placeholder="NBO" /></label>
                <label className="is-wide"><span>Aliases</span><input value={draft.aliases} onChange={(event) => onChange({ ...draft, aliases: event.target.value })} placeholder="Optional: HQ, Nairobi Hangar (comma separated)" /></label>
                <label className="is-wide"><span>Description</span><textarea rows={2} value={draft.description} onChange={(event) => onChange({ ...draft, description: event.target.value })} placeholder="Optional scope, access notes or operating limitations" /></label>
              </div>
            </div>
          ) : null}
        </section>

        <section ref={locationSectionRef} className="setup-base-editor__location" aria-labelledby="baseLocationHeading">
          <div className="setup-base-editor__location-heading">
            <div>
              <LocateFixed size={19} />
              <span><strong id="baseLocationHeading">Approved facility location</strong><small>Search Google Maps, select an aerodrome, click the map or drag the pin.</small></span>
            </div>
            <Button type="button" size="sm" variant="secondary" disabled={capturing !== null} onClick={() => void captureDeviceLocationForDraft()}>
              <Crosshair size={15} /> {capturing === "draft" ? "Locating…" : "Use this device"}
            </Button>
          </div>

          <GoogleBaseLocationPicker
            latitude={latitude}
            longitude={longitude}
            label={draft.name || draft.code || "Base location"}
            onPositionChange={applyGooglePlace}
          />

          <div className="setup-base-editor__coordinate-row">
            <label><span>Latitude</span><input inputMode="decimal" value={draft.latitude} onChange={(event) => onChange({ ...draft, latitude: event.target.value, location_source: "MANUAL" })} placeholder="-1.3191670" /></label>
            <label><span>Longitude</span><input inputMode="decimal" value={draft.longitude} onChange={(event) => onChange({ ...draft, longitude: event.target.value, location_source: "MANUAL" })} placeholder="36.9277780" /></label>
            <label><span>Accuracy (m)</span><input inputMode="decimal" value={draft.coordinate_accuracy_m} onChange={(event) => onChange({ ...draft, coordinate_accuracy_m: event.target.value })} placeholder="Optional" /></label>
            <label><span>Geofence radius (m)</span><input type="number" min={50} max={5000} step={10} value={draft.geofence_radius_m} onChange={(event) => onChange({ ...draft, geofence_radius_m: event.target.value })} /></label>
          </div>

          <details className="setup-base-editor__policy">
            <summary>Location and attendance policy</summary>
            <div className="setup-location-consent">
              <ShieldCheck size={18} />
              <p><strong>Privacy rule:</strong> the approved facility point is saved only when this form is submitted. Device observations remain short-lived and are deleted after consensus approval.</p>
            </div>
            <div className="setup-location-policy">
              <label><input type="checkbox" disabled={!hasCoordinates} checked={draft.checkin_prompt_enabled} onChange={(event) => onChange({ ...draft, checkin_prompt_enabled: event.target.checked })} /><span>Allow HR/Rostering to prompt check-in inside this approved geofence</span></label>
              <label><input type="checkbox" disabled={!hasCoordinates} checked={draft.checkout_reminder_enabled} onChange={(event) => onChange({ ...draft, checkout_reminder_enabled: event.target.checked })} /><span>Allow checkout reminders after duty has ended</span></label>
              <label><input type="checkbox" disabled={!hasCoordinates} checked={draft.suspicious_location_review_enabled} onChange={(event) => onChange({ ...draft, suspicious_location_review_enabled: event.target.checked })} /><span>Send materially distant high-confidence submissions for human review</span></label>
            </div>
          </details>

          {editor.id ? (
            <details className="setup-consensus-card">
              <summary>
                <span><strong>Independent device consensus</strong><small>{consensus?.sample_count || 0} current sample(s)</small></span>
                <button type="button" onClick={(event) => { event.preventDefault(); void refreshConsensus(); }} disabled={consensusBusy} aria-label="Refresh location consensus"><RefreshCw size={16} className={consensusBusy ? "is-spinning" : ""} /></button>
              </summary>
              {consensus ? (
                <div className="setup-consensus-card__body">
                  <div className="setup-consensus-metrics">
                    <span><strong>{consensus.sample_count}</strong> samples</span>
                    <span><strong>{consensus.distinct_contributor_count}</strong> contributors</span>
                    <span><strong>{consensus.max_spread_m == null ? "—" : `${Math.round(consensus.max_spread_m)} m`}</strong> max spread</span>
                    <span><strong>{consensus.median_accuracy_m == null ? "—" : `±${Math.round(consensus.median_accuracy_m)} m`}</strong> median accuracy</span>
                  </div>
                  <p className={consensus.ready_for_approval ? "is-ready" : ""}>{consensus.ready_for_approval ? <CheckCircle2 size={16} /> : <ShieldCheck size={16} />}{consensus.reason}</p>
                  <div className="setup-location-actions">
                    <Button type="button" variant="secondary" disabled={capturing !== null} onClick={() => void contributeDeviceSample()}><ShieldCheck size={15} /> {capturing === "contribution" ? "Contributing…" : "Contribute sample"}</Button>
                    <Button type="button" disabled={!consensus.ready_for_approval || consensusBusy} onClick={() => void approveConsensus()}><CheckCircle2 size={15} /> Approve aggregate</Button>
                    <Button type="button" variant="secondary" disabled={!consensus.sample_count || consensusBusy} onClick={() => void clearConsensus()}><Trash2 size={15} /> Clear</Button>
                  </div>
                </div>
              ) : <p>No unapproved observations are available.</p>}
            </details>
          ) : null}
        </section>

        <div className="setup-base-editor__active-row">
          <label><input type="checkbox" checked={draft.is_active} onChange={(event) => onChange({ ...draft, is_active: event.target.checked })} /><span>Active and available to portal modules</span></label>
        </div>

        <div className="setup-dialog__actions">
          <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="button" disabled={saving || Boolean(codeConflict)} onClick={onSave}>
            <Save size={16} /> {saving ? "Saving…" : editor.id ? "Save changes" : "Create facility"}
          </Button>
        </div>
      </section>
    </div>
  );
};

export default BaseStationEditorDialog;
