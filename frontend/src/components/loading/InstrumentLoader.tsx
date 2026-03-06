import React, { useEffect, useMemo, useState } from "react";
import type { LoadingPhase } from "./GlobalLoadingProvider";
import LoadingPhaseBadge from "./LoadingPhaseBadge";
import LoadingStatusLabel from "./LoadingStatusLabel";
import { detectSystemContrastPreference, resolveLoaderContrast } from "./contrastMode";

type LoaderSize = "sm" | "md" | "lg" | "xl";
type LoaderTone = "default" | "subtle" | "inverted";
type LoaderContrast = "normal" | "high";

type InstrumentLoaderProps = {
  size?: LoaderSize;
  tone?: LoaderTone;
  contrast?: LoaderContrast;
  label?: string;
  subtitle?: string;
  phase?: LoadingPhase;
  message?: string;
  progressText?: string;
  compact?: boolean;
};

const InstrumentLoader: React.FC<InstrumentLoaderProps> = ({
  size = "md",
  tone = "default",
  contrast = "normal",
  label,
  subtitle,
  phase = "loading",
  message,
  progressText,
  compact = false,
}) => {
  const [prefersContrastMore, setPrefersContrastMore] = useState(false);
  const [forcedColors, setForcedColors] = useState(false);

  useEffect(() => {
    const detected = detectSystemContrastPreference();
    setPrefersContrastMore(detected.prefersContrastMore);
    setForcedColors(detected.forcedColors);
  }, []);

  const rootHighContrastClass = typeof document !== "undefined" && document.documentElement.classList.contains("amo-contrast-high");

  const resolvedContrast = useMemo(
    () =>
      resolveLoaderContrast({
        requested: contrast,
        prefersContrastMore,
        forcedColors,
        rootHighContrastClass,
      }),
    [contrast, prefersContrastMore, forcedColors, rootHighContrastClass]
  );

  const hasCopy = Boolean(label || subtitle || message || progressText);

  return (
    <div
      className={`instrument-loader instrument-loader--${size} instrument-loader--${tone} instrument-loader--contrast-${resolvedContrast} ${
        compact ? "is-compact" : ""
      }`.trim()}
    >
      <div className="instrument-loader__viz" aria-hidden>
        <span className="instrument-loader__ring" />
        <span className="instrument-loader__orbit" />
        <span className="instrument-loader__core" />
        <span className="instrument-loader__bar-track">
          <span className="instrument-loader__bar-fill" />
        </span>
        <span className="instrument-loader__waypoints">
          <i />
          <i />
          <i />
        </span>
      </div>
      {hasCopy ? (
        <div className="instrument-loader__copy" role="status" aria-live="polite" aria-busy="true">
          {label ? <strong>{label}</strong> : null}
          {subtitle ? <p>{subtitle}</p> : null}
          <div className="instrument-loader__meta">
            <LoadingPhaseBadge phase={phase} />
            <LoadingStatusLabel phase={phase} message={message} />
            {progressText ? <span className="instrument-loader__progress-text">{progressText}</span> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default InstrumentLoader;
