import React, { createContext, useCallback, useContext, useMemo, useState } from "react";
import { BellRing, CheckCircle2, CircleAlert, Info, X } from "lucide-react";
import { playNotificationCue } from "../../services/notificationPreferences";

export type ToastVariant = "info" | "success" | "warning" | "error";

export type Toast = {
  id: string;
  title: string;
  message?: string;
  variant?: ToastVariant;
  duration?: number;
  sound?: boolean;
};

type ToastContextValue = {
  pushToast: (toast: Omit<Toast, "id">) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

function randomId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2);
}

function ToastIcon({ variant }: { variant: ToastVariant }) {
  if (variant === "success") return <CheckCircle2 size={19} />;
  if (variant === "warning") return <BellRing size={19} />;
  if (variant === "error") return <CircleAlert size={19} />;
  return <Info size={19} />;
}

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((previous) => previous.filter((toast) => toast.id !== id));
  }, []);

  const pushToast = useCallback((toast: Omit<Toast, "id">) => {
    const id = randomId();
    const variant = toast.variant ?? "info";
    const nextToast: Toast = {
      id,
      duration: variant === "error" ? 8000 : variant === "warning" ? 6500 : 5000,
      sound: variant !== "info",
      ...toast,
      variant,
    };

    setToasts((previous) => [...previous.slice(-4), nextToast]);
    if (nextToast.sound !== false) playNotificationCue(variant);
    if (nextToast.duration && nextToast.duration > 0) {
      window.setTimeout(() => removeToast(id), nextToast.duration);
    }
  }, [removeToast]);

  const value = useMemo(() => ({ pushToast }), [pushToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" aria-label="System notifications">
        {toasts.map((toast) => {
          const variant = toast.variant ?? "info";
          const urgent = variant === "warning" || variant === "error";
          return (
            <article
              key={toast.id}
              className={`toast toast--${variant}`}
              role={urgent ? "alert" : "status"}
              aria-live={urgent ? "assertive" : "polite"}
              aria-atomic="true"
              style={{ "--toast-duration": `${toast.duration || 0}ms` } as React.CSSProperties}
            >
              <div className="toast__icon-wrap" aria-hidden="true"><ToastIcon variant={variant} /></div>
              <div className="toast__content">
                <div className="toast__title">{toast.title}</div>
                {toast.message ? <div className="toast__message">{toast.message}</div> : null}
              </div>
              <button type="button" className="toast__close" aria-label="Dismiss notification" onClick={() => removeToast(toast.id)}><X size={16} /></button>
              {toast.duration ? <span className="toast__timer" aria-hidden="true" /> : null}
            </article>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
};

export const useToast = (): ToastContextValue => {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used within a ToastProvider");
  return context;
};
