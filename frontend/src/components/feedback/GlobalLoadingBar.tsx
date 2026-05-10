import React, { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useGlobalLoadingCount } from "../../services/loading";

const MIN_VISIBLE_MS = 180;
const ROUTE_CHANGE_MS = 240;
const MAX_VISIBLE_MS = 5000;

const GlobalLoadingBar: React.FC = () => {
  const location = useLocation();
  const foregroundLoadingCount = useGlobalLoadingCount();
  const [routeChanging, setRouteChanging] = useState(false);
  const [visible, setVisible] = useState(false);
  const lastShownAtRef = useRef<number>(0);

  useEffect(() => {
    setRouteChanging(true);
    const timer = window.setTimeout(() => setRouteChanging(false), ROUTE_CHANGE_MS);
    return () => window.clearTimeout(timer);
  }, [location.pathname, location.search]);

  const busy = useMemo(
    () => routeChanging || foregroundLoadingCount > 0,
    [foregroundLoadingCount, routeChanging]
  );

  useEffect(() => {
    if (busy) {
      if (!visible) {
        lastShownAtRef.current = Date.now();
        setVisible(true);
      }
      const hardStop = window.setTimeout(() => setVisible(false), MAX_VISIBLE_MS);
      return () => window.clearTimeout(hardStop);
    }
    const elapsed = Date.now() - lastShownAtRef.current;
    const delay = Math.max(MIN_VISIBLE_MS - elapsed, 0);
    const timer = window.setTimeout(() => setVisible(false), delay);
    return () => window.clearTimeout(timer);
  }, [busy, visible]);

  return (
    <div className={`global-loading-bar${visible ? " is-visible" : ""}`} aria-hidden={!visible}>
      <div className="global-loading-bar__track" />
      <div className="global-loading-bar__indicator" />
    </div>
  );
};

export default GlobalLoadingBar;
