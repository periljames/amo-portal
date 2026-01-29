import React from "react";
import { clsx } from "clsx";

export type InlineAlertTone = "info" | "warning" | "danger" | "success";

export interface InlineAlertProps {
  tone?: InlineAlertTone;
  title?: string;
  children?: React.ReactNode;
  className?: string;
  actions?: React.ReactNode;
}

const InlineAlert: React.FC<InlineAlertProps> = ({
  tone = "info",
  title,
  children,
  className,
  actions,
}) => {
  return (
    <div className={clsx("admin-inline-alert", `admin-inline-alert--${tone}`, className)}>
      <div className="admin-inline-alert__content">
        {title ? <strong>{title}</strong> : null}
        {children ? <div className="admin-inline-alert__body">{children}</div> : null}
      </div>
      {actions ? <div className="admin-inline-alert__actions">{actions}</div> : null}
    </div>
  );
};

export default InlineAlert;
