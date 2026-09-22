import React, { Suspense, lazy, useEffect } from "react";
import { scheduleQmsOfflineWarmup } from "../../services/qmsOfflineWarmup";
import { useLocation } from "react-router-dom";

import { ModalTopLayerGuard } from "../shared/ModalTopLayerGuard";
import QmsCommandPalette from "./QmsCommandPalette";

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
        <Suspense fallback={null}>
          <QualityEnhancementsHost />
        </Suspense>
      ) : null}
    </>
  );
};

export default QualityEnhancementsRouteGate;
