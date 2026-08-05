export const PORTAL_ERROR_EVENT = "amo:portal-error";
export const PORTAL_REVEAL_ERROR_TARGET_EVENT = "amo:reveal-error-target";

export type PortalErrorSource = "form" | "upload" | "api" | "runtime" | "unknown";
export type PortalErrorTarget = HTMLElement | string | null;

export type PortalErrorDetail = {
  title: string;
  message: string;
  source: PortalErrorSource;
  code?: string;
  target?: PortalErrorTarget;
  actionLabel?: string;
  action?: () => void | Promise<void>;
  dedupeKey?: string;
  persistent?: boolean;
};

export type PortalErrorOptions = Partial<Omit<PortalErrorDetail, "message" | "source">> & {
  message?: string;
  source?: PortalErrorSource;
  fallbackMessage?: string;
};

type ErrorLike = {
  detail?: unknown;
  message?: unknown;
  error?: unknown;
  status?: unknown;
  code?: unknown;
};

function truncate(value: string, maximum = 700): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  return normalized.length <= maximum ? normalized : `${normalized.slice(0, maximum - 1)}…`;
}

function stringifyDetail(value: unknown): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    return value
      .map((item) => stringifyDetail(item))
      .filter(Boolean)
      .join("; ");
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    const nested = record.msg ?? record.message ?? record.detail ?? record.error;
    if (nested !== undefined) return stringifyDetail(nested);
  }
  return "";
}

export function portalErrorMessage(error: unknown, fallback = "The action could not be completed."): string {
  if (error instanceof Error && error.message.trim()) return truncate(error.message);
  if (typeof error === "string" && error.trim()) return truncate(error);
  if (error && typeof error === "object") {
    const candidate = error as ErrorLike;
    const detail = candidate.detail ?? candidate.message ?? candidate.error;
    const message = stringifyDetail(detail);
    if (message) return truncate(message);
  }
  return fallback;
}

export function portalErrorTitle(source: PortalErrorSource): string {
  if (source === "upload") return "Upload failed";
  if (source === "form") return "Review the highlighted information";
  if (source === "runtime") return "This page encountered a problem";
  return "Action failed";
}

function selectorEscape(value: string): string {
  if (typeof CSS !== "undefined" && typeof CSS.escape === "function") return CSS.escape(value);
  return value.replace(/["\\]/g, "\\$&");
}

export function resolvePortalErrorTarget(target?: PortalErrorTarget): HTMLElement | null {
  if (!target || typeof document === "undefined") return null;
  if (target instanceof HTMLElement) return target;
  const escaped = selectorEscape(target);
  return document.getElementById(target)
    || document.querySelector<HTMLElement>(`[name="${escaped}"]`)
    || document.querySelector<HTMLElement>(`[data-field="${escaped}"]`)
    || document.querySelector<HTMLElement>(`[data-error-anchor="${escaped}"]`);
}

function revealOwningTab(target: HTMLElement): void {
  const hiddenPanel = target.closest<HTMLElement>('[role="tabpanel"][hidden], [role="tabpanel"][aria-hidden="true"]');
  if (!hiddenPanel?.id) return;
  const trigger = document.querySelector<HTMLElement>(`[aria-controls="${selectorEscape(hiddenPanel.id)}"]`);
  trigger?.click();
}

export function revealPortalErrorTarget(target?: PortalErrorTarget): HTMLElement | null {
  const element = resolvePortalErrorTarget(target);
  if (!element) return null;

  element.closest("details")?.setAttribute("open", "");
  revealOwningTab(element);
  element.dispatchEvent(new CustomEvent(PORTAL_REVEAL_ERROR_TARGET_EVENT, {
    bubbles: true,
    detail: { target: element },
  }));
  element.dataset.portalErrorTarget = "true";
  element.setAttribute("aria-invalid", "true");

  const clearMarker = () => {
    delete element.dataset.portalErrorTarget;
    element.removeEventListener("input", clearMarker);
    element.removeEventListener("change", clearMarker);
  };
  element.addEventListener("input", clearMarker, { once: true });
  element.addEventListener("change", clearMarker, { once: true });

  window.requestAnimationFrame(() => {
    element.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
    window.setTimeout(() => element.focus({ preventScroll: true }), 180);
  });
  return element;
}

export function firstInvalidFormControl(form: HTMLFormElement): HTMLElement | null {
  const explicit = form.querySelector<HTMLElement>('[aria-invalid="true"], [data-error="true"], [data-invalid="true"]');
  if (explicit) return explicit;
  try {
    return form.querySelector<HTMLElement>(":invalid");
  } catch {
    return null;
  }
}

export function reportPortalError(error: unknown, options: PortalErrorOptions = {}): PortalErrorDetail {
  const source = options.source ?? "unknown";
  const candidate = error && typeof error === "object" ? error as ErrorLike : null;
  const code = options.code
    ?? (candidate?.code == null ? undefined : String(candidate.code))
    ?? (candidate?.status == null ? undefined : String(candidate.status));
  const detail: PortalErrorDetail = {
    title: options.title || portalErrorTitle(source),
    message: options.message || portalErrorMessage(error, options.fallbackMessage),
    source,
    code,
    target: options.target,
    actionLabel: options.actionLabel,
    action: options.action,
    dedupeKey: options.dedupeKey,
    persistent: options.persistent ?? true,
  };

  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent<PortalErrorDetail>(PORTAL_ERROR_EVENT, { detail }));
  }
  return detail;
}

export function reportUploadError(
  error: unknown,
  options: Omit<PortalErrorOptions, "source"> = {},
): PortalErrorDetail {
  return reportPortalError(error, {
    ...options,
    source: "upload",
    title: options.title || "Upload failed",
    fallbackMessage: options.fallbackMessage || "The file could not be uploaded. Check its format and size, then try again.",
  });
}

export function reportInvalidForm(
  form: HTMLFormElement,
  options: Omit<PortalErrorOptions, "source" | "target"> = {},
): PortalErrorDetail {
  const target = firstInvalidFormControl(form);
  const validationMessage = target instanceof HTMLInputElement
    || target instanceof HTMLSelectElement
    || target instanceof HTMLTextAreaElement
    ? target.validationMessage
    : "";
  const detail = reportPortalError(validationMessage || "Complete the highlighted required fields before continuing.", {
    ...options,
    source: "form",
    target,
    title: options.title || "Review the highlighted information",
    actionLabel: target ? "Show first field" : options.actionLabel,
    action: target ? () => { revealPortalErrorTarget(target); } : options.action,
    dedupeKey: options.dedupeKey || `form:${form.id || form.getAttribute("name") || window.location.pathname}`,
  });
  revealPortalErrorTarget(target);
  return detail;
}
