import React from "react";
import type { LoadingPhase } from "./GlobalLoadingProvider";
import InstrumentLoader from "./InstrumentLoader";

const ProgressLoader: React.FC<{ label: string; phase?: LoadingPhase; message?: string; progressText?: string }> = ({
  label,
  phase = "loading",
  message,
  progressText,
}) => <InstrumentLoader size="md" tone="default" compact label={label} phase={phase} message={message} progressText={progressText} />;

export default ProgressLoader;
