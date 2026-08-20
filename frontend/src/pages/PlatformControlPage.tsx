import React from "react";
import { Navigate, useSearchParams } from "react-router-dom";

import { getCachedUser, getContext } from "../services/auth";
import PlatformAIPage from "./platform/PlatformAIPage";
import PlatformOperationsPage from "./platform/PlatformOperationsPage";

export default function PlatformControlPage() {
  const [searchParams] = useSearchParams();
  const user = getCachedUser();

  // Do not mount platform-control children for tenant-bound sessions. Those
  // children start data loaders before PlatformShell can render its own access
  // denial, so guarding here prevents even unnecessary cross-scope API calls.
  if (!user?.is_superuser || user.amo_id) {
    const context = getContext();
    const tenant = context.amoSlug || context.amoCode;
    return <Navigate to={tenant ? `/maintenance/${encodeURIComponent(tenant)}` : "/login"} replace />;
  }

  return searchParams.get("tab") === "ai" ? <PlatformAIPage /> : <PlatformOperationsPage />;
}
