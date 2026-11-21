import React, { useEffect, useMemo } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { buildCarInviteHash, parseCarInviteLocation } from "../utils/carInviteUrl";

import PublicCarInvitePage from "./PublicCarInvitePage";

/**
 * Public CAR route adapter. Hold the bearer in the URL fragment and convert
 * previously issued path/query invitations to the canonical no-login route.
 */
const CanonicalPublicCarAccessPage: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const routeToken = useMemo(() => {
    const match = location.pathname.match(/^\/qms\/car-access\/([^/]+)\/?$/i);
    if (!match?.[1]) return "";
    try { return decodeURIComponent(match[1]); } catch { return ""; }
  }, [location.pathname]);
  const parsed = useMemo(
    () => parseCarInviteLocation(location.search, location.hash),
    [location.search, location.hash],
  );
  const fragmentToken = new URLSearchParams(location.hash.replace(/^#/, "")).get("token");
  const token = fragmentToken || routeToken || parsed.token;
  const canonicalHash = token ? buildCarInviteHash(token, parsed.captureMode) : "";
  const isCanonical = location.pathname.toLowerCase() === "/qms/car-access"
    && location.search === ""
    && location.hash === canonicalHash;

  useEffect(() => {
    if (!token || isCanonical) return;
    navigate({ pathname: "/qms/car-access", search: "", hash: canonicalHash }, { replace: true });
  }, [token, isCanonical, canonicalHash, navigate]);

  if (token && !isCanonical) {
    return <div role="status" aria-live="polite">Opening corrective action response…</div>;
  }
  return <PublicCarInvitePage />;
};

export default CanonicalPublicCarAccessPage;
