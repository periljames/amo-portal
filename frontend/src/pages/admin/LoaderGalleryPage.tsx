import React, { useEffect, useState } from "react";
import PageHeader from "../../components/shared/PageHeader";
import SectionCard from "../../components/shared/SectionCard";
import InstrumentLoader from "../../components/loading/InstrumentLoader";
import PageLoader from "../../components/loading/PageLoader";
import SectionLoader from "../../components/loading/SectionLoader";
import InlineLoader from "../../components/loading/InlineLoader";
import { useGlobalLoading } from "../../hooks/useGlobalLoading";

const sizes = ["sm", "md", "lg", "xl"] as const;
const tones = ["default", "subtle", "inverted"] as const;

const LoaderGalleryPage: React.FC = () => {
  const [simulateReduced, setSimulateReduced] = useState(false);
  const [simulateHighContrast, setSimulateHighContrast] = useState(false);
  const { startLoading, stopLoading, updateLoading } = useGlobalLoading();

  useEffect(() => {
    document.documentElement.classList.toggle("amo-contrast-high", simulateHighContrast);
    return () => document.documentElement.classList.remove("amo-contrast-high");
  }, [simulateHighContrast]);

  const startOverlayDemo = () => {
    const id = startLoading({
      scope: "loader-gallery",
      label: "Gallery overlay demo",
      phase: "verifying",
      message: "Demonstrating escalation behavior",
      allow_overlay: true,
      mode_preference: "auto",
      affects_route: true,
    });
    window.setTimeout(() => updateLoading(id, { phase: "finalizing", message: "Still working" }), 3000);
    window.setTimeout(() => stopLoading(id), 6000);
  };

  const startDockDemo = () => {
    const id = startLoading({
      scope: "loader-gallery",
      label: "Gallery dock demo",
      phase: "generating",
      message: "Dock presentation only",
      mode_preference: "section",
      allow_overlay: false,
    });
    window.setTimeout(() => stopLoading(id), 4000);
  };

  return (
    <div className={simulateReduced ? "loader-gallery loader-gallery--reduced" : "loader-gallery"}>
      <PageHeader title="Loader Gallery" subtitle="Internal visual validation route for InstrumentLoader variants and escalation surfaces." />
      <SectionCard title="Controls">
        <label>
          <input type="checkbox" checked={simulateReduced} onChange={(e) => setSimulateReduced(e.target.checked)} /> Simulate reduced motion
        </label>
        <label>
          <input type="checkbox" checked={simulateHighContrast} onChange={(e) => setSimulateHighContrast(e.target.checked)} /> Simulate high contrast
        </label>
        <div className="esign-actions">
          <button type="button" onClick={startOverlayDemo}>Trigger overlay demo</button>
          <button type="button" onClick={startDockDemo}>Trigger dock demo</button>
        </div>
      </SectionCard>

      <SectionCard title="InstrumentLoader variants">
        <div className="loader-gallery__grid">
          {sizes.map((size) => (
            <div key={size} className="loader-gallery__cell">
              <h4>Size: {size}</h4>
              <InstrumentLoader size={size} label="Verifying" phase="verifying" message="Checking status" />
            </div>
          ))}
        </div>
        <div className="loader-gallery__grid">
          {tones.map((tone) => (
            <div key={tone} className="loader-gallery__cell loader-gallery__cell--dark">
              <h4>Tone: {tone}</h4>
              <InstrumentLoader tone={tone} size="md" label="Generating" phase="generating" message="Preparing output" compact />
            </div>
          ))}
        </div>
        <div className="loader-gallery__grid">
          <div className="loader-gallery__cell">
            <h4>Contrast: normal</h4>
            <InstrumentLoader size="md" contrast="normal" label="Loading" phase="loading" message="Standard readability" progressText="Systems active" />
          </div>
          <div className="loader-gallery__cell loader-gallery__cell--dark">
            <h4>Contrast: high</h4>
            <InstrumentLoader size="md" contrast="high" label="Loading" phase="loading" message="Sunlight readability" progressText="Systems active" />
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Loader surfaces">
        <div className="loader-gallery__stack">
          <PageLoader title="Page mode" subtitle="Route-level loading" phase="loading" message="Loading module data" />
          <PageLoader title="Page mode high contrast" subtitle="Public/outdoor readability" phase="verifying" message="Checking verification status" contrast="high" />
          <SectionLoader title="Section mode" phase="refreshing" message="Refreshing panel metrics" />
          <button type="button" className="loader-gallery__inline-btn">
            <InlineLoader label="Inline action" />
          </button>
        </div>
      </SectionCard>
    </div>
  );
};

export default LoaderGalleryPage;
