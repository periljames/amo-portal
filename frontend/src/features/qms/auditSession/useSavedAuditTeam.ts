import { useQueries } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";
import { getPortalConnectivity, onPortalConnectivityChange } from "../../../services/portalConnectivity";
import type { QMSAuditOut } from "../../../services/qms";
import { getAuditAssignmentEligibility } from "../../../services/qmsAuditAssignments";
import { AUDIT_TEAM_ROLES } from "./auditSetupControls";

const subscribeConnectivity = (listener: () => void) => onPortalConnectivityChange(listener);
const connectivityState = () => getPortalConnectivity().state;
export function useAuditAuthorityOnline() {
  return useSyncExternalStore(subscribeConnectivity, connectivityState, connectivityState) === "ONLINE";
}

export function useSavedAuditTeam(amoCode: string, audit?: QMSAuditOut) {
  const online = useAuditAuthorityOnline();
  const checks = useQueries({ queries: AUDIT_TEAM_ROLES.map(({ field, role }) => ({
    queryKey: ["qms-audit-assignment-eligibility", amoCode, audit?.id || "", role, audit?.[field] || ""],
    queryFn: ({ signal }: { signal: AbortSignal }) => getAuditAssignmentEligibility(amoCode, audit!.id, audit![field]!, role, signal),
    enabled: Boolean(audit?.id && audit[field]), staleTime: 30_000, retry: false, refetchOnMount: "always" as const,
  })) });
  const selected = checks.filter((_, index) => Boolean(audit?.[AUDIT_TEAM_ROLES[index].field]));
  const assigned = Boolean(audit?.lead_auditor_user_id);
  const pending = selected.some((check) => check.isPending);
  const unavailable = selected.some((check) => check.isError);
  const ready = online && assigned && !pending && !unavailable && selected.every((check) => check.data?.eligible === true);
  return { ready, pending, unavailable, message: !assigned ? "Assign a lead auditor."
    : !online ? "Reconnect to verify team eligibility and independence."
    : pending ? "Checking saved team eligibility and independence…"
    : unavailable ? "Team verification unavailable. Retry before continuing."
    : ready ? "Saved team verified."
    : "Saved team needs eligibility or independence review.",
  };
}
