import React from "react";
import type { LoadingPhase } from "./GlobalLoadingProvider";
import InstrumentLoader from "./InstrumentLoader";
import { SkeletonCard } from "./Skeletons";

const PageLoader: React.FC<{ title?: string; subtitle?: string; phase?: LoadingPhase; message?: string; contrast?: "normal" | "high" }> = ({
  title = "Loading",
  subtitle = "Preparing module workspace",
  phase = "loading",
  message,
  contrast = "normal",
}) => (
  <section className="page-loader" aria-live="polite" aria-busy="true">
    <InstrumentLoader size="xl" contrast={contrast} label={title} subtitle={subtitle} phase={phase} message={message} progressText="Systems active" />
    <div className="page-loader__skeletons">
      <SkeletonCard />
      <SkeletonCard />
    </div>
  </section>
);

export default PageLoader;
