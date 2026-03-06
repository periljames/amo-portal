import React from "react";
import InstrumentLoader from "./InstrumentLoader";

const InlineLoader: React.FC<{ label?: string }> = ({ label = "Working" }) => (
  <span className="inline-loader" role="status" aria-live="polite" aria-label={label}>
    <InstrumentLoader size="sm" compact tone="inverted" />
    {label}
  </span>
);

export default InlineLoader;
