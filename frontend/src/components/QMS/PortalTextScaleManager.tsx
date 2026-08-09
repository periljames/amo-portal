import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { ALargeSmall, Check } from "lucide-react";

import { getCachedUser } from "../../services/auth";
import {
  getPortalPreferences,
  updatePortalPreferences,
  type PortalTextScale,
} from "../../services/portalPreferences";


type ScaleOption = {
  id: PortalTextScale;
  label: string;
  sample: string;
  description: string;
  multiplier: number;
};

type PortalTextScalePreferenceScopeProps = {
  storageKey: string;
};

const SCALE_OPTIONS: readonly ScaleOption[] = [
  {
    id: "standard",
    label: "Standard",
    sample: "A",
    description: "Normal portal text",
    multiplier: 1,
  },
  {
    id: "large",
    label: "Large",
    sample: "A+",
    description: "Easier sustained reading",
    multiplier: 1.125,
  },
  {
    id: "extra-large",
    label: "Extra large",
    sample: "A++",
    description: "Maximum portal readability",
    multiplier: 1.25,
  },
] as const;

function isTextScale(value: string | null): value is PortalTextScale {
  return SCALE_OPTIONS.some((option) => option.id === value);
}

function preferenceStorageKey(): string {
  const user = getCachedUser();
  return `amo_portal_text_scale:${user?.id || "anonymous"}:${user?.amo_id || "platform"}`;
}

function readStoredScale(storageKey: string): PortalTextScale {
  if (typeof window === "undefined") return "standard";
  const value = window.localStorage.getItem(storageKey);
  return isTextScale(value) ? value : "standard";
}

function applyScale(scale: PortalTextScale): void {
  if (typeof document === "undefined") return;
  const option = SCALE_OPTIONS.find((candidate) => candidate.id === scale) || SCALE_OPTIONS[0];
  document.documentElement.dataset.portalTextScale = option.id;
  document.body.dataset.portalTextScale = option.id;
  document.documentElement.style.setProperty("--portal-text-scale", String(option.multiplier));
  document.body.style.setProperty("--portal-text-scale", String(option.multiplier));
}

const PortalTextScalePreferenceScope: React.FC<PortalTextScalePreferenceScopeProps> = ({ storageKey }) => {
  const [scale, setScale] = useState<PortalTextScale>(() => readStoredScale(storageKey));
  const [mountTarget, setMountTarget] = useState<HTMLElement | null>(null);
  const [syncState, setSyncState] = useState<"idle" | "saving" | "saved" | "local">(
    () => getCachedUser() ? "idle" : "local",
  );

  useEffect(() => {
    applyScale(scale);
  }, [scale]);

  useEffect(() => {
    // The appearance manager is mounted at the application root, including on
    // public login routes. Account preferences are authenticated data; do not
    // probe the endpoint for an anonymous visitor and generate a routine 401.
    if (!getCachedUser()) return;
    let cancelled = false;
    void getPortalPreferences()
      .then((preferences) => {
        if (cancelled || !isTextScale(preferences.text_scale)) return;
        window.localStorage.setItem(storageKey, preferences.text_scale);
        setScale(preferences.text_scale);
        setSyncState("saved");
      })
      .catch(() => {
        if (!cancelled) setSyncState("local");
      });
    return () => {
      cancelled = true;
    };
  }, [storageKey]);

  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key !== storageKey || !isTextScale(event.newValue)) return;
      setScale(event.newValue);
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [storageKey]);

  useEffect(() => {
    let activeHost: HTMLDivElement | null = null;

    const syncMount = () => {
      const appearance = document.querySelector<HTMLElement>(".tenant-shell__appearance");
      if (!appearance) {
        if (activeHost && !activeHost.isConnected) activeHost = null;
        setMountTarget(null);
        return;
      }

      let host = appearance.querySelector<HTMLDivElement>(".tenant-shell__text-scale-host");
      if (!host) {
        host = document.createElement("div");
        host.className = "tenant-shell__text-scale-host";
        appearance.append(host);
      }
      activeHost = host;
      setMountTarget((current) => current === host ? current : host);
    };

    syncMount();
    const observer = new MutationObserver(syncMount);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => {
      observer.disconnect();
      activeHost?.remove();
    };
  }, []);

  const chooseScale = (next: PortalTextScale) => {
    setScale(next);
    window.localStorage.setItem(storageKey, next);
    if (!getCachedUser()) {
      setSyncState("local");
      return;
    }
    setSyncState("saving");
    void updatePortalPreferences({ text_scale: next })
      .then((preferences) => {
        const confirmed = isTextScale(preferences.text_scale) ? preferences.text_scale : next;
        window.localStorage.setItem(storageKey, confirmed);
        setScale(confirmed);
        setSyncState("saved");
      })
      .catch(() => setSyncState("local"));
  };

  if (!mountTarget) return null;

  return createPortal(
    <section className="tenant-shell__text-scale" aria-label="Text size preference">
      <div className="tenant-shell__text-scale-heading">
        <ALargeSmall size={17} aria-hidden="true" />
        <span>
          <strong>Text size</strong>
          <small>{syncState === "saving" ? "Saving…" : syncState === "local" ? "Saved on this device" : "Saved for your account"}</small>
        </span>
      </div>
      <div className="tenant-shell__text-scale-options" role="radiogroup" aria-label="Portal text size">
        {SCALE_OPTIONS.map((option) => (
          <button
            key={option.id}
            type="button"
            role="radio"
            aria-checked={scale === option.id}
            className={scale === option.id ? "is-selected" : ""}
            onClick={() => chooseScale(option.id)}
            title={option.description}
          >
            <span className="tenant-shell__text-scale-sample">{option.sample}</span>
            <span className="tenant-shell__text-scale-label">{option.label}</span>
            {scale === option.id ? <Check size={14} aria-hidden="true" /> : null}
          </button>
        ))}
      </div>
    </section>,
    mountTarget,
  );
};

const PortalTextScaleManager: React.FC = () => {
  const storageKey = preferenceStorageKey();
  return <PortalTextScalePreferenceScope key={storageKey} storageKey={storageKey} />;
};

export default PortalTextScaleManager;
