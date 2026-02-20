import { createContext, useContext } from "react";

import type { ActivityEvent, BackendHealth, RealtimeStatus } from "./RealtimeProvider";
import type { BrokerState } from "../../services/realtime/types";

export type RealtimeContextValue = {
  status: RealtimeStatus;
  brokerState: BrokerState;
  backendHealth: BackendHealth;
  lastGoodServerTime: Date | null;
  lastUpdated: Date | null;
  currentTime: Date;
  activity: ActivityEvent[];
  isStale: boolean;
  staleSeconds: number;
  isOnline: boolean;
  clockSource: "server" | "local";
  refreshData: () => void;
  triggerSync: () => void;
};

export const RealtimeContext = createContext<RealtimeContextValue | null>(null);

export function useRealtime() {
  const ctx = useContext(RealtimeContext);
  if (!ctx) throw new Error("useRealtime must be used within RealtimeProvider");
  return ctx;
}
