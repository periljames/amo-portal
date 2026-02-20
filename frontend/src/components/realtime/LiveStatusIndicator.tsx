import React, { useMemo, useState } from "react";
import { WifiOff } from "lucide-react";
import { useRealtime } from "./realtimeContext";

const formatTime = (value: Date | null): string => {
  if (!value) return "--";
  return value.toLocaleTimeString();
};

const statusLabel = (status: string): string => {
  switch (status) {
    case "live":
      return "Live";
    case "syncing":
      return "Stream reconnecting";
    case "offline":
      return "Offline";
    default:
      return "--";
  }
};

const LiveStatusIndicator: React.FC = () => {
  const { status, brokerState, backendHealth, lastGoodServerTime, lastUpdated, currentTime, staleSeconds, isOnline, clockSource, refreshData, triggerSync } = useRealtime();
  const [menuOpen, setMenuOpen] = useState(false);

  const label = useMemo(() => statusLabel(status), [status]);
  const hasTransportIssue = status !== "live" || !isOnline;
  const chipState = hasTransportIssue ? "offline" : status;
  const isLongConnectionIssue = hasTransportIssue && staleSeconds >= 180;

  return (
    <div className="live-status" onBlur={() => setMenuOpen(false)}>
      <button
        type="button"
        className={`live-status__chip live-status__chip--${chipState}`}
        onClick={() => setMenuOpen((prev) => !prev)}
      >
        {hasTransportIssue ? (
          <span
            className={`live-status__connection-icon ${isLongConnectionIssue ? "is-critical" : ""}`}
            aria-hidden="true"
            title="Network connection issue"
          >
            <WifiOff size={12} />
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
          {hasTransportIssue && (
            <div className="live-status__meta">
              Connection issue for {Math.floor(staleSeconds / 60)}m {staleSeconds % 60}s.
            </div>
          )}
          {!hasTransportIssue && brokerState !== "connected" && (
            <div className="live-status__meta">Broker reconnecting in background. Live stream remains active.</div>
          )}
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
