import React, { useEffect, useMemo } from "react";
import { useLocation, useSearchParams } from "react-router-dom";

import PublicCarInvitePage from "./PublicCarInvitePage";

/**
 * Canonical QMS guest CAR route adapter.
 *
 * The established CAR response workspace consumes its invitation from the
 * `token` query parameter. The canonical QMS information architecture exposes
 * that same governed workflow at `/qms/car-access/:token`. Keep the canonical
 * path in place and mirror its path token into the existing query contract so
 * no second CAR implementation or weaker access path is introduced.
 */
const CanonicalPublicCarAccessPage: React.FC = () => {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const routeToken = useMemo(() => {
    const match = location.pathname.match(/^\/qms\/car-access\/([^/]+)\/?$/i);
    if (!match?.[1]) return "";
    try {
      return decodeURIComponent(match[1]);
    } catch {
      return "";
    }
  }, [location.pathname]);
  const queryToken = searchParams.get("token") || "";

  useEffect(() => {
    if (!routeToken || queryToken === routeToken) return;
    const next = new URLSearchParams(searchParams);
    next.set("token", routeToken);
    setSearchParams(next, { replace: true });
  }, [queryToken, routeToken, searchParams, setSearchParams]);

  // Do not mount the legacy workspace until the canonical path token has been
  // mirrored into its established token contract; otherwise it would latch an
  // initial "Invite token missing" state before the URL update completes.
  if (routeToken && queryToken !== routeToken) {
    return <div role="status" aria-live="polite">Opening corrective action response…</div>;
  }

  return <PublicCarInvitePage />;
};

export default CanonicalPublicCarAccessPage;
