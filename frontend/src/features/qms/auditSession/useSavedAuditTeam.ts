import { useQueries } from "@tanstack/react-query";
import { useEffect, useMemo, useSyncExternalStore } from "react";
import { getPortalConnectivity, onPortalConnectivityChange } from "../../../services/portalConnectivity";
import type { QMSAuditOut } from "../../../services/qms";
import { getAuditAssignmentEligibility } from "../../../services/qmsAuditAssignments";
import { AUDIT_TEAM_ROLES } from "./auditSetupControls";

const subscribeConnectivity = (listener: () => void) => onPortalConnectivityChange(listener);
const connectivityState = () => getPortalConnectivity().state;

export function useAuditAuthorityOnline() {
  return useSyncExternalStore(subscribeConnectivity, connectivityState, connectivityState) === "ONLINE";
}

export type SavedTeamCheck = {
  hasAssignee: boolean;
  eligible: boolean | null;
  pending: boolean;
  error: boolean;
  hasData: boolean;
};

export type SavedTeamStatus = {
  ready: boolean;
  pending: boolean;
  unavailable: boolean;
  message: string;
  /** True when readiness comes from a prior online verification while currently offline. */
  offlineTrusted: boolean;
};

type TeamVerificationRecord = {
  fingerprint: string;
  verifiedAt: number;
};

function teamAssignmentFingerprint(audit: Pick<
  QMSAuditOut,
  "id" | "lead_auditor_user_id" | "observer_auditor_user_id" | "assistant_auditor_user_id"
>): string {
  return [
    audit.id,
    audit.lead_auditor_user_id || "",
    audit.observer_auditor_user_id || "",
    audit.assistant_auditor_user_id || "",
  ].join("|");
}

function verificationStorageKey(amoCode: string, auditId: string): string {
  return `qms-audit-team-verified:v1:${amoCode}:${auditId}`;
}

export function readCachedTeamVerification(
  amoCode: string,
  auditId: string,
): TeamVerificationRecord | null {
  if (typeof sessionStorage === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(verificationStorageKey(amoCode, auditId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as TeamVerificationRecord;
    if (!parsed?.fingerprint || typeof parsed.verifiedAt !== "number") return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writeCachedTeamVerification(
  amoCode: string,
  auditId: string,
  fingerprint: string,
): void {
  if (typeof sessionStorage === "undefined") return;
  try {
    const payload: TeamVerificationRecord = {
      fingerprint,
      verifiedAt: Date.now(),
    };
    sessionStorage.setItem(
      verificationStorageKey(amoCode, auditId),
      JSON.stringify(payload),
    );
  } catch {
    // Private mode / quota — live query cache still covers the current session.
  }
}

export function clearCachedTeamVerification(amoCode: string, auditId: string): void {
  if (typeof sessionStorage === "undefined") return;
  try {
    sessionStorage.removeItem(verificationStorageKey(amoCode, auditId));
  } catch {
    // ignore
  }
}

/**
 * Resolve saved-team readiness for setup gating.
 * A prior successful online verification is trusted while offline for the same
 * assignment fingerprint — do not force reconnect just to re-check.
 */
export function resolveSavedTeamStatus(input: {
  online: boolean;
  assigned: boolean;
  checks: SavedTeamCheck[];
  cachedFingerprint?: string | null;
  currentFingerprint?: string | null;
}): SavedTeamStatus {
  const { online, assigned, checks } = input;
  if (!assigned) {
    return {
      ready: false,
      pending: false,
      unavailable: false,
      message: "Assign a lead auditor",
      offlineTrusted: false,
    };
  }

  const active = checks.filter((check) => check.hasAssignee);
  const liveVerified =
    active.length > 0 &&
    active.every((check) => check.hasData && check.eligible === true);
  const cacheTrusted =
    Boolean(input.cachedFingerprint) &&
    Boolean(input.currentFingerprint) &&
    input.cachedFingerprint === input.currentFingerprint;

  if (liveVerified || cacheTrusted) {
    return {
      ready: true,
      pending: false,
      unavailable: false,
      message: "",
      offlineTrusted: !online && !liveVerified && cacheTrusted,
    };
  }

  if (!online) {
    return {
      ready: false,
      pending: false,
      unavailable: false,
      message: "Reconnect to verify team",
      offlineTrusted: false,
    };
  }

  const pending = active.some((check) => check.pending && !check.hasData);
  if (pending) {
    return {
      ready: false,
      pending: true,
      unavailable: false,
      message: "Checking eligibility…",
      offlineTrusted: false,
    };
  }

  const unavailable = active.some((check) => check.error && !check.hasData);
  if (unavailable) {
    return {
      ready: false,
      pending: false,
      unavailable: true,
      message: "Verification unavailable — retry",
      offlineTrusted: false,
    };
  }

  return {
    ready: false,
    pending: false,
    unavailable: false,
    message: "Eligibility or independence issue",
    offlineTrusted: false,
  };
}

export function useSavedAuditTeam(amoCode: string, audit?: QMSAuditOut) {
  const online = useAuditAuthorityOnline();
  const fingerprint = audit ? teamAssignmentFingerprint(audit) : "";
  const cached = useMemo(
    () => (audit?.id ? readCachedTeamVerification(amoCode, audit.id) : null),
    // Re-read when assignment fingerprint changes or connectivity returns.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional fingerprint/online triggers
    [amoCode, audit?.id, fingerprint, online],
  );

  const checks = useQueries({
    queries: AUDIT_TEAM_ROLES.map(({ field, role }) => ({
      queryKey: [
        "qms-audit-assignment-eligibility",
        amoCode,
        audit?.id || "",
        role,
        audit?.[field] || "",
      ],
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        getAuditAssignmentEligibility(
          amoCode,
          audit!.id,
          audit![field]!,
          role,
          signal,
        ),
      // Skip network while offline so a prior success stays in the query cache.
      enabled: Boolean(online && audit?.id && audit[field]),
      staleTime: 5 * 60_000,
      gcTime: 24 * 60 * 60_000,
      retry: false,
      refetchOnMount: online ? ("always" as const) : false,
      refetchOnReconnect: true,
      networkMode: "online" as const,
    })),
  });

  const checkStates: SavedTeamCheck[] = AUDIT_TEAM_ROLES.map(({ field }, index) => {
    const query = checks[index];
    const hasAssignee = Boolean(audit?.[field]);
    return {
      hasAssignee,
      eligible: query?.data?.eligible ?? null,
      pending: Boolean(query?.isPending),
      error: Boolean(query?.isError),
      hasData: query?.data != null,
    };
  });

  const status = resolveSavedTeamStatus({
    online,
    assigned: Boolean(audit?.lead_auditor_user_id),
    checks: checkStates,
    cachedFingerprint: cached?.fingerprint || null,
    currentFingerprint: fingerprint || null,
  });

  const liveVerifiedSignature = checkStates
    .filter((check) => check.hasAssignee)
    .map((check) => `${check.eligible}:${check.hasData}`)
    .join(",");

  useEffect(() => {
    if (!audit?.id || !online || !fingerprint) return;
    const liveVerified =
      Boolean(audit.lead_auditor_user_id) &&
      checkStates.some((check) => check.hasAssignee) &&
      checkStates
        .filter((check) => check.hasAssignee)
        .every((check) => check.hasData && check.eligible === true);
    if (liveVerified) {
      writeCachedTeamVerification(amoCode, audit.id, fingerprint);
    }
  }, [amoCode, audit?.id, audit?.lead_auditor_user_id, fingerprint, liveVerifiedSignature, online]);

  useEffect(() => {
    if (audit?.id && !audit.lead_auditor_user_id) {
      clearCachedTeamVerification(amoCode, audit.id);
    }
  }, [amoCode, audit?.id, audit?.lead_auditor_user_id]);

  return status;
}
