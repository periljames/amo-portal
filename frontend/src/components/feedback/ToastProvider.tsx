import React, { createContext, useCallback, useContext, useMemo, useState } from "react";
import { BellRing, CheckCircle2, CircleAlert, Info, X } from "lucide-react";
import { playNotificationChirp } from "../../services/notificationPreferences";

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
  return Math.random().toString(36).slice(2);
}

function ToastIcon({ variant }: { variant: ToastVariant }) {
  if (variant === "success") return <CheckCircle2 size={18} />;
  if (variant === "warning") return <BellRing size={18} />;
  if (variant === "error") return <CircleAlert size={18} />;
  return <Info size={18} />;
}

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const pushToast = useCallback((toast: Omit<Toast, "id">) => {
    const id = randomId();
    const nextToast: Toast = {
      id,
      duration: 5000,
      variant: "info",
      sound: toast.variant === "error" || toast.variant === "warning",
      ...toast,
    };

    setToasts((prev) => [...prev, nextToast]);

    if (nextToast.sound !== false) {
      playNotificationChirp();
    }

    if (nextToast.duration && nextToast.duration > 0) {
      window.setTimeout(() => removeToast(id), nextToast.duration);
    }
  }, [removeToast]);

  const value = useMemo(() => ({ pushToast }), [pushToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" role="status" aria-live="polite">
        {toasts.map((toast) => {
          const variant = toast.variant ?? "info";
          return (
            <article key={toast.id} className={`toast toast--${variant}`}>
              <div className="toast__icon-wrap" aria-hidden="true">
                <ToastIcon variant={variant} />
              </div>
              <div className="toast__content">
                <div className="toast__title">{toast.title}</div>
                {toast.message ? <div className="toast__message">{toast.message}</div> : null}
              </div>
              <button
                type="button"
                className="toast__close"
                aria-label="Dismiss notification"
                onClick={() => removeToast(toast.id)}
              >
                <X size={16} />
              </button>
            </article>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
};

export const useToast = (): ToastContextValue => {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return ctx;
};
