import { AlertTriangle, CloudOff, CloudUpload, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  getOfflineOutboxSummary,
  onOfflineStateChanged,
  replayOfflineMutations,
  type OfflineOutboxSummary,
} from "../../services/offlinePersistence";

const EMPTY: OfflineOutboxSummary = { queued: 0, syncing: 0, conflict: 0, failed: 0, total: 0 };

type IndicatorState = "online" | "offline" | "queued" | "syncing" | "conflict";

export function OfflineSyncIndicator() {
  const [online, setOnline] = useState(() => typeof navigator === "undefined" ? true : navigator.onLine);
  const [summary, setSummary] = useState<OfflineOutboxSummary>(EMPTY);
  const [manualSync, setManualSync] = useState(false);

  const refresh = useCallback(async () => {
    setSummary(await getOfflineOutboxSummary().catch(() => EMPTY));
  }, []);

  const sync = useCallback(async () => {
    if (manualSync || !online) return;
    setManualSync(true);
    try {
      setSummary(await replayOfflineMutations());
    } finally {
      setManualSync(false);
      await refresh();
    }
  }, [manualSync, online, refresh]);

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

  const state: IndicatorState = useMemo(() => {
    if (!online) return "offline";
    if (summary.conflict > 0 || summary.failed > 0) return "conflict";
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

  return (
    <button
      type="button"
      className="portal-offline-indicator"
      data-state={state}
      aria-label={title}
      title={title}
      onClick={() => void sync()}
      disabled={!online || manualSync}
    >
      <Icon size={18} aria-hidden="true" />
      {pending > 0 ? <span className="portal-offline-indicator__count">{pending > 99 ? "99+" : pending}</span> : null}
    </button>
  );
}

export default OfflineSyncIndicator;
