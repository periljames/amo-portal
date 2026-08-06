import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { BellRing, CheckCircle2, CircleAlert, Info, X } from "lucide-react";
import { playNotificationCue } from "../../services/notificationPreferences";
import {
  PORTAL_ERROR_EVENT,
  portalErrorMessage,
  revealPortalErrorTarget,
  type PortalErrorDetail,
  type PortalErrorSource,
  type PortalErrorTarget,
} from "../../services/portalError";

export type ToastVariant = "info" | "success" | "warning" | "error";

export type Toast = {
  id: string;
  title: string;
  message?: string;
  variant?: ToastVariant;
  duration?: number;
  sound?: boolean;
  persistent?: boolean;
  source?: PortalErrorSource;
  code?: string;
  target?: PortalErrorTarget;
  actionLabel?: string;
  action?: () => void | Promise<void>;
  dedupeKey?: string;
};

type ToastContextValue = {
  pushToast: (toast: Omit<Toast, "id">) => string;
  showError: (toast: Omit<Toast, "id" | "variant" | "persistent">) => string;
  dismissToast: (id: string) => void;
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

function defaultDuration(variant: ToastVariant): number {
  if (variant === "error") return 0;
  if (variant === "warning") return 9000;
  return 5000;
}

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const errorRefs = useRef(new Map<string, HTMLElement>());
  const invalidGuard = useRef<{ form: HTMLFormElement | null; at: number }>({ form: null, at: 0 });

  const removeToast = useCallback((id: string) => {
    errorRefs.current.delete(id);
    setToasts((previous) => previous.filter((toast) => toast.id !== id));
  }, []);

  const pushToast = useCallback((toast: Omit<Toast, "id">): string => {
    const id = randomId();
    const variant = toast.variant ?? "info";
    const persistent = toast.persistent ?? variant === "error";
    const nextToast: Toast = {
      id,
      duration: persistent ? 0 : defaultDuration(variant),
      sound: variant !== "info",
      ...toast,
      variant,
      persistent,
    };

    setToasts((previous) => {
      const deduplicated = nextToast.dedupeKey
        ? previous.filter((item) => item.dedupeKey !== nextToast.dedupeKey)
        : previous;
      const ordered = variant === "error"
        ? [nextToast, ...deduplicated]
        : [...deduplicated, nextToast];
      return ordered.slice(0, 5);
    });
    if (nextToast.sound !== false) playNotificationCue(variant);
    if (nextToast.duration && nextToast.duration > 0) {
      window.setTimeout(() => removeToast(id), nextToast.duration);
    }
    return id;
  }, [removeToast]);

  const showError = useCallback((toast: Omit<Toast, "id" | "variant" | "persistent">): string => (
    pushToast({ ...toast, variant: "error", persistent: true })
  ), [pushToast]);

  useEffect(() => {
    const firstError = toasts.find((toast) => toast.variant === "error");
    if (!firstError) return;
    const element = errorRefs.current.get(firstError.id);
    window.requestAnimationFrame(() => element?.focus({ preventScroll: true }));
  }, [toasts]);

  useEffect(() => {
    const onPortalError = (event: Event) => {
      const detail = (event as CustomEvent<PortalErrorDetail>).detail;
      if (!detail?.message) return;
      showError({
        title: detail.title,
        message: detail.message,
        source: detail.source,
        code: detail.code,
        target: detail.target,
        actionLabel: detail.actionLabel || (detail.target ? "Show affected field" : undefined),
        action: detail.action || (detail.target ? () => { revealPortalErrorTarget(detail.target); } : undefined),
        dedupeKey: detail.dedupeKey || `${detail.source}:${detail.title}:${detail.message}`,
        sound: true,
      });
      if (detail.target) revealPortalErrorTarget(detail.target);
    };

    const onInvalid = (event: Event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement)
        && !(target instanceof HTMLSelectElement)
        && !(target instanceof HTMLTextAreaElement)) return;
      const now = Date.now();
      const form = target.form;
      if (invalidGuard.current.form === form && now - invalidGuard.current.at < 500) return;
      invalidGuard.current = { form, at: now };
      showError({
        title: "Review the highlighted information",
        message: target.validationMessage || "Complete the required field before continuing.",
        source: "form",
        target,
        actionLabel: "Show first field",
        action: () => { revealPortalErrorTarget(target); },
        dedupeKey: `native-form:${form?.id || form?.getAttribute("name") || window.location.pathname}`,
      });
      revealPortalErrorTarget(target);
    };

    const onUnhandledRejection = (event: PromiseRejectionEvent) => {
      const reason = event.reason;
      if (!(reason instanceof Error)) return;
      showError({
        title: "This action did not finish",
        message: portalErrorMessage(reason),
        source: "runtime",
        dedupeKey: `unhandled:${reason.name}:${reason.message}`,
      });
    };

    const onWindowError = (event: ErrorEvent) => {
      if (!(event.error instanceof Error)) return;
      showError({
        title: "This page encountered a problem",
        message: portalErrorMessage(event.error, "Reload the page and try the action again."),
        source: "runtime",
        actionLabel: "Reload page",
        action: () => window.location.reload(),
        dedupeKey: `runtime:${event.error.name}:${event.error.message}`,
      });
    };

    window.addEventListener(PORTAL_ERROR_EVENT, onPortalError);
    window.addEventListener("unhandledrejection", onUnhandledRejection);
    window.addEventListener("error", onWindowError);
    document.addEventListener("invalid", onInvalid, true);
    return () => {
      window.removeEventListener(PORTAL_ERROR_EVENT, onPortalError);
      window.removeEventListener("unhandledrejection", onUnhandledRejection);
      window.removeEventListener("error", onWindowError);
      document.removeEventListener("invalid", onInvalid, true);
    };
  }, [showError]);

  const value = useMemo(() => ({ pushToast, showError, dismissToast: removeToast }), [pushToast, removeToast, showError]);

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
              ref={(element) => {
                if (element && variant === "error") errorRefs.current.set(toast.id, element);
                else errorRefs.current.delete(toast.id);
              }}
              className={`toast toast--${variant} ${toast.persistent ? "toast--persistent" : ""}`}
              role={urgent ? "alert" : "status"}
              aria-live={urgent ? "assertive" : "polite"}
              aria-atomic="true"
              tabIndex={variant === "error" ? -1 : undefined}
              data-error-source={toast.source}
              style={{ "--toast-duration": `${toast.duration || 0}ms` } as React.CSSProperties}
            >
              <div className="toast__icon-wrap" aria-hidden="true"><ToastIcon variant={variant} /></div>
              <div className="toast__content">
                <div className="toast__title">{toast.title}</div>
                {toast.message ? <div className="toast__message">{toast.message}</div> : null}
                {toast.code ? <div className="toast__code">Reference: {toast.code}</div> : null}
                {toast.actionLabel && toast.action ? (
                  <button
                    type="button"
                    className="toast__action"
                    onClick={() => void Promise.resolve(toast.action?.()).catch(() => undefined)}
                  >
                    {toast.actionLabel}
                  </button>
                ) : null}
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
