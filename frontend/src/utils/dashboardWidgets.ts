export type DashboardWidget = {
  id: string;
  label: string;
  description: string;
  departments: Array<
    | "planning"
    | "production"
    | "quality"
    | "safety"
    | "stores"
    | "engineering"
    | "workshops"
  >;
};

export const DASHBOARD_WIDGETS: DashboardWidget[] = [
  {
    id: "planning-capacity",
    label: "Planning capacity",
    description: "Slots, hangar availability, and upcoming checks.",
    departments: ["planning"],
  },
  {
    id: "fleet-readiness",
    label: "Fleet readiness",
    description: "Airworthiness status and upcoming events.",
    departments: ["planning", "quality"],
  },
  {
    id: "production-flow",
    label: "Production flow",
    description: "Work order throughput and CRS status.",
    departments: ["production"],
  },
  {
    id: "quality-actions",
    label: "Quality actions",
    description: "Open findings, CARs, and audit readiness.",
    departments: ["quality"],
  },
  {
    id: "safety-risk",
    label: "Safety risk",
    description: "Reports, mitigations, and safety actions.",
    departments: ["safety"],
  },
  {
    id: "stores-demand",
    label: "Stores demand",
    description: "Stockouts, reorder points, and inbound stock.",
    departments: ["stores"],
  },
  {
    id: "engineering-planning",
    label: "Engineering planning",
    description: "Deferred items, packages, and logs.",
    departments: ["engineering"],
  },
  {
    id: "workshop-capacity",
    label: "Workshop capacity",
    description: "Component throughput and turnaround.",
    departments: ["workshops"],
  },
];

export const getWidgetStorageKey = (
  amoCode: string,
  userId: string,
  department: string
): string => `amo_widgets_${amoCode}_${userId}_${department}`;

