import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link2, RefreshCcw, ShieldCheck, Unlink } from "lucide-react";

import {
  createCalendarSubscription,
  getCalendarSubscriptionStatus,
  revokeCalendarSubscription,
  rotateCalendarSubscription,
  type CalendarSubscriptionLink,
} from "../../../services/rosteringControl";
import { errorMessage, formatDateTime } from "../rosterUi";

const CALENDAR_KEY = ["rostering", "self-service", "calendar-subscription"] as const;

export function CalendarSubscriptionSecurityPanel() {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [latestLink, setLatestLink] = useState<CalendarSubscriptionLink | null>(null);
  const query = useQuery({
    queryKey: CALENDAR_KEY,
    queryFn: getCalendarSubscriptionStatus,
    staleTime: 60_000,
  });
  const active = query.data?.active === true;

  const generate = async () => {
    setBusy("generate");
    setError(null);
    try {
      const link = await createCalendarSubscription();
      setLatestLink(link);
      await queryClient.invalidateQueries({ queryKey: CALENDAR_KEY });
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const rotate = async () => {
    if (!window.confirm("Rotate this calendar subscription? The previous calendar URL will stop working immediately.")) return;
    setBusy("rotate");
    setError(null);
    try {
      const link = await rotateCalendarSubscription();
      setLatestLink(link);
      await queryClient.invalidateQueries({ queryKey: CALENDAR_KEY });
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  const revoke = async () => {
    if (!window.confirm("Revoke this calendar subscription? External calendar apps using the current URL will stop receiving roster updates.")) return;
    setBusy("revoke");
    setError(null);
    try {
      await revokeCalendarSubscription();
      setLatestLink(null);
      await queryClient.invalidateQueries({ queryKey: CALENDAR_KEY });
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="wr-panel">
      <div className="wr-section-heading">
        <div>
          <span className="wr-eyebrow">Calendar subscription security</span>
          <h2><ShieldCheck size={19} /> Personal operations calendar</h2>
          <p>The subscription uses a random revocable bearer URL stored encrypted at rest. Rotation invalidates the previous URL.</p>
        </div>
        <span className="wr-header-badge">{active ? "ACTIVE" : "INACTIVE"}</span>
      </div>
      {error || query.error ? <div className="wr-inline-error" role="alert">{error || errorMessage(query.error)}</div> : null}
      <div className="wr-actions">
        {!active ? (
          <button type="button" className="wr-button wr-button--primary" disabled={busy === "generate" || query.isPending} onClick={() => void generate()}>
            <Link2 size={14} /> Create secure link
          </button>
        ) : (
          <>
            <button type="button" className="wr-button wr-button--secondary" disabled={busy === "rotate"} onClick={() => void rotate()}>
              <RefreshCcw size={14} /> Rotate link
            </button>
            <button type="button" className="wr-button wr-button--secondary" disabled={busy === "revoke"} onClick={() => void revoke()}>
              <Unlink size={14} /> Revoke link
            </button>
          </>
        )}
      </div>
      {latestLink ? (
        <div className="wr-inline-warning" role="status">
          New calendar URL created. Re-subscribe any external calendar that used the previous URL: <code>{latestLink.https_url}</code>
        </div>
      ) : null}
      {active && query.data?.rotated_at ? <small>Last rotated {formatDateTime(query.data.rotated_at)}</small> : null}
    </section>
  );
}
