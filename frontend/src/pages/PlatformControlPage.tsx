import React from "react";
import { useSearchParams } from "react-router-dom";

import PlatformAIPage from "./platform/PlatformAIPage";
import PlatformOperationsPage from "./platform/PlatformOperationsPage";

export default function PlatformControlPage() {
  const [searchParams] = useSearchParams();
  return searchParams.get("tab") === "ai" ? <PlatformAIPage /> : <PlatformOperationsPage />;
}
