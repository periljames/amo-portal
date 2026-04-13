import type { PortalUser } from "../services/auth";
import { getUserCapabilities, type RoleCapability } from "./roleAccess";

export type DashboardWidget = {
  id: string;
  label: string;
  description: string;
  departments: Array<
    | "planning"
    | "production"
    | "maintenance"
    | "quality"
    | "safety"
    | "stores"
    | "workshops"
  >;
  capabilities?: RoleCapability[];
};

export const DASHBOARD_WIDGETS: DashboardWidget[] = [
  {
    id: "planning-capacity",
    label: "Planning capacity",
    description: "Slots, hangar availability, and upcoming checks.",
    departments: ["planning"],
    capabilities: ["admin", "planner"],
  },
  {
    id: "fleet-readiness",
    label: "Fleet readiness",
    description: "Airworthiness status and upcoming events.",
    departments: ["planning", "quality"],
    capabilities: ["admin", "planner", "quality"],
  },
  {
    id: "production-flow",
    label: "Production flow",
    description: "Work order throughput and release status.",
    departments: ["production"],
    capabilities: ["admin", "supervisor", "certifying"],
  },
  {
    id: "technical-records-control",
    label: "Technical records control",
    description: "Record completeness, reconciliation, and handover readiness.",
    departments: ["production"],
    capabilities: ["admin", "supervisor", "records", "planner"],
  },
  {
    id: "maintenance-execution",
    label: "Maintenance execution",
    description: "Packages, defects, inspections, and closeout control.",
    departments: ["maintenance"],
    capabilities: ["admin", "supervisor", "certifying", "technician"],
  },
  {
    id: "quality-actions",
    label: "Quality actions",
    description: "Open findings, CARs, and audit readiness.",
    departments: ["quality"],
    capabilities: ["admin", "quality"],
  },
  {
    id: "safety-risk",
    label: "Safety risk",
    description: "Reports, mitigations, and safety actions.",
    departments: ["safety"],
    capabilities: ["admin", "safety"],
  },
  {
    id: "stores-demand",
    label: "Stores demand",
    description: "Stockouts, reorder points, and inbound stock.",
    departments: ["stores"],
    capabilities: ["admin", "stores"],
  },
  {
    id: "workshop-capacity",
    label: "Workshop capacity",
    description: "Component throughput and turnaround.",
    departments: ["workshops"],
    capabilities: ["admin"],
  },
];

export function canSeeDashboardWidget(
  widget: DashboardWidget,
  user: PortalUser | null,
  contextDepartment?: string | null
): boolean {
  if (!widget.capabilities || widget.capabilities.length === 0) return true;
  const capabilities = getUserCapabilities(user, contextDepartment);
  return widget.capabilities.some((cap) => capabilities.includes(cap));
}

export const getWidgetStorageKey = (
  amoCode: string,
  userId: string,
  department: string
): string => `amo_widgets_${amoCode}_${userId}_${department}`;
