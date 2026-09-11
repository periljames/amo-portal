import React, { Suspense, lazy } from "react";
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
  const commandPaletteRelevant = /^\/maintenance\/[^/]+(?:\/|$)/i.test(location.pathname);

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
