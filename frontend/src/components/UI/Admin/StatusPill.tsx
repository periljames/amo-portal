import React from "react";
import { clsx } from "clsx";

export type StatusTone = "healthy" | "degraded" | "down" | "paused" | "unknown";

export interface StatusPillProps {
  status: StatusTone;
  label?: string;
  className?: string;
}

const StatusPill: React.FC<StatusPillProps> = ({
  status,
  label,
  className,
}) => {
  return (
    <span
      className={clsx("admin-status-pill", `admin-status-pill--${status}`, className)}
    >
      {label ?? status}
    </span>
  );
};

export default StatusPill;
