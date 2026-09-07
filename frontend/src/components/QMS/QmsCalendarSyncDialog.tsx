import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarCheck2,
  CalendarPlus,
  Copy,
  Download,
  ExternalLink,
  RefreshCcw,
  ShieldCheck,
  Unlink,
  X,
} from "lucide-react";

import { getRosterCalendarSubscription } from "../../services/rostering";
import {
  createCalendarSubscription,
  getCalendarSubscriptionStatus,
  revokeCalendarSubscription,
  ROSTER_CALENDAR_LINK_QUERY_KEY,
  ROSTER_CALENDAR_STATUS_QUERY_KEY,
  rotateCalendarSubscription,
} from "../../services/rosteringControl";
import { resolveRosterCalendarUrls } from "../../pages/rostering/rosterUi";
import "../../styles/qms-calendar-sync.css";

type Props = {
  open: boolean;
  onClose: () => void;
};

function messageOf(value: unknown): string {
  return value instanceof Error && value.message ? value.message : "Calendar subscription could not be updated.";
}

export default function QmsCalendarSyncDialog({ open, onClose }: Props) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const statusQuery = useQuery({
    queryKey: ROSTER_CALENDAR_STATUS_QUERY_KEY,
    queryFn: getCalendarSubscriptionStatus,
    enabled: open,
    staleTime: 60_000,
  });
  const active = statusQuery.data?.active === true;
  const linkQuery = useQuery({
    queryKey: ROSTER_CALENDAR_LINK_QUERY_KEY,
    queryFn: getRosterCalendarSubscription,
    enabled: open && active,
    staleTime: 60 * 60_000,
  });
  const urls = useMemo(
    () => linkQuery.data
      ? resolveRosterCalendarUrls(linkQuery.data, {
          browserOrigin: typeof window === "undefined" ? null : window.location.origin,
          configuredApiOrigin: null,
        })
      : null,
    [linkQuery.data],
  );
  const googleUrl = urls
    ? `https://calendar.google.com/calendar/r?cid=${encodeURIComponent(urls.httpsUrl)}`
    : "";
  const outlookUrl = urls
    ? `https://outlook.live.com/calendar/0/addcalendar?url=${encodeURIComponent(urls.httpsUrl)}&name=${encodeURIComponent("AMO Portal operations")}`
    : "";

  if (!open) return null;

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ROSTER_CALENDAR_STATUS_QUERY_KEY, exact: true }),
      queryClient.invalidateQueries({ queryKey: ROSTER_CALENDAR_LINK_QUERY_KEY, exact: true }),
    ]);
  };

  const create = async () => {
    setBusy("create");
    setError(null);
    try {
      const link = await createCalendarSubscription();
      queryClient.setQueryData(ROSTER_CALENDAR_LINK_QUERY_KEY, link);
      queryClient.setQueryData(ROSTER_CALENDAR_STATUS_QUERY_KEY, link);
      await refresh();
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(null);
    }
  };

  const rotate = async () => {
    if (!window.confirm("Rotate the secure calendar URL? Calendars using the previous URL will stop updating.")) return;
    setBusy("rotate");
    setError(null);
    try {
      const link = await rotateCalendarSubscription();
      queryClient.setQueryData(ROSTER_CALENDAR_LINK_QUERY_KEY, link);
      queryClient.setQueryData(ROSTER_CALENDAR_STATUS_QUERY_KEY, link);
      await refresh();
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(null);
    }
  };

  const revoke = async () => {
    if (!window.confirm("Revoke the calendar URL? Connected calendar apps will stop receiving updates immediately.")) return;
    setBusy("revoke");
    setError(null);
    try {
      await revokeCalendarSubscription();
      queryClient.removeQueries({ queryKey: ROSTER_CALENDAR_LINK_QUERY_KEY, exact: true });
      await refresh();
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(null);
    }
  };

  const copy = async () => {
    if (!urls) return;
    try {
      await navigator.clipboard.writeText(urls.httpsUrl);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setError("The browser could not copy the address. Select the URL below and copy it manually.");
    }
  };

  return (
    <div className="qms-calendar-sync__backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="qms-calendar-sync" role="dialog" aria-modal="true" aria-labelledby="qms-calendar-sync-title">
        <header>
          <div>
            <span><CalendarCheck2 size={15} /> Automatic calendar updates</span>
            <h2 id="qms-calendar-sync-title">Sync the QMS calendar</h2>
            <p>One secure subscription keeps assigned audits, duty, training and operational commitments current in the calendar app you already use.</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close calendar sync"><X size={18} /></button>
        </header>

        <div className="qms-calendar-sync__assurance">
          <ShieldCheck size={18} />
          <div><strong>Personal, read-only and revocable</strong><span>Each user receives a unique bearer URL. Rotate or revoke it if it is shared accidentally.</span></div>
          <i className={active ? "is-active" : ""}>{active ? "Active" : "Not linked"}</i>
        </div>

        {error || statusQuery.error || linkQuery.error ? (
          <p className="qms-calendar-sync__error" role="alert">{error || messageOf(statusQuery.error || linkQuery.error)}</p>
        ) : null}

        {!active ? (
          <div className="qms-calendar-sync__empty">
            <CalendarPlus size={25} />
            <strong>Create your calendar subscription</strong>
            <span>After linking once, schedule changes appear without another portal login. Calendar apps normally refresh the feed within 60 minutes.</span>
            <button type="button" className="is-primary" disabled={busy === "create" || statusQuery.isPending} onClick={() => void create()}>
              <CalendarPlus size={15} /> {busy === "create" ? "Creating…" : "Create secure link"}
            </button>
          </div>
        ) : !urls ? (
          <p className="qms-calendar-sync__loading">Preparing your secure calendar address…</p>
        ) : (
          <>
            <label className="qms-calendar-sync__url">
              <span>Subscription URL</span>
              <div><input readOnly value={urls.httpsUrl} onFocus={(event) => event.currentTarget.select()} /><button type="button" onClick={() => void copy()}><Copy size={14} /> {copied ? "Copied" : "Copy"}</button></div>
            </label>
            <div className="qms-calendar-sync__platforms">
              <a className="is-primary" href={urls.webcalUrl}><CalendarPlus size={15} /> Apple / default app</a>
              <a href={googleUrl} target="_blank" rel="noreferrer">Google Calendar <ExternalLink size={14} /></a>
              <a href={outlookUrl} target="_blank" rel="noreferrer">Outlook <ExternalLink size={14} /></a>
              <a href={urls.httpsUrl} download="amo-portal-calendar.ics"><Download size={14} /> Download current feed</a>
            </div>
            <div className="qms-calendar-sync__scope">
              <strong>What updates automatically</strong>
              <ul>
                <li>Approved QMS audit schedules for each assigned auditor and internal auditee</li>
                <li>Reschedules, suspensions and live audit dates using stable event identifiers</li>
                <li>Published duty, training, maintenance and direct aircraft commitments</li>
              </ul>
              <small>External auditees without a portal account receive governed email notices; they do not receive a personal bearer feed.</small>
            </div>
            <footer>
              <button type="button" disabled={Boolean(busy)} onClick={() => void rotate()}><RefreshCcw size={14} /> Rotate URL</button>
              <button type="button" className="is-danger" disabled={Boolean(busy)} onClick={() => void revoke()}><Unlink size={14} /> Revoke</button>
            </footer>
          </>
        )}
      </section>
    </div>
  );
}
