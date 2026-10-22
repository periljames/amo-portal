import React, { Suspense, lazy, useEffect } from "react";
import { scheduleQmsOfflineWarmup } from "../../services/qmsOfflineWarmup";
import { useLocation } from "react-router-dom";

import { ModalTopLayerGuard } from "../shared/ModalTopLayerGuard";
const QmsCommandPalette = lazy(() => import("./QmsCommandPalette"));
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
      {commandPaletteRelevant ? <Suspense fallback={null}><QmsCommandPalette /></Suspense> : null}
      {relevant ? (
        <PortalErrorBoundary resetKey={location.pathname} inline title="Quality controls could not be displayed">
          <Suspense fallback={null}>
            <QualityEnhancementsHost />
          </Suspense>
        </PortalErrorBoundary>
      ) : null}
    </>
  );
};

export default QualityEnhancementsRouteGate;
