import React, { useMemo, useState } from "react";
import { useRealtime } from "./RealtimeProvider";

const formatTime = (value: Date | null): string => {
  if (!value) return "--";
  return value.toLocaleTimeString();
};

const statusLabel = (status: string): string => {
  switch (status) {
    case "live":
      return "Live";
    case "syncing":
      return "Syncing";
    case "offline":
      return "Offline";
    default:
      return "--";
  }
};

const LiveStatusIndicator: React.FC = () => {
  const { status, lastUpdated, isStale, staleSeconds, refreshData, triggerSync } = useRealtime();
  const [menuOpen, setMenuOpen] = useState(false);

  const label = useMemo(() => {
    if (isStale && status === "live") return "Stale";
    return statusLabel(status);
  }, [isStale, status]);

  return (
    <div className="live-status" onBlur={() => setMenuOpen(false)}>
      <button
        type="button"
        className={`live-status__chip live-status__chip--${isStale ? "offline" : status}`}
        onClick={() => setMenuOpen((prev) => !prev)}
      >
        <span className="live-status__dot" />
        {label}
        <span className="live-status__time">{formatTime(lastUpdated)}</span>
      </button>
      {menuOpen && (
        <div className="live-status__menu" role="menu">
          <div className="live-status__meta">Last update: {formatTime(lastUpdated)}</div>
          {isStale && <div className="live-status__meta">Stream stale for {staleSeconds}s.</div>}
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
