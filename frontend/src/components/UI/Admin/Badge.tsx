import React from "react";
import { clsx } from "clsx";

export type BadgeTone = "neutral" | "info" | "warning" | "danger" | "success";
export type BadgeSize = "sm" | "md";

export interface BadgeProps {
  children: React.ReactNode;
  tone?: BadgeTone;
  size?: BadgeSize;
  className?: string;
}

const Badge: React.FC<BadgeProps> = ({
  children,
  tone = "neutral",
  size = "md",
  className,
}) => {
  return (
    <span
      className={clsx("admin-badge", `admin-badge--${tone}`, `admin-badge--${size}`, className)}
    >
      {children}
    </span>
  );
};

export default Badge;
