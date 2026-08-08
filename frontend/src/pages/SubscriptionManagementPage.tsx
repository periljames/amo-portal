import React from "react";
import { Navigate, useLocation, useParams } from "react-router-dom";

/**
 * Legacy subscription route retained for bookmarked URLs only.
 *
 * All subscription ordering, invoice settlement, module upgrades, cancellations
 * and payment-provider handoff now live in the canonical tenant Billing workspace.
 * Keeping a second commerce UI previously allowed manually entered provider-token
 * metadata and the legacy pre-settlement purchase path to drift from the verified
 * invoice-first control plane.
 */
const SubscriptionManagementPage: React.FC = () => {
  const { amoCode } = useParams<{ amoCode?: string }>();
  const location = useLocation();
  const tenant = encodeURIComponent(amoCode || "UNKNOWN");
  const suffix = location.search || "";
  return <Navigate to={`/maintenance/${tenant}/admin/billing${suffix}`} replace />;
};

export default SubscriptionManagementPage;
