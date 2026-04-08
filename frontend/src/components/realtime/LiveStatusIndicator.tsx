import React, { useMemo, useState } from "react";
import { RefreshCw, Wifi, WifiOff } from "lucide-react";
import { useRealtime } from "./realtimeContext";

const formatTime = (value: Date | null): string => {
  if (!value) return "--";
  return value.toLocaleTimeString();
};

const CLOCK_FRESH_WINDOW_MS = 15 * 60_000;

const LiveStatusIndicator: React.FC<{ compact?: boolean }> = ({ compact = false }) => {
  const {
    status,
    brokerState,
    backendHealth,
    lastUpdated,
    currentTime,
    isOnline,
    clockSource,
    lastClockSyncAt,
    refreshData,
  } = useRealtime();
  const [menuOpen, setMenuOpen] = useState(false);

  const hasFreshClock = useMemo(() => {
    if (!lastClockSyncAt) return false;
    return Date.now() - lastClockSyncAt.getTime() <= CLOCK_FRESH_WINDOW_MS;
  }, [lastClockSyncAt]);

  const displayState = useMemo<"live" | "syncing" | "offline">(() => {
    if (!isOnline) return "offline";
    if (backendHealth === "degraded" && !hasFreshClock && status === "offline") return "offline";
    if (status === "live") return "live";
    if ((status === "syncing" || status === "offline") && (brokerState === "connected" || hasFreshClock || clockSource === "server")) {
      return "live";
    }
    if (status === "syncing") return "syncing";
    return "offline";
  }, [backendHealth, brokerState, clockSource, hasFreshClock, isOnline, status]);

  const label = displayState === "offline" ? "Offline" : displayState === "syncing" ? "Reconnecting" : "Live";
  const Icon = displayState === "offline" ? WifiOff : Wifi;

  if (compact) {
    return (
      <div className="live-status live-status--compact" aria-label={label}>
        <Icon size={16} aria-hidden="true" />
      </div>
    );
  }

  return (
    <div className="live-status" onBlur={() => setMenuOpen(false)}>
      <button
        type="button"
        className={`live-status__chip live-status__chip--${displayState}`}
        onClick={() => setMenuOpen((prev) => !prev)}
        aria-expanded={menuOpen}
      >
        <span className="live-status__dot" />
        {label}
        <span className="live-status__time">{formatTime(currentTime)}</span>
      </button>
      {menuOpen ? (
        <div className="live-status__menu" role="menu">
          <div className="live-status__meta">Last update: {formatTime(lastUpdated)}</div>
          <div className="live-status__meta">Broker: {brokerState}</div>
          <div className="live-status__meta">Backend: {backendHealth}</div>
          <div className="live-status__meta">Clock source: {clockSource === "server" ? "server" : "local"}</div>
          <div className="live-status__meta">Clock sync: {hasFreshClock ? "healthy" : "refresh pending"}</div>
          <button type="button" onClick={() => refreshData()}>
            <RefreshCw size={14} style={{ marginRight: 6, verticalAlign: "text-bottom" }} />
            Refresh now
          </button>
        </div>
      ) : null}
    </div>
  );
};

export default LiveStatusIndicator;
