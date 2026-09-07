import React from "react";
import { useSearchParams } from "react-router-dom";

import PlatformDashboardPage from "./platform/PlatformDashboardPage";
import PlatformOperationsPage from "./platform/PlatformOperationsPage";

export default function PlatformControlPage() {
  const [searchParams] = useSearchParams();
  return searchParams.get("view") === "operations" ? <PlatformOperationsPage /> : <PlatformDashboardPage />;
}
