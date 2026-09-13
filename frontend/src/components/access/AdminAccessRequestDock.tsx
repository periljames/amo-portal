import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Clock3, Database, KeyRound, RefreshCw, ShieldX, X } from "lucide-react";
import { useLocation } from "react-router-dom";

import { useRealtime } from "../realtime/realtimeContext";
import {
  decideAccessElevationRequest,
  listAdminAccessElevationRequests,
  type AccessElevationRequest,
} from "../../services/accessProfiles";
import "./admin-access-request-dock.css";

function personLabel(item: AccessElevationRequest): string {
  return item.user_name?.trim() || item.user_email?.trim() || item.user_id;
}

export default function AdminAccessRequestDock() {
  const location = useLocation();
  const queryClient = useQueryClient();
  const { status: realtimeStatus, lastUpdated } = useRealtime();
  const [open, setOpen] = useState(false);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [feedback, setFeedback] = useState("");
  const params = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const visible = /\/admin\/users\/?$/.test(location.pathname) && params.get("tab") === "roles";

  const requests = useQuery({
    queryKey: ["access-elevation-requests", "admin", "ALL"],
    queryFn: () => listAdminAccessElevationRequests("ALL"),
    enabled: visible,
    staleTime: 3_000,
    refetchInterval: realtimeStatus === "live" ? false : 12_000,
    refetchOnWindowFocus: true,
  });

  const items = requests.data?.items || [];
  const pending = items.filter((item) => item.status === "PENDING");
  const recent = items.filter((item) => item.status !== "PENDING").slice(0, 8);

  const decide = useMutation({
    mutationFn: ({ item, decision }: { item: AccessElevationRequest; decision: "APPROVE" | "DENY" }) => (
      decideAccessElevationRequest(item.id, decision, notes[item.id])
    ),
    onSuccess: async (result) => {
      setFeedback(result.status === "APPROVED"
        ? `${personLabel(result)} was approved for ${result.requested_profile_name || "the requested profile"}.`
        : `${personLabel(result)} access request was denied.`);
      setNotes((current) => ({ ...current, [result.id]: "" }));
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["access-elevation-requests"] }),
        queryClient.invalidateQueries({ queryKey: ["accounts"] }),
        queryClient.invalidateQueries({ queryKey: ["admin-user-directory"] }),
      ]);
    },
    onError: (error: Error) => setFeedback(error.message),
  });

  if (!visible) return null;

  return <div className={`admin-access-request-dock${open ? " is-open" : ""}`}>
    {!open ? <button type="button" className="admin-access-request-dock__trigger" onClick={() => setOpen(true)}>
      <KeyRound size={17} /><span>Access requests</span>{pending.length ? <strong>{pending.length}</strong> : null}
    </button> : null}

    {open ? <aside className="admin-access-request-dock__panel" aria-label="Access request decisions">
      <header>
        <div><span>Access governance</span><h2>Approval queue</h2><p>Approve or decline ordinary portal access elevation. Protected appointments and certifying authority remain outside this queue.</p></div>
        <button type="button" onClick={() => setOpen(false)} aria-label="Close access request queue"><X size={18} /></button>
      </header>

      <div className="admin-access-request-dock__health">
        <span><Database size={14} /><strong>Server persisted</strong></span>
        <span className={`is-${realtimeStatus}`}>{realtimeStatus === "live" ? "Live sync" : realtimeStatus === "syncing" ? "Syncing" : "Offline fallback"}</span>
        <button type="button" onClick={() => void requests.refetch()} disabled={requests.isFetching}><RefreshCw size={14} className={requests.isFetching ? "is-spinning" : ""} /> Refresh</button>
        {lastUpdated ? <small>Last event {lastUpdated.toLocaleTimeString()}</small> : null}
      </div>

      {feedback ? <div className="admin-access-request-dock__feedback" role="status">{feedback}</div> : null}

      <section>
        <div className="admin-access-request-dock__section-title"><h3>Pending</h3><span>{pending.length}</span></div>
        {requests.isLoading ? <p className="admin-access-request-dock__empty">Loading requests…</p> : null}
        {requests.isError ? <p className="admin-access-request-dock__empty is-error">{requests.error instanceof Error ? requests.error.message : "Requests could not be loaded."}</p> : null}
        {!requests.isLoading && !pending.length ? <p className="admin-access-request-dock__empty">No pending access requests.</p> : null}
        <div className="admin-access-request-dock__requests">
          {pending.map((item) => <article key={item.id} className="admin-access-request-card">
            <div className="admin-access-request-card__heading"><div><strong>{personLabel(item)}</strong><small>{item.staff_code || item.user_email}</small></div><span><Clock3 size={13} /> Pending</span></div>
            <div className="admin-access-request-card__transition"><span>{item.current_profile_name || "Current access"}</span><b>→</b><strong>{item.requested_profile_name || item.requested_profile_code || "Requested access"}</strong></div>
            <p>{item.reason}</p>
            <small>Submitted {new Date(item.created_at).toLocaleString()}</small>
            <label><span>Decision note</span><textarea rows={2} value={notes[item.id] || ""} onChange={(event) => setNotes((current) => ({ ...current, [item.id]: event.target.value }))} placeholder="Optional approval note; give a reason when declining." /></label>
            <div className="admin-access-request-card__actions">
              <button type="button" className="is-approve" onClick={() => decide.mutate({ item, decision: "APPROVE" })} disabled={decide.isPending}><Check size={14} /> Approve & apply</button>
              <button type="button" className="is-deny" onClick={() => decide.mutate({ item, decision: "DENY" })} disabled={decide.isPending}><ShieldX size={14} /> Deny</button>
            </div>
          </article>)}
        </div>
      </section>

      <section>
        <div className="admin-access-request-dock__section-title"><h3>Recent decisions</h3><span>{recent.length}</span></div>
        <div className="admin-access-request-dock__recent">
          {recent.map((item) => <article key={item.id} className={`is-${item.status.toLowerCase()}`}>
            <div><strong>{personLabel(item)}</strong><span>{item.status}</span></div>
            <p>{item.requested_profile_name || item.requested_profile_code}</p>
            {item.decision_note ? <small>{item.decision_note}</small> : null}
          </article>)}
          {!recent.length ? <p className="admin-access-request-dock__empty">No recent decisions.</p> : null}
        </div>
      </section>
    </aside> : null}
  </div>;
}
