import React, { Suspense, lazy } from "react";
import { useLocation } from "react-router-dom";

import { ModalTopLayerGuard } from "../shared/ModalTopLayerGuard";

const QualityEnhancementsHost = lazy(
  () => import("./QualityEnhancementsHost"),
);

const QualityEnhancementsRouteGate: React.FC = () => {
  const location = useLocation();
  const checklistLibraryRoute = /^\/maintenance\/[^/]+\/(?:quality|qms)\/audits\/checklists\/?$/i.test(location.pathname);
  const relevant = !checklistLibraryRoute && (
    /^\/car-invite\/?$/i.test(location.pathname)
    || /^\/maintenance\/[^/]+(?:\/|$)/i.test(location.pathname)
    || /^\/platform(?:\/|$)/i.test(location.pathname)
  );

  return (
    <>
      <ModalTopLayerGuard />
      {relevant ? (
        <Suspense fallback={null}>
          <QualityEnhancementsHost />
        </Suspense>
      ) : null}
    </>
  );
};

export default QualityEnhancementsRouteGate;
