import React, { useEffect, useMemo, useRef, useState } from "react";
import { MapPin, Move, Search, TriangleAlert } from "lucide-react";

type LatLngLiteral = { lat: number; lng: number };
type LatLngObject = { lat: () => number; lng: () => number };
type LatLngValue = LatLngLiteral | LatLngObject | null | undefined;

type MapsListener = { remove?: () => void };

type GoogleMapInstance = {
  setCenter: (position: LatLngLiteral) => void;
  setZoom: (zoom: number) => void;
  fitBounds?: (bounds: unknown) => void;
  addListener: (eventName: string, handler: (event: { latLng?: LatLngValue }) => void) => MapsListener;
};

type GoogleMapConstructor = new (
  element: HTMLElement,
  options: {
    center: LatLngLiteral;
    zoom: number;
    mapId?: string;
    streetViewControl?: boolean;
    mapTypeControl?: boolean;
    fullscreenControl?: boolean;
  },
) => GoogleMapInstance;

type AdvancedMarkerInstance = {
  map?: GoogleMapInstance | null;
  position?: LatLngValue;
  addListener: (eventName: string, handler: () => void) => MapsListener;
};

type AdvancedMarkerConstructor = new (options: {
  map?: GoogleMapInstance | null;
  position?: LatLngLiteral;
  title: string;
  gmpDraggable: boolean;
}) => AdvancedMarkerInstance;

type GooglePlace = {
  id?: string;
  displayName?: string;
  formattedAddress?: string;
  location?: LatLngValue;
  viewport?: unknown;
  fetchFields: (request: { fields: string[] }) => Promise<void>;
};

type PlacePrediction = { toPlace: () => GooglePlace };
type PlaceSelectEvent = Event & { placePrediction?: PlacePrediction };

type PlaceAutocompleteElementInstance = HTMLElement & {
  placeholder?: string;
};

type PlaceAutocompleteElementConstructor = new (
  options?: Record<string, unknown>,
) => PlaceAutocompleteElementInstance;

type GoogleMapsRoot = {
  maps: {
    importLibrary: (name: "maps" | "marker" | "places") => Promise<unknown>;
  };
};

declare global {
  interface Window {
    google?: GoogleMapsRoot;
    __amoGoogleMapsReady?: () => void;
  }
}

export type GooglePlaceSelection = {
  latitude: number;
  longitude: number;
  displayName?: string;
  formattedAddress?: string;
  placeId?: string;
};

type Props = {
  latitude: number | null;
  longitude: number | null;
  label: string;
  onPositionChange: (selection: GooglePlaceSelection) => void;
};

const SCRIPT_ID = "amo-google-maps-js";
const DEFAULT_POSITION: LatLngLiteral = { lat: -1.319167, lng: 36.927778 };
let googleMapsPromise: Promise<GoogleMapsRoot> | null = null;

function toLatLng(value: LatLngValue): LatLngLiteral | null {
  if (!value) return null;
  if (typeof (value as LatLngObject).lat === "function") {
    const objectValue = value as LatLngObject;
    return { lat: objectValue.lat(), lng: objectValue.lng() };
  }
  const literal = value as LatLngLiteral;
  return Number.isFinite(literal.lat) && Number.isFinite(literal.lng) ? literal : null;
}

function loadGoogleMaps(apiKey: string): Promise<GoogleMapsRoot> {
  if (window.google?.maps?.importLibrary) return Promise.resolve(window.google);
  if (googleMapsPromise) return googleMapsPromise;

  googleMapsPromise = new Promise<GoogleMapsRoot>((resolve, reject) => {
    const existing = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null;
    const finish = () => {
      if (window.google?.maps?.importLibrary) resolve(window.google);
      else reject(new Error("Google Maps loaded without the expected Maps JavaScript API."));
    };

    window.__amoGoogleMapsReady = finish;
    if (existing) {
      existing.addEventListener("load", finish, { once: true });
      existing.addEventListener("error", () => reject(new Error("Google Maps could not be loaded.")), { once: true });
      return;
    }

    const script = document.createElement("script");
    script.id = SCRIPT_ID;
    script.async = true;
    script.defer = true;
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&v=weekly&loading=async&callback=__amoGoogleMapsReady`;
    script.onerror = () => reject(new Error("Google Maps could not be loaded. Check the API key, allowed domain and network access."));
    document.head.appendChild(script);
  }).catch((error) => {
    googleMapsPromise = null;
    throw error;
  });

  return googleMapsPromise;
}

const GoogleBaseLocationPicker: React.FC<Props> = ({
  latitude,
  longitude,
  label,
  onPositionChange,
}) => {
  const apiKey = String(import.meta.env.VITE_GOOGLE_MAPS_API_KEY || "").trim();
  const mapId = String(import.meta.env.VITE_GOOGLE_MAPS_MAP_ID || "DEMO_MAP_ID").trim();
  const mapHostRef = useRef<HTMLDivElement | null>(null);
  const searchHostRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<GoogleMapInstance | null>(null);
  const markerRef = useRef<AdvancedMarkerInstance | null>(null);
  const listenersRef = useRef<MapsListener[]>([]);
  const onChangeRef = useRef(onPositionChange);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "unconfigured" | "error">(
    apiKey ? "loading" : "unconfigured",
  );
  const [error, setError] = useState<string | null>(null);

  const position = useMemo<LatLngLiteral | null>(() => {
    if (latitude == null || longitude == null) return null;
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null;
    return { lat: latitude, lng: longitude };
  }, [latitude, longitude]);
  const positionRef = useRef<LatLngLiteral | null>(position);
  const labelRef = useRef(label);

  useEffect(() => {
    onChangeRef.current = onPositionChange;
  }, [onPositionChange]);

  useEffect(() => {
    positionRef.current = position;
    labelRef.current = label;
  }, [label, position]);

  useEffect(() => {
    if (!apiKey || !mapHostRef.current || !searchHostRef.current) return;

    let cancelled = false;

    void loadGoogleMaps(apiKey)
      .then(async (google) => {
        const [mapsLibrary, markerLibrary, placesLibrary] = await Promise.all([
          google.maps.importLibrary("maps"),
          google.maps.importLibrary("marker"),
          google.maps.importLibrary("places"),
        ]);
        if (cancelled || !mapHostRef.current || !searchHostRef.current) return;

        const { Map } = mapsLibrary as { Map: GoogleMapConstructor };
        const { AdvancedMarkerElement } = markerLibrary as {
          AdvancedMarkerElement: AdvancedMarkerConstructor;
        };
        const { PlaceAutocompleteElement } = placesLibrary as {
          PlaceAutocompleteElement: PlaceAutocompleteElementConstructor;
        };

        const configuredPosition = positionRef.current;
        const initialPosition = configuredPosition || DEFAULT_POSITION;
        const map = new Map(mapHostRef.current, {
          center: initialPosition,
          zoom: configuredPosition ? 17 : 11,
          mapId: mapId || "DEMO_MAP_ID",
          streetViewControl: false,
          mapTypeControl: true,
          fullscreenControl: true,
        });
        const marker = new AdvancedMarkerElement({
          ...(configuredPosition ? { map, position: configuredPosition } : {}),
          title: `${labelRef.current || "Base location"}. Drag to correct the approved point.`,
          gmpDraggable: true,
        });

        const commitPosition = (nextPosition: LatLngValue, metadata: Partial<GooglePlaceSelection> = {}) => {
          const literal = toLatLng(nextPosition);
          if (!literal) return;
          marker.position = literal;
          marker.map = map;
          map.setCenter(literal);
          onChangeRef.current({
            latitude: Number(literal.lat.toFixed(7)),
            longitude: Number(literal.lng.toFixed(7)),
            ...metadata,
          });
        };

        listenersRef.current = [
          marker.addListener("dragend", () => commitPosition(marker.position)),
          map.addListener("click", (event) => commitPosition(event.latLng)),
        ];

        const autocomplete = new PlaceAutocompleteElement({});
        autocomplete.placeholder = "Search Google Maps for an airport, hangar, workshop or address";
        autocomplete.setAttribute("aria-label", "Search Google Maps for the base location");
        autocomplete.className = "setup-google-map__autocomplete";
        searchHostRef.current.replaceChildren(autocomplete);
        autocomplete.addEventListener("gmp-select", (rawEvent) => {
          const event = rawEvent as PlaceSelectEvent;
          const place = event.placePrediction?.toPlace();
          if (!place) return;
          void place.fetchFields({
            fields: ["id", "displayName", "formattedAddress", "location", "viewport"],
          }).then(() => {
            const selectedPosition = toLatLng(place.location);
            if (!selectedPosition) return;
            if (place.viewport && map.fitBounds) map.fitBounds(place.viewport);
            else {
              map.setCenter(selectedPosition);
              map.setZoom(18);
            }
            commitPosition(selectedPosition, {
              displayName: place.displayName,
              formattedAddress: place.formattedAddress,
              placeId: place.id,
            });
          });
        });

        mapRef.current = map;
        markerRef.current = marker;
        setStatus("ready");
      })
      .catch((cause) => {
        if (cancelled) return;
        setStatus("error");
        setError(cause instanceof Error ? cause.message : "Google Maps could not be initialized.");
      });

    return () => {
      cancelled = true;
      listenersRef.current.forEach((listener) => listener.remove?.());
      listenersRef.current = [];
      if (markerRef.current) markerRef.current.map = null;
      markerRef.current = null;
      mapRef.current = null;
      searchHostRef.current?.replaceChildren();
    };
  }, [apiKey, mapId]);

  useEffect(() => {
    if (!mapRef.current || !markerRef.current) return;
    if (!position) {
      markerRef.current.map = null;
      return;
    }
    markerRef.current.position = position;
    markerRef.current.map = mapRef.current;
    mapRef.current.setCenter(position);
    mapRef.current.setZoom(17);
  }, [position]);

  const fallbackUrl = position
    ? `https://www.google.com/maps?q=${encodeURIComponent(`${position.lat},${position.lng}`)}&z=17&output=embed`
    : null;

  return (
    <div className="setup-google-map" data-status={status}>
      <div className="setup-google-map__search" ref={searchHostRef}>
        {!apiKey ? (
          <div className="setup-google-map__search-disabled">
            <Search size={16} />
            <span>Google place search requires the deployment Maps API key.</span>
          </div>
        ) : null}
      </div>

      <div className="setup-google-map__canvas-wrap">
        {apiKey ? <div ref={mapHostRef} className="setup-google-map__canvas" aria-label="Google map for selecting the approved base location" /> : null}
        {!apiKey && fallbackUrl ? (
          <iframe
            className="setup-google-map__fallback"
            title="Google Maps location preview"
            src={fallbackUrl}
            loading="lazy"
            referrerPolicy="no-referrer-when-downgrade"
          />
        ) : null}
        {!apiKey && !fallbackUrl ? (
          <div className="setup-google-map__empty">
            <MapPin size={30} />
            <strong>Select an aerodrome or enter coordinates</strong>
            <span>The map preview will centre on the saved point.</span>
          </div>
        ) : null}
        {status === "loading" ? <div className="setup-google-map__loading">Loading Google Maps…</div> : null}
        {status === "error" ? (
          <div className="setup-google-map__error" role="alert">
            <TriangleAlert size={18} />
            <span>{error}</span>
          </div>
        ) : null}
      </div>

      <div className="setup-google-map__footer">
        <span>
          {position
            ? <><Move size={15} /> Drag the pin or click the map to correct the exact facility point.</>
            : <><MapPin size={15} /> Search or click the map to place the facility pin.</>}
        </span>
        <output>
          {position ? `${position.lat.toFixed(7)}, ${position.lng.toFixed(7)}` : "No coordinates selected"}
        </output>
      </div>
    </div>
  );
};

export default GoogleBaseLocationPicker;
