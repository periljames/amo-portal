import {
  AlertTriangle,
  CheckCircle2,
  CloudOff,
  CloudUpload,
  RefreshCw,
  RotateCcw,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { getCachedUser, getToken } from "../../services/auth";
import { hasTenantMessagingContext } from "../../services/messaging";
import {
  discardOfflineMutation,
  getOfflineOutboxSummary,
  listOfflineMutations,
  onOfflineReplayProgress,
  onOfflineStateChanged,
  replayOfflineMutations,
  retryOfflineMutation,
  type OfflineOutboxEntry,
  type OfflineOutboxSummary,
  type OfflineReplayProgress,
} from "../../services/offlinePersistence";
import {
  isQmsFieldworkConflict,
  keepServerVersionForQmsFieldwork,
  qmsFieldworkConflictSnapshot,
  reapplyQmsFieldworkConflict,
} from "../../services/qmsOfflineFieldworkConflict";
import {
  getPortalConnectivity,
  onPortalConnectivityChange,
  probePortalReadiness,
  type PortalConnectivitySnapshot,
} from "../../services/portalConnectivity";
import { MessagingHub } from "../messaging/MessagingHub";
import "../../styles/components/messaging.css";

const EMPTY: OfflineOutboxSummary = { queued: 0, syncing: 0, conflict: 0, failed: 0, total: 0 };
const EMPTY_PROGRESS: OfflineReplayProgress = {
  scope: "",
  phase: "idle",
  current: 0,
  total: 0,
  synced: 0,
};

type IndicatorState = "online" | "offline" | "degraded" | "queued" | "syncing" | "conflict";

function entryLabel(entry: OfflineOutboxEntry): string {
  if (entry.entityType === "qms-audit-checklist-item") return "Audit checklist fieldwork";
  const entity = entry.entityType?.replace(/-/g, " ") || "local change";
  return entity.replace(/^./, (letter) => letter.toUpperCase());
}

function formatLastReady(value: number | null): string {
  if (!value) return "Not yet connected";
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

function compactFieldworkState(value: Record<string, unknown> | null): string {
  if (!value) return "Unavailable";
  const response = typeof value.canonical_response_status === "string" ? value.canonical_response_status.replaceAll("_", " ") : "Not recorded";
  const notes = typeof value.auditor_notes === "string" && value.auditor_notes.trim() ? ` · ${value.auditor_notes.trim().slice(0, 160)}` : "";
  return `${response}${notes}`;
}

export function OfflineSyncIndicator() {
  const [connectivity, setConnectivity] = useState<PortalConnectivitySnapshot>(getPortalConnectivity);
  const [summary, setSummary] = useState<OfflineOutboxSummary>(EMPTY);
  const [entries, setEntries] = useState<OfflineOutboxEntry[]>([]);
  const [progress, setProgress] = useState<OfflineReplayProgress>(EMPTY_PROGRESS);
  const [manualSync, setManualSync] = useState(false);
  const [open, setOpen] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const online = connectivity.state === "ONLINE";

  const refresh = useCallback(async () => {
    const [nextSummary, nextEntries] = await Promise.all([
      getOfflineOutboxSummary().catch(() => EMPTY),
      listOfflineMutations().catch(() => [] as OfflineOutboxEntry[]),
    ]);
    setSummary(nextSummary);
    setEntries(nextEntries);
  }, []);

  const sync = useCallback(async () => {
    if (manualSync) return;
    if (!online) {
      void probePortalReadiness(true);
      return;
    }
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

  const reapplyQmsEntry = useCallback(async (entry: OfflineOutboxEntry) => {
    if (busyId) return;
    const snapshot = qmsFieldworkConflictSnapshot(entry);
    if (!snapshot) {
      setActionError("The server version for this checklist item is unavailable. Reopen the audit online before retrying.");
      return;
    }
    const confirmed = window.confirm(
      `Reapply your saved fieldwork against server version ${snapshot.serverVersion}? This creates a new attributable mutation and preserves the rejected attempt in audit history.`,
    );
    if (!confirmed) return;
    setBusyId(entry.id);
    setActionError(null);
    try {
      await reapplyQmsFieldworkConflict(entry);
      if (online) await replayOfflineMutations();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusyId(null);
      await refresh();
    }
  }, [busyId, online, refresh]);

  const keepServerQmsEntry = useCallback(async (entry: OfflineOutboxEntry) => {
    if (busyId) return;
    const confirmed = window.confirm(
      "Keep the current server version and discard this local fieldwork attempt? The local queued copy will be removed.",
    );
    if (!confirmed) return;
    setBusyId(entry.id);
    setActionError(null);
    try {
      await keepServerVersionForQmsFieldwork(entry);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusyId(null);
      await refresh();
    }
  }, [busyId, refresh]);

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
    const removeConnectivity = onPortalConnectivityChange((next) => {
      setConnectivity(next);
      void refresh();
    });
    const removeState = onOfflineStateChanged(() => void refresh());
    const removeProgress = onOfflineReplayProgress((next) => {
      setProgress(next);
      void refresh();
    });
    void refresh();
    return () => {
      removeConnectivity();
      removeState();
      removeProgress();
    };
  }, [refresh]);

  useEffect(() => {
    if (!online || summary.queued <= 0) return;
    const timer = window.setInterval(() => void replayOfflineMutations().then(() => refresh()), 15_000);
    return () => window.clearInterval(timer);
  }, [online, refresh, summary.queued]);

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
    if (manualSync || progress.phase === "sending" || summary.syncing > 0) return "syncing";
    if (connectivity.state === "DEGRADED" || connectivity.state === "RECOVERING") return "degraded";
    if (!online) return "offline";
    if (summary.queued > 0) return "queued";
    return "online";
  }, [connectivity.state, manualSync, online, progress.phase, summary]);

  const showMessaging = hasTenantMessagingContext(getCachedUser(), getToken());
  if (state === "online") return showMessaging ? <MessagingHub /> : null;

  const pending = summary.total;
  const issueCount = summary.conflict + summary.failed;
  const title = state === "degraded"
    ? "Server reachable; database recovery in progress"
    : state === "offline"
      ? `${pending ? `${pending} change${pending === 1 ? "" : "s"} saved locally. ` : ""}Portal connection unavailable.`
      : state === "conflict"
        ? `${issueCount} local change${issueCount === 1 ? "" : "s"} need review.`
        : state === "syncing"
          ? progress.message || `Synchronising ${pending} local change${pending === 1 ? "" : "s"}.`
          : `${summary.queued} change${summary.queued === 1 ? "" : "s"} waiting to sync.`;

  const Icon = state === "offline"
    ? CloudOff
    : state === "conflict"
      ? AlertTriangle
      : state === "syncing" || state === "degraded"
        ? RefreshCw
        : CloudUpload;
  const progressPercent = progress.total > 0
    ? Math.min(100, Math.max(4, Math.round((progress.current / progress.total) * 100)))
    : state === "syncing" ? 8 : 0;
  const reviewEntries = entries.filter((entry) => entry.status === "conflict" || entry.status === "failed");

  return (
    <>
      {showMessaging ? <MessagingHub /> : null}
      <button
        type="button"
        className="portal-offline-indicator"
        data-state={state}
        aria-label={title}
        aria-expanded={open}
        aria-controls="portal-offline-recovery"
        title={title}
        onClick={() => setOpen((value) => !value)}
      >
        <Icon size={18} aria-hidden="true" />
        {pending > 0 ? <span className="portal-offline-indicator__count">{pending > 99 ? "99+" : pending}</span> : null}
      </button>

      {open ? (
        <section
          id="portal-offline-recovery"
          className="portal-offline-recovery"
          role="dialog"
          aria-modal="false"
          aria-labelledby="portal-offline-recovery-title"
        >
          <header className="portal-offline-recovery__header">
            <div>
              <strong id="portal-offline-recovery-title">Connection &amp; sync</strong>
              <span>{title}</span>
            </div>
            <button type="button" className="portal-offline-recovery__close" onClick={() => setOpen(false)} aria-label="Close connection and sync panel">
              <X size={17} aria-hidden="true" />
            </button>
          </header>

          <div className="portal-offline-recovery__status" data-state={state}>
            {online ? <CheckCircle2 size={17} aria-hidden="true" /> : <Icon size={17} aria-hidden="true" />}
            <div>
              <strong>{online ? "Server ready" : connectivity.reason || "Connection unavailable"}</strong>
              <span>Last connected {formatLastReady(connectivity.lastReadyAt)}</span>
            </div>
          </div>

          {(progress.phase === "sending" || manualSync) ? (
            <div className="portal-offline-recovery__progress" aria-live="polite">
              <div><strong>{progress.message || "Synchronising local changes"}</strong><span>{progressPercent}%</span></div>
              <progress max="100" value={progressPercent}>{progressPercent}%</progress>
            </div>
          ) : null}

          <div className="portal-offline-recovery__summary">
            <span><strong>{summary.queued + summary.syncing}</strong> waiting</span>
            <span><strong>{issueCount}</strong> review</span>
            <span><strong>{connectivity.attempt}</strong> retry attempt{connectivity.attempt === 1 ? "" : "s"}</span>
          </div>

          {actionError ? <p className="portal-offline-recovery__error" role="alert">{actionError}</p> : null}

          {reviewEntries.length ? (
            <div className="portal-offline-recovery__list">
              <strong className="portal-offline-recovery__review-title">Offline changes need review</strong>
              {reviewEntries.map((entry) => {
                const busy = busyId === entry.id;
                const qmsConflict = isQmsFieldworkConflict(entry);
                const snapshot = qmsConflict ? qmsFieldworkConflictSnapshot(entry) : null;
                return (
                  <article className="portal-offline-recovery__item" key={entry.id}>
                    <div className="portal-offline-recovery__item-copy">
                      <strong>{entryLabel(entry)}</strong>
                      <span>{entry.serverDetail || entry.error || "The server rejected this local change."}</span>
                      {snapshot ? (
                        <details>
                          <summary>Compare saved and server versions</summary>
                          <dl>
                            <div><dt>Saved base version</dt><dd>{snapshot.baseVersion ?? "Unknown"}</dd></div>
                            <div><dt>Current server version</dt><dd>{snapshot.serverVersion}</dd></div>
                            <div><dt>Your saved response</dt><dd>{compactFieldworkState(snapshot.localBody)}</dd></div>
                            <div><dt>Current server response</dt><dd>{compactFieldworkState(snapshot.serverRow)}</dd></div>
                          </dl>
                        </details>
                      ) : null}
                      {entry.retryable === false ? <small>Correct the source record, then recreate this item.</small> : null}
                    </div>
                    <div className="portal-offline-recovery__actions">
                      {qmsConflict ? (
                        <>
                          <button type="button" onClick={() => void reapplyQmsEntry(entry)} disabled={Boolean(busyId)}>
                            <RotateCcw size={15} aria-hidden="true" />{busy ? "Working…" : "Reapply my change"}
                          </button>
                          <button type="button" className="portal-offline-recovery__discard" onClick={() => void keepServerQmsEntry(entry)} disabled={Boolean(busyId)}>
                            <CheckCircle2 size={15} aria-hidden="true" />Keep server version
                          </button>
                        </>
                      ) : (
                        <>
                          {entry.retryable !== false ? (
                            <button type="button" onClick={() => void retryEntry(entry)} disabled={!online || Boolean(busyId)}>
                              <RotateCcw size={15} aria-hidden="true" />{busy ? "Working…" : "Retry"}
                            </button>
                          ) : null}
                          <button type="button" className="portal-offline-recovery__discard" onClick={() => void discardEntry(entry)} disabled={Boolean(busyId)}>
                            <Trash2 size={15} aria-hidden="true" />Discard
                          </button>
                        </>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          ) : null}

          <footer className="portal-offline-recovery__footer">
            <button type="button" onClick={() => void probePortalReadiness(true)} disabled={manualSync}>
              <RefreshCw size={15} aria-hidden="true" />Check server
            </button>
            {summary.queued > 0 ? (
              <button type="button" className="portal-offline-recovery__primary" onClick={() => void sync()} disabled={!online || manualSync}>
                <CloudUpload size={15} aria-hidden="true" />Sync now
              </button>
            ) : null}
          </footer>
        </section>
      ) : null}
    </>
  );
}

export default OfflineSyncIndicator;
