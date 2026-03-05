import React, { useEffect, useState } from "react";
import { useGlobalLoading } from "../../hooks/useGlobalLoading";
import { pickLoaderPresentation } from "./escalationRules";
import InstrumentLoader from "./InstrumentLoader";

const GlobalLoaderOverlay: React.FC = () => {
  const { tasks } = useGlobalLoading();
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!tasks.length) return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 200);
    return () => window.clearInterval(timer);
  }, [tasks.length]);

  if (!tasks.length) return null;

  const sorted = [...tasks].sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0));
  const activeTask = sorted[0];
  const elapsedMs = now - activeTask.started_at;
  const decision = pickLoaderPresentation(activeTask, elapsedMs);

  return (
    <>
      {decision.showOverlay ? (
        <div className="global-loader-overlay" role="status" aria-live="polite" aria-busy="true">
          <div className="global-loader-overlay__panel">
            <InstrumentLoader
              size="lg"
              tone="inverted"
              compact
              label={activeTask.label}
              phase={activeTask.phase}
              message={activeTask.message}
              progressText={activeTask.indeterminate ? "In progress" : `${activeTask.progress_percent ?? 0}%`}
            />
            {decision.showLongWaitHint ? <p className="loader-long-wait">Taking longer than usual. Please keep this tab open.</p> : null}
          </div>
        </div>
      ) : null}

      {decision.showDock ? (
        <div className="global-loader-dock" aria-live="polite" aria-atomic="true">
          <InstrumentLoader size="sm" compact tone="subtle" phase={activeTask.phase} message={activeTask.message} />
          <div className="global-loader-dock__copy">
            <strong>{activeTask.label}</strong>
            <span>{activeTask.message || activeTask.phase.replace("_", " ")}</span>
          </div>
        </div>
      ) : null}
    </>
  );
};

export default GlobalLoaderOverlay;
