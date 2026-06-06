import React, { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { useGlobalLoadingCount } from "../../services/loading";

const SHOW_DELAY_MS = 90;
const MIN_VISIBLE_MS = 120;
const ROUTE_SETTLE_MS = 140;
const MAX_VISIBLE_MS = 5000;

/**
 * A restrained global progress indicator.
 *
 * Fast client-side route changes should feel immediate, so the bar is only
 * shown when a transition or foreground request lasts long enough to be
 * perceptible. This avoids making every click look slower than it is.
 */
const GlobalLoadingBar: React.FC = () => {
  const location = useLocation();
  const foregroundLoadingCount = useGlobalLoadingCount();
  const [routeChanging, setRouteChanging] = useState(false);
  const [visible, setVisible] = useState(false);
  const lastShownAtRef = useRef<number>(0);
  const showTimerRef = useRef<number | null>(null);

  useEffect(() => {
    setRouteChanging(true);
    const timer = window.setTimeout(() => setRouteChanging(false), ROUTE_SETTLE_MS);
    return () => window.clearTimeout(timer);
  }, [location.pathname, location.search]);

  const busy = useMemo(
    () => routeChanging || foregroundLoadingCount > 0,
    [foregroundLoadingCount, routeChanging],
  );

  useEffect(() => {
    if (showTimerRef.current != null) {
      window.clearTimeout(showTimerRef.current);
      showTimerRef.current = null;
    }

    if (busy) {
      if (!visible) {
        showTimerRef.current = window.setTimeout(() => {
          lastShownAtRef.current = Date.now();
          setVisible(true);
          showTimerRef.current = null;
        }, SHOW_DELAY_MS);
      }
      const hardStop = window.setTimeout(() => setVisible(false), MAX_VISIBLE_MS);
      return () => {
        window.clearTimeout(hardStop);
        if (showTimerRef.current != null) {
          window.clearTimeout(showTimerRef.current);
          showTimerRef.current = null;
        }
      };
    }

    if (!visible) return undefined;
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
