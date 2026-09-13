import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Clock3,
  KeyRound,
  RefreshCw,
  Send,
  ShieldAlert,
  ShieldCheck,
  X,
} from "lucide-react";

import { useRealtime } from "../realtime/realtimeContext";
import { getCachedUser } from "../../services/auth";
import {
  cancelAccessElevationRequest,
  getActiveTenantAccessProfiles,
  listMyAccessElevationRequests,
  requestAccessElevation,
  type AccessElevationRequest,
} from "../../services/accessProfiles";
import "./access-elevation-launcher.css";

const PROTECTED_MANAGEMENT = new Set([
  "ACCOUNTABLE_EXECUTIVE",
  "BASE_MAINTENANCE_MANAGER",
  "LINE_MAINTENANCE_MANAGER",
  "WORKSHOP_MANAGER",
  "QUALITY_MANAGER",
  "SAFETY_MANAGER",
  "SUPERUSER",
  "AMO_ADMIN",
]);

function statusCopy(request: AccessElevationRequest): string {
  if (request.status === "PENDING") return "Awaiting AMO administrator decision";
  if (request.status === "APPROVED") return "Approved and applied to your portal access";
  if (request.status === "DENIED") return request.decision_note || "Declined by the AMO administrator";
  return request.decision_note || "Request cancelled";
}

function statusIcon(request: AccessElevationRequest) {
  if (request.status === "APPROVED") return <CheckCircle2 size={15} />;
  if (request.status === "PENDING") return <Clock3 size={15} />;
  return <ShieldAlert size={15} />;
}

export default function AccessElevationLauncher() {
  const queryClient = useQueryClient();
  const { status: realtimeStatus, activity } = useRealtime();
  const user = getCachedUser();
  const [open, setOpen] = useState(false);
  const [profileId, setProfileId] = useState("");
  const [reason, setReason] = useState("");
  const [feedback, setFeedback] = useState("");
  const [lastDecisionEventId, setLastDecisionEventId] = useState("");

  const hidden = !user
    || Boolean(user.is_superuser)
    || Boolean(user.is_amo_admin)
    || PROTECTED_MANAGEMENT.has(user.role);

  const profiles = useQuery({
    queryKey: ["accounts", "requestable-access-profiles"],
    queryFn: getActiveTenantAccessProfiles,
    enabled: open && !hidden,
    staleTime: 30_000,
  });
  const requests = useQuery({
    queryKey: ["access-elevation-requests", "mine"],
    queryFn: listMyAccessElevationRequests,
    enabled: open && !hidden,
    staleTime: 5_000,
    refetchInterval: realtimeStatus === "live" ? false : 15_000,
    refetchOnWindowFocus: true,
  });

  const requestableProfiles = useMemo(
    () => (profiles.data || []).filter((profile) => (
      !profile.is_regulated
      && !PROTECTED_MANAGEMENT.has(profile.base_role_key)
      && profile.id !== user?.access_profile_id
    )),
    [profiles.data, user?.access_profile_id],
  );
  const history = requests.data?.items || [];
  const pending = history.find((item) => item.status === "PENDING") || null;
  const latestDecision = history.find((item) => item.status !== "PENDING") || null;

  useEffect(() => {
    const event = activity[0];
    if (!event || event.id === lastDecisionEventId || event.entityType !== "accounts.access_sync") return;
    const subjectUserId = String(event.metadata?.subjectUserId || "");
    const decisionStatus = String(event.metadata?.status || "");
    if (!user || subjectUserId !== user.id || !["APPROVED", "DENIED"].includes(decisionStatus)) return;
    setLastDecisionEventId(event.id);
    setFeedback(decisionStatus === "APPROVED"
      ? "Your access request was approved. The new portal access is being applied now."
      : "Your access request was declined. Open Request history to review the administrator’s reason.");
    void requests.refetch();
  }, [activity, lastDecisionEventId, requests, user]);

  const requestMutation = useMutation({
    mutationFn: () => requestAccessElevation(profileId, reason.trim()),
    onSuccess: async (result) => {
      setProfileId("");
      setReason("");
      setFeedback(`Request submitted for ${result.requested_profile_name || "the selected access profile"}.`);
      await queryClient.invalidateQueries({ queryKey: ["access-elevation-requests"] });
    },
    onError: (error: Error) => setFeedback(error.message),
  });

  const cancelMutation = useMutation({
    mutationFn: (requestId: string) => cancelAccessElevationRequest(requestId),
    onSuccess: async () => {
      setFeedback("Pending access request cancelled.");
      await queryClient.invalidateQueries({ queryKey: ["access-elevation-requests"] });
    },
    onError: (error: Error) => setFeedback(error.message),
  });

  if (hidden) return null;

  return <div className={`access-elevation-launcher${open ? " is-open" : ""}`}>
    {!open ? <button
      type="button"
      className="access-elevation-launcher__trigger"
      onClick={() => setOpen(true)}
      aria-label="Request additional portal access"
      title={feedback || "Request additional portal access"}
    >
      <KeyRound size={17} />
      <span>Request access</span>
      {pending ? <strong>1</strong> : latestDecision ? <i className={`is-${latestDecision.status.toLowerCase()}`} /> : null}
    </button> : null}

    {open ? <section className="access-elevation-launcher__panel" aria-label="Access request">
      <header>
        <div>
          <span className="access-elevation-launcher__eyebrow"><ShieldCheck size={14} /> Access governance</span>
          <h2>Request portal access</h2>
          <p>Ask for a tenant access profile needed for your work. Regulated appointments, certifying authority and administrator access use their separate governed workflows.</p>
        </div>
        <button type="button" className="access-elevation-launcher__close" onClick={() => setOpen(false)} aria-label="Close access request panel"><X size={18} /></button>
      </header>

      <div className="access-elevation-launcher__sync">
        <span className={`is-${realtimeStatus}`}>{realtimeStatus === "live" ? "Live sync" : realtimeStatus === "syncing" ? "Syncing" : "Offline fallback"}</span>
        <span>Current: <strong>{user?.access_profile_name || user?.role.replaceAll("_", " ")}</strong></span>
        <button type="button" onClick={() => void requests.refetch()} disabled={requests.isFetching}><RefreshCw size={14} className={requests.isFetching ? "is-spinning" : ""} /> Refresh</button>
      </div>

      {feedback ? <div className="access-elevation-launcher__feedback" role="status">{feedback}</div> : null}

      {pending ? <div className="access-elevation-launcher__pending">
        <div><Clock3 size={18} /><div><strong>{pending.requested_profile_name || "Access request"}</strong><span>{statusCopy(pending)}</span></div></div>
        <p>{pending.reason}</p>
        <button type="button" onClick={() => cancelMutation.mutate(pending.id)} disabled={cancelMutation.isPending}>{cancelMutation.isPending ? "Cancelling…" : "Cancel request"}</button>
      </div> : <div className="access-elevation-launcher__form">
        <label><span>Access profile needed</span><select value={profileId} onChange={(event) => setProfileId(event.target.value)} disabled={profiles.isLoading}>
          <option value="">Select access profile</option>
          {requestableProfiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.display_name} — {profile.category}</option>)}
        </select></label>
        <label><span>Why do you need this access?</span><textarea rows={4} minLength={8} maxLength={1000} value={reason} onChange={(event) => setReason(event.target.value)} placeholder="State the task, module or responsibility that requires the additional access." /></label>
        <button type="button" className="access-elevation-launcher__submit" disabled={!profileId || reason.trim().length < 8 || requestMutation.isPending} onClick={() => requestMutation.mutate()}>
          <Send size={15} /> {requestMutation.isPending ? "Submitting…" : "Submit for approval"}
        </button>
      </div>}

      <div className="access-elevation-launcher__history">
        <div className="access-elevation-launcher__history-heading"><strong>Request history</strong><span>{history.length} records</span></div>
        {requests.isLoading ? <p>Loading access requests…</p> : null}
        {requests.isError ? <p className="is-error">{requests.error instanceof Error ? requests.error.message : "Access requests could not be loaded."}</p> : null}
        {!requests.isLoading && !history.length ? <p>No access requests yet.</p> : null}
        {history.slice(0, 6).map((item) => <article key={item.id} className={`access-elevation-request is-${item.status.toLowerCase()}`}>
          <div className="access-elevation-request__title">{statusIcon(item)}<strong>{item.requested_profile_name || item.requested_profile_code || "Access profile"}</strong><span>{item.status}</span></div>
          <p>{statusCopy(item)}</p>
          {item.decision_note && item.status !== "DENIED" ? <small>Decision note: {item.decision_note}</small> : null}
          <small>Requested {new Date(item.created_at).toLocaleString()}{item.decided_by_name ? ` · decided by ${item.decided_by_name}` : ""}</small>
        </article>)}
      </div>
    </section> : null}
  </div>;
}