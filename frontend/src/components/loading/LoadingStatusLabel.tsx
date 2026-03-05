import React from "react";
import type { LoadingPhase } from "./GlobalLoadingProvider";

const phaseCopy: Record<LoadingPhase, string> = {
  initializing: "Initializing",
  loading: "Loading",
  validating: "Validating",
  verifying: "Verifying",
  generating: "Generating",
  finalizing: "Finalizing",
  syncing: "Syncing",
  refreshing: "Refreshing",
  preparing_download: "Preparing download",
  completing: "Completing",
};

const LoadingStatusLabel: React.FC<{ phase: LoadingPhase; message?: string }> = ({ phase, message }) => (
  <span className="loading-status-label">{message || phaseCopy[phase]}</span>
);

export default LoadingStatusLabel;
