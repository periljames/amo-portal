import type { DashboardConfig } from "./types";

const qualityDashboardConfig: DashboardConfig = {
  id: "quality",
  title: "Quality cockpit",
  departments: ["quality", "safety"],
  description: "QMS-focused cockpit with audit, CAR/CAPA, and document readiness signals.",
};

export default qualityDashboardConfig;
