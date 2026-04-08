import React, { useMemo, useState } from "react";
import { RefreshCw, Wifi, WifiOff } from "lucide-react";
import { useRealtime } from "./realtimeContext";

const formatTime = (value: Date | null): string => {
  if (!value) return "--";
  return value.toLocaleTimeString();
};

type DisplayState = "live" | "syncing" | "offline";

const buildDisplayState = (params: {
  status: string;
  brokerState: string;
  backendHealth: string;
  isOnline: boolean;
  staleSeconds: number;
}): DisplayState => {
  if (!params.isOnline) return "offline";
  if (params.backendHealth === "ok" && params.staleSeconds < 180) return "live";
  if (params.status === "live" && params.staleSeconds < 180) return "live";
  if (params.brokerState === "connected" && params.staleSeconds < 180) return "live";
  return "offline";
};

const statusLabel = (displayState: DisplayState): string => {
  switch (displayState) {
    case "live":
      return "Live";
    case "syncing":
      return "Live";
    case "offline":
      return "Offline";
    default:
      return "--";
  }
};

const LiveStatusIndicator: React.FC<{ compact?: boolean }> = ({ compact = false }) => {
  const {
    status,
    brokerState,
    backendHealth,
    lastGoodServerTime,
    lastUpdated,
    currentTime,
    staleSeconds,
    isOnline,
    clockSource,
    refreshData,
    triggerSync,
  } = useRealtime();
  const [menuOpen, setMenuOpen] = useState(false);

  const displayState = useMemo(
    () => buildDisplayState({ status, brokerState, backendHealth, isOnline, staleSeconds }),
    [backendHealth, brokerState, isOnline, staleSeconds, status]
  );
  const label = useMemo(() => statusLabel(displayState), [displayState]);
  const showOfflineIcon = displayState === "offline";
  const showSyncIcon = displayState === "syncing";
  const isLongConnectionIssue = displayState === "offline" && staleSeconds >= 180;

  if (compact) {
    return (
      <div className={`live-status live-status--compact live-status--compact-${displayState}`} aria-label={label}>
        {showOfflineIcon ? <WifiOff size={16} aria-hidden="true" /> : <Wifi size={16} aria-hidden="true" />}
      </div>
    );
  }

  return (
    <div className="live-status" onBlur={() => setMenuOpen(false)}>
      <button
        type="button"
        className={`live-status__chip live-status__chip--${displayState}`}
        onClick={() => setMenuOpen((prev) => !prev)}
      >
        {showOfflineIcon ? (
          <span
            className={`live-status__connection-icon ${isLongConnectionIssue ? "is-critical" : ""}`}
            aria-hidden="true"
            title="Network connection issue"
          >
            <WifiOff size={12} />
          </span>
        ) : showSyncIcon ? (
          <span className="live-status__connection-icon live-status__connection-icon--syncing" aria-hidden="true" title="Realtime stream reconnecting">
            <RefreshCw size={12} />
          </span>
        ) : null}
        <span className="live-status__dot" />
        {label}
        <span className="live-status__time">{formatTime(currentTime)}</span>
      </button>
      {menuOpen && (
        <div className="live-status__menu" role="menu">
          <div className="live-status__meta">Last update: {formatTime(lastUpdated)}</div>
          <div className="live-status__meta">Broker: {brokerState}</div>
          <div className="live-status__meta">Backend: {backendHealth}</div>
          <div className="live-status__meta">Last good server time: {formatTime(lastGoodServerTime)}</div>
          {displayState === "offline" ? (
            <div className="live-status__meta">
              Connection issue for {Math.floor(staleSeconds / 60)}m {staleSeconds % 60}s.
            </div>
          ) : null}
          {displayState === "live" ? (
            <div className="live-status__meta">The portal is online and the last server heartbeat is within the accepted window.</div>
          ) : null}
          <div className="live-status__meta">Clock source: {clockSource === "server" ? "server-synced" : "local"}</div>
          <button type="button" onClick={() => refreshData()}>
            Refresh data
          </button>
          <button type="button" onClick={() => triggerSync()}>
            Sync now
          </button>
        </div>
      )}
    </div>
  );
};

export default LiveStatusIndicator;
