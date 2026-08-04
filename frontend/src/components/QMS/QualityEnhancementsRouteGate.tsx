import React, { Suspense, lazy } from "react";
import { useLocation } from "react-router-dom";

const QualityEnhancementsHost = lazy(
  () => import("./QualityEnhancementsHost"),
);

const QualityEnhancementsRouteGate: React.FC = () => {
  const location = useLocation();
  const relevant = /^\/car-invite\/?$/i.test(location.pathname)
    || /^\/maintenance\/[^/]+(?:\/|$)/i.test(location.pathname)
    || /^\/platform(?:\/|$)/i.test(location.pathname);
  if (!relevant) return null;
  return (
    <Suspense fallback={null}>
      <QualityEnhancementsHost />
    </Suspense>
  );
};

export default QualityEnhancementsRouteGate;
