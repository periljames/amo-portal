import {
  AlertTriangle,
  CloudOff,
  CloudUpload,
  RefreshCw,
  RotateCcw,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  discardOfflineMutation,
  getOfflineOutboxSummary,
  listOfflineMutations,
  onOfflineStateChanged,
  replayOfflineMutations,
  retryOfflineMutation,
  type OfflineOutboxEntry,
  type OfflineOutboxSummary,
} from "../../services/offlinePersistence";

const EMPTY: OfflineOutboxSummary = { queued: 0, syncing: 0, conflict: 0, failed: 0, total: 0 };

type IndicatorState = "online" | "offline" | "queued" | "syncing" | "conflict";

function entryLabel(entry: OfflineOutboxEntry): string {
  const entity = entry.entityType?.replace(/-/g, " ") || "offline change";
  return entry.entityId ? `${entity} ${entry.entityId}` : entity;
}

export function OfflineSyncIndicator() {
  const [online, setOnline] = useState(() => typeof navigator === "undefined" ? true : navigator.onLine);
  const [summary, setSummary] = useState<OfflineOutboxSummary>(EMPTY);
  const [reviewEntries, setReviewEntries] = useState<OfflineOutboxEntry[]>([]);
  const [manualSync, setManualSync] = useState(false);
  const [open, setOpen] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [nextSummary, entries] = await Promise.all([
      getOfflineOutboxSummary().catch(() => EMPTY),
      listOfflineMutations().catch(() => [] as OfflineOutboxEntry[]),
    ]);
    setSummary(nextSummary);
    const unresolved = entries.filter((entry) => entry.status === "conflict" || entry.status === "failed");
    setReviewEntries(unresolved);
    if (!unresolved.length) setOpen(false);
  }, []);

  const sync = useCallback(async () => {
    if (manualSync || !online) return;
    setManualSync(true);
    setActionError(null);
    try {
      setSummary(await replayOfflineMutations());
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setManualSync(false);
      await refresh();
    }
  }, [manualSync, online, refresh]);

  const retryEntry = useCallback(async (entry: OfflineOutboxEntry) => {
    if (busyId || !online) return;
    setBusyId(entry.id);
    setActionError(null);
    try {
      await retryOfflineMutation(entry.id);
      await replayOfflineMutations();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusyId(null);
      await refresh();
    }
  }, [busyId, online, refresh]);

  const discardEntry = useCallback(async (entry: OfflineOutboxEntry) => {
    if (busyId) return;
    const confirmed = window.confirm(
      "Discard this locally stored change? The pending edit will be removed and cannot be recovered.",
    );
    if (!confirmed) return;
    setBusyId(entry.id);
    setActionError(null);
    try {
      await discardOfflineMutation(entry.id);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusyId(null);
      await refresh();
    }
  }, [busyId, refresh]);

  useEffect(() => {
    const handleOnline = () => {
      setOnline(true);
      void replayOfflineMutations().then(setSummary).catch(() => undefined);
    };
    const handleOffline = () => setOnline(false);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    const removeOfflineListener = onOfflineStateChanged(() => void refresh());
    void refresh();
    if (navigator.onLine) void replayOfflineMutations().then(setSummary).catch(() => undefined);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
      removeOfflineListener();
    };
  }, [refresh]);

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  const state: IndicatorState = useMemo(() => {
    if (summary.conflict > 0 || summary.failed > 0) return "conflict";
    if (!online) return "offline";
    if (manualSync || summary.syncing > 0) return "syncing";
    if (summary.queued > 0) return "queued";
    return "online";
  }, [manualSync, online, summary]);

  if (state === "online") return null;

  const pending = summary.queued + summary.syncing + summary.conflict + summary.failed;
  const title = state === "offline"
    ? `${pending ? `${pending} change${pending === 1 ? "" : "s"} stored locally. ` : ""}Offline mode: cached data remains available.`
    : state === "conflict"
      ? `${summary.conflict + summary.failed} offline change${summary.conflict + summary.failed === 1 ? "" : "s"} need review.`
      : state === "syncing"
        ? `Synchronising ${pending} local change${pending === 1 ? "" : "s"}.`
        : `${summary.queued} change${summary.queued === 1 ? "" : "s"} waiting to sync.`;

  const Icon = state === "offline"
    ? CloudOff
    : state === "conflict"
      ? AlertTriangle
      : state === "syncing"
        ? RefreshCw
        : CloudUpload;

  const handleIndicatorClick = () => {
    if (state === "conflict") {
      setOpen((value) => !value);
      return;
    }
    void sync();
  };

  return (
    <>
      <button
        type="button"
        className="portal-offline-indicator"
        data-state={state}
        aria-label={title}
        aria-expanded={state === "conflict" ? open : undefined}
        aria-controls={state === "conflict" ? "portal-offline-recovery" : undefined}
        title={title}
        onClick={handleIndicatorClick}
        disabled={manualSync || (state !== "conflict" && !online)}
      >
        <Icon size={18} aria-hidden="true" />
        {pending > 0 ? <span className="portal-offline-indicator__count">{pending > 99 ? "99+" : pending}</span> : null}
      </button>

      {open && state === "conflict" ? (
        <section
          id="portal-offline-recovery"
          className="portal-offline-recovery"
          role="dialog"
          aria-modal="false"
          aria-labelledby="portal-offline-recovery-title"
        >
          <header className="portal-offline-recovery__header">
            <div>
              <strong id="portal-offline-recovery-title">Offline changes need review</strong>
              <span>{online ? "Retry after resolving the server record, or discard the local edit." : "Reconnect to retry, or discard the local edit."}</span>
            </div>
            <button
              type="button"
              className="portal-offline-recovery__close"
              onClick={() => setOpen(false)}
              aria-label="Close offline change review"
            >
              <X size={17} aria-hidden="true" />
            </button>
          </header>

          {actionError ? <p className="portal-offline-recovery__error" role="alert">{actionError}</p> : null}

          <div className="portal-offline-recovery__list">
            {reviewEntries.map((entry) => {
              const busy = busyId === entry.id;
              return (
                <article className="portal-offline-recovery__item" key={entry.id}>
                  <div className="portal-offline-recovery__item-copy">
                    <strong>{entryLabel(entry)}</strong>
                    <code>{entry.method} {entry.path}</code>
                    <span>{entry.error || "The server rejected this local change."}</span>
                  </div>
                  <div className="portal-offline-recovery__actions">
                    <button
                      type="button"
                      onClick={() => void retryEntry(entry)}
                      disabled={!online || Boolean(busyId)}
                      title={!online ? "Reconnect before retrying" : "Retry this local change"}
                    >
                      <RotateCcw size={15} aria-hidden="true" />
                      {busy ? "Working…" : "Retry"}
                    </button>
                    <button
                      type="button"
                      className="portal-offline-recovery__discard"
                      onClick={() => void discardEntry(entry)}
                      disabled={Boolean(busyId)}
                    >
                      <Trash2 size={15} aria-hidden="true" />
                      Discard
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      ) : null}
    </>
  );
}

export default OfflineSyncIndicator;
