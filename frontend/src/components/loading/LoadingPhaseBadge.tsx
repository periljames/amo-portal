import React from "react";
import type { LoadingPhase } from "./GlobalLoadingProvider";

const LoadingPhaseBadge: React.FC<{ phase: LoadingPhase }> = ({ phase }) => (
  <span className={`loading-phase-badge loading-phase-badge--${phase}`}>{phase.replace("_", " ")}</span>
);

export default LoadingPhaseBadge;
