import React from "react";
import type { LoadingPhase } from "./GlobalLoadingProvider";
import InstrumentLoader from "./InstrumentLoader";

const SectionLoader: React.FC<{ title?: string; message?: string; phase?: LoadingPhase }> = ({
  title = "Refreshing section",
  message,
  phase = "refreshing",
}) => (
  <div className="section-loader">
    <InstrumentLoader size="md" tone="subtle" compact label={title} phase={phase} message={message} />
  </div>
);

export default SectionLoader;
