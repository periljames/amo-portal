import React, { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { useIsFetching, useIsMutating } from "@tanstack/react-query";

const MIN_VISIBLE_MS = 240;

const GlobalLoadingBar: React.FC = () => {
  const location = useLocation();
  const isFetching = useIsFetching();
  const isMutating = useIsMutating();
  const [routeChanging, setRouteChanging] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    setRouteChanging(true);
    const timer = window.setTimeout(() => setRouteChanging(false), 320);
    return () => window.clearTimeout(timer);
  }, [location.pathname, location.search]);

  const busy = useMemo(() => routeChanging || isFetching > 0 || isMutating > 0, [routeChanging, isFetching, isMutating]);

  useEffect(() => {
    if (busy) {
      setVisible(true);
      return;
    }
    const timer = window.setTimeout(() => setVisible(false), MIN_VISIBLE_MS);
    return () => window.clearTimeout(timer);
  }, [busy]);

  return (
    <div className={`global-loading-bar${visible ? " is-visible" : ""}`} aria-hidden={!visible}>
      <div className="global-loading-bar__track" />
      <div className="global-loading-bar__indicator" />
    </div>
  );
};

export default GlobalLoadingBar;
