import "../../../styles/platform-ux-hardening.css";

type ToastTone = "success" | "error" | "warning" | "info";

declare global {
  interface Window {
    __amoPlatformUxInstalled?: boolean;
    __amoPlatformOriginalFetch?: typeof fetch;
  }
}

const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const GRAPH_SELECTOR = [
  ".platform-trend-card",
  "[data-platform-graph]",
  ".echarts-for-react",
  ".recharts-responsive-container",
].join(",");

let toastCounter = 0;
const recentNotices = new Map<string, number>();

function safeText(value: string | null | undefined, fallback: string): string {
  const clean = String(value || "").replace(/\s+/g, " ").trim();
  return clean || fallback;
}

function ensureToastViewport(): HTMLDivElement {
  let root = document.querySelector<HTMLDivElement>(".platform-toast-viewport");
  if (root) return root;
  root = document.createElement("div");
  root.className = "platform-toast-viewport";
  root.setAttribute("aria-live", "polite");
  root.setAttribute("aria-atomic", "false");
  document.body.appendChild(root);
  return root;
}

function dismissToast(toast: HTMLElement): void {
  if (toast.classList.contains("is-leaving")) return;
  toast.classList.add("is-leaving");
  window.setTimeout(() => toast.remove(), 210);
}

function showToast(
  tone: ToastTone,
  title: string,
  detail?: string,
  options: { durationMs?: number; dedupeKey?: string } = {},
): void {
  if (typeof document === "undefined") return;
  const now = Date.now();
  const dedupeKey = options.dedupeKey || `${tone}:${title}:${detail || ""}`;
  const previous = recentNotices.get(dedupeKey) || 0;
  if (now - previous < 900) return;
  recentNotices.set(dedupeKey, now);

  const toast = document.createElement("article");
  toast.className = "platform-toast";
  toast.dataset.tone = tone;
  toast.dataset.toastId = String(++toastCounter);
  toast.setAttribute("role", tone === "error" ? "alert" : "status");

  const icon = document.createElement("span");
  icon.className = "platform-toast__icon";
  icon.textContent = tone === "success" ? "✓" : tone === "error" ? "!" : tone === "warning" ? "△" : "i";

  const copy = document.createElement("div");
  copy.className = "platform-toast__copy";
  const heading = document.createElement("strong");
  heading.textContent = title;
  copy.appendChild(heading);
  if (detail) {
    const description = document.createElement("small");
    description.textContent = detail;
    copy.appendChild(description);
  }

  const close = document.createElement("button");
  close.type = "button";
  close.className = "platform-toast__close";
  close.setAttribute("aria-label", "Dismiss notification");
  close.textContent = "×";
  close.addEventListener("click", () => dismissToast(toast));

  toast.append(icon, copy, close);
  ensureToastViewport().appendChild(toast);
  window.setTimeout(() => dismissToast(toast), options.durationMs ?? (tone === "error" ? 7200 : 4300));
}

function endpointLabel(pathname: string): string {
  const path = pathname.toLowerCase();
  if (path.includes("support-session")) return "Support session";
  if (path.includes("support") && path.includes("ticket")) return "Support ticket";
  if (path.includes("security/alerts")) return "Security alert";
  if (path.includes("api-keys")) return "API key";
  if (path.includes("webhooks")) return "Webhook";
  if (path.includes("providers")) return "Provider configuration";
  if (path.includes("subscriptions")) return "Subscription";
  if (path.includes("price-book") || path.includes("prices")) return "Pricing record";
  if (path.includes("invoices")) return "Invoice";
  if (path.includes("payments")) return "Payment";
  if (path.includes("tenants")) return "Tenant";
  if (path.includes("users")) return "User";
  if (path.includes("feature-flags")) return "Feature flag";
  if (path.includes("maintenance")) return "Maintenance window";
  if (path.includes("jobs") || path.includes("commands") || path.includes("diagnostics")) return "Platform job";
  if (path.includes("email")) return "Email delivery setting";
  return "Platform operation";
}

function successVerb(method: string): string {
  if (method === "DELETE") return "removed";
  if (method === "PATCH" || method === "PUT") return "updated";
  return "completed";
}

function installFetchFeedback(): void {
  if (window.__amoPlatformOriginalFetch) return;
  const original = window.fetch.bind(window);
  window.__amoPlatformOriginalFetch = original;

  window.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : null;
    const method = String(init?.method || request?.method || "GET").toUpperCase();
    const urlText = request?.url || String(input);
    let url: URL | null = null;
    try {
      url = new URL(urlText, window.location.origin);
    } catch {
      url = null;
    }
    const isPlatformRequest = Boolean(url?.pathname.includes("/platform/"));
    const started = performance.now();

    try {
      const response = await original(input, init);
      const elapsed = Math.max(0, Math.round(performance.now() - started));
      if (isPlatformRequest && MUTATING_METHODS.has(method)) {
        const label = endpointLabel(url?.pathname || "");
        if (response.ok) {
          showToast(
            "success",
            `${label} ${successVerb(method)} successfully`,
            elapsed >= 1800 ? `Completed in ${(elapsed / 1000).toFixed(1)} seconds.` : `Completed in ${elapsed} ms.`,
            { dedupeKey: `${method}:${url?.pathname}:success` },
          );
        } else if (response.status !== 401) {
          showToast(
            "error",
            `${label} was not completed`,
            `The endpoint returned HTTP ${response.status}.`,
            { dedupeKey: `${method}:${url?.pathname}:${response.status}` },
          );
        }
      } else if (isPlatformRequest && !response.ok && response.status >= 500) {
        showToast(
          "error",
          "Platform section failed to load",
          `${endpointLabel(url?.pathname || "")} returned HTTP ${response.status}.`,
          { dedupeKey: `GET:${url?.pathname}:${response.status}` },
        );
      } else if (isPlatformRequest && method === "GET" && response.ok && elapsed >= 3500) {
        showToast(
          "warning",
          "Slow platform response detected",
          `${endpointLabel(url?.pathname || "")} took ${(elapsed / 1000).toFixed(1)} seconds.`,
          { durationMs: 5200, dedupeKey: `slow:${url?.pathname}` },
        );
      }
      return response;
    } catch (error) {
      if (isPlatformRequest) {
        showToast(
          "error",
          "Platform request failed",
          error instanceof Error ? error.message : "The endpoint could not be reached.",
          { dedupeKey: `network:${method}:${url?.pathname || urlText}` },
        );
      }
      throw error;
    }
  }) as typeof fetch;
}

function ensureConfirmDialog(): {
  root: HTMLDivElement;
  title: HTMLHeadingElement;
  message: HTMLParagraphElement;
  cancel: HTMLButtonElement;
  confirm: HTMLButtonElement;
} {
  const existing = document.querySelector<HTMLDivElement>(".platform-dialog-backdrop");
  if (existing) {
    return {
      root: existing,
      title: existing.querySelector("h2") as HTMLHeadingElement,
      message: existing.querySelector("p") as HTMLParagraphElement,
      cancel: existing.querySelector("[data-dialog-cancel]") as HTMLButtonElement,
      confirm: existing.querySelector("[data-dialog-confirm]") as HTMLButtonElement,
    };
  }

  const root = document.createElement("div");
  root.className = "platform-dialog-backdrop";
  root.setAttribute("aria-hidden", "true");
  root.innerHTML = `
    <section class="platform-dialog" role="dialog" aria-modal="true" aria-labelledby="platform-confirm-title" aria-describedby="platform-confirm-message">
      <div class="platform-dialog__head">
        <span class="platform-dialog__mark" aria-hidden="true">!</span>
        <div>
          <h2 id="platform-confirm-title">Confirm operation</h2>
          <p id="platform-confirm-message">This change affects live platform data.</p>
        </div>
      </div>
      <div class="platform-dialog__actions">
        <button type="button" class="platform-btn" data-dialog-cancel>Cancel</button>
        <button type="button" class="platform-btn danger" data-dialog-confirm>Confirm</button>
      </div>
    </section>`;
  document.body.appendChild(root);
  return {
    root,
    title: root.querySelector("h2") as HTMLHeadingElement,
    message: root.querySelector("p") as HTMLParagraphElement,
    cancel: root.querySelector("[data-dialog-cancel]") as HTMLButtonElement,
    confirm: root.querySelector("[data-dialog-confirm]") as HTMLButtonElement,
  };
}

function installDangerConfirmations(): void {
  let pendingButton: HTMLElement | null = null;
  const dialog = ensureConfirmDialog();

  const close = () => {
    dialog.root.classList.remove("is-open");
    dialog.root.setAttribute("aria-hidden", "true");
    pendingButton = null;
  };

  dialog.cancel.addEventListener("click", close);
  dialog.root.addEventListener("click", (event) => {
    if (event.target === dialog.root) close();
  });
  dialog.confirm.addEventListener("click", () => {
    const target = pendingButton;
    close();
    if (!target) return;
    target.dataset.platformConfirmBypass = "true";
    target.click();
  });

  document.addEventListener("click", (event) => {
    const target = event.target instanceof Element
      ? event.target.closest<HTMLElement>(".platform-btn.danger, [data-platform-confirm]")
      : null;
    if (!target || target.closest(".platform-dialog")) return;
    if (target.dataset.platformConfirmBypass === "true") {
      delete target.dataset.platformConfirmBypass;
      return;
    }
    if ((target as HTMLButtonElement).disabled) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    pendingButton = target;
    const action = safeText(target.textContent, "this operation");
    dialog.title.textContent = safeText(target.dataset.confirmTitle, `Confirm ${action}`);
    dialog.message.textContent = safeText(
      target.dataset.confirmMessage,
      "Review the selected record and scope before continuing. This operation is audited.",
    );
    dialog.confirm.textContent = safeText(target.dataset.confirmLabel, action);
    dialog.root.classList.add("is-open");
    dialog.root.setAttribute("aria-hidden", "false");
    window.setTimeout(() => dialog.cancel.focus(), 0);
  }, true);

  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && dialog.root.classList.contains("is-open")) close();
  });
}

function graphSurface(target: Element): HTMLElement | null {
  const matched = target.closest<HTMLElement>(GRAPH_SELECTOR);
  if (!matched) return null;
  if (matched.matches(".echarts-for-react, .recharts-responsive-container")) {
    return matched.closest<HTMLElement>(".platform-card, .platform-dashboard-panel, [data-platform-graph]") || matched;
  }
  return matched;
}

function graphTitle(surface: HTMLElement): string {
  return safeText(
    surface.dataset.graphTitle
      || surface.getAttribute("aria-label")
      || surface.querySelector("h2, h3, header span, .label")?.textContent,
    "Expanded graph",
  );
}

function ensureGraphFocus(): {
  root: HTMLDivElement;
  content: HTMLDivElement;
  heading: HTMLElement;
  close: HTMLButtonElement;
} {
  const root = document.createElement("div");
  root.className = "platform-graph-focus";
  root.setAttribute("aria-hidden", "true");
  root.innerHTML = `
    <section class="platform-graph-focus__frame" role="dialog" aria-modal="true" aria-labelledby="platform-graph-focus-title">
      <header class="platform-graph-focus__bar">
        <strong id="platform-graph-focus-title">Expanded graph</strong>
        <button type="button" class="platform-graph-focus__close" aria-label="Close expanded graph">×</button>
      </header>
      <div class="platform-graph-focus__content"></div>
    </section>`;
  document.body.appendChild(root);
  return {
    root,
    content: root.querySelector(".platform-graph-focus__content") as HTMLDivElement,
    heading: root.querySelector("#platform-graph-focus-title") as HTMLElement,
    close: root.querySelector(".platform-graph-focus__close") as HTMLButtonElement,
  };
}

function installGraphFocus(): void {
  const focus = ensureGraphFocus();
  let source: HTMLElement | null = null;
  let placeholder: Comment | null = null;

  const dispatchResize = () => window.dispatchEvent(new Event("resize"));

  const close = () => {
    focus.root.classList.remove("is-open");
    focus.root.setAttribute("aria-hidden", "true");
    document.body.classList.remove("platform-graph-focus-open");
    const returning = source;
    if (returning && placeholder?.parentNode) placeholder.replaceWith(returning);
    focus.content.replaceChildren();
    source = null;
    placeholder = null;
    window.setTimeout(() => {
      dispatchResize();
      returning?.focus({ preventScroll: true });
    }, 0);
  };

  const open = (surface: HTMLElement) => {
    if (source || focus.root.contains(surface)) return;
    source = surface;
    placeholder = document.createComment("platform-graph-focus-placeholder");
    surface.replaceWith(placeholder);
    surface.style.cursor = "default";
    focus.heading.textContent = graphTitle(surface);
    focus.content.replaceChildren(surface);
    focus.root.classList.add("is-open");
    focus.root.setAttribute("aria-hidden", "false");
    document.body.classList.add("platform-graph-focus-open");
    window.setTimeout(() => {
      dispatchResize();
      focus.close.focus();
    }, 0);
  };

  const prepareElement = (candidate: Element) => {
    const surface = graphSurface(candidate) || (candidate.matches(GRAPH_SELECTOR) ? candidate as HTMLElement : null);
    if (!surface || focus.root.contains(surface)) return;
    if (!surface.hasAttribute("tabindex")) surface.tabIndex = 0;
    if (!surface.hasAttribute("role")) surface.setAttribute("role", "button");
    if (!surface.hasAttribute("aria-label")) surface.setAttribute("aria-label", `${graphTitle(surface)}. Activate to expand.`);
  };

  const prepare = (root: ParentNode = document) => {
    if (root instanceof Element) prepareElement(root);
    root.querySelectorAll<HTMLElement>(GRAPH_SELECTOR).forEach(prepareElement);
  };

  prepare();
  const observer = new MutationObserver((records) => {
    records.forEach((record) => record.addedNodes.forEach((node) => {
      if (node instanceof Element) prepare(node);
    }));
  });
  observer.observe(document.body, { childList: true, subtree: true });

  document.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) return;
    if (event.target.closest("button, a, input, select, textarea, [role='menuitem']")) return;
    const surface = graphSurface(event.target);
    if (surface && !focus.root.contains(surface)) open(surface);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && focus.root.classList.contains("is-open")) {
      close();
      return;
    }
    if (event.key !== "Enter" && event.key !== " ") return;
    if (!(event.target instanceof Element)) return;
    const surface = graphSurface(event.target);
    if (!surface || focus.root.contains(surface)) return;
    event.preventDefault();
    open(surface);
  });

  focus.close.addEventListener("click", close);
  focus.root.addEventListener("click", (event) => {
    if (event.target === focus.root) close();
  });
}

function installPlatformUxRuntime(): void {
  if (typeof window === "undefined" || typeof document === "undefined") return;
  if (window.__amoPlatformUxInstalled) return;
  window.__amoPlatformUxInstalled = true;
  const start = () => {
    installFetchFeedback();
    installDangerConfirmations();
    installGraphFocus();
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
}

installPlatformUxRuntime();

export { showToast };
