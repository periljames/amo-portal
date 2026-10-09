import React, { Suspense, lazy, useEffect } from "react";
import { scheduleQmsOfflineWarmup } from "../../services/qmsOfflineWarmup";
import { useLocation } from "react-router-dom";

import { ModalTopLayerGuard } from "../shared/ModalTopLayerGuard";
import QmsCommandPalette from "./QmsCommandPalette";
import PortalErrorBoundary from "../feedback/PortalErrorBoundary";

const QualityEnhancementsHost = lazy(
  () => import("./QualityEnhancementsHost"),
);

const QualityEnhancementsRouteGate: React.FC = () => {
  const location = useLocation();
  const relevant = /^\/car-invite\/?$/i.test(location.pathname)
    || /^\/maintenance\/[^/]+(?:\/|$)/i.test(location.pathname)
    || /^\/platform(?:\/|$)/i.test(location.pathname);
  const commandPaletteRelevant = /^\/maintenance\/[^/]+\/quality(?:\/|$)/i.test(location.pathname);
  useEffect(() => {
    if (commandPaletteRelevant) return scheduleQmsOfflineWarmup();
  }, [commandPaletteRelevant]);

  return (
    <>
      <ModalTopLayerGuard />
      {commandPaletteRelevant ? <QmsCommandPalette /> : null}
      {relevant ? (
        <PortalErrorBoundary key={location.pathname}>
          <Suspense fallback={<div role="status" className="qms-audit-stage-suspense">Loading workspace…</div>}>
            <QualityEnhancementsHost />
          </Suspense>
        </PortalErrorBoundary>
      ) : null}
    </>
  );
};

export default QualityEnhancementsRouteGate;
