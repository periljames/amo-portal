import "../../../styles/platform-graph-focus.css";

const GRAPH_SELECTOR = [
  ".platform-trend-card",
  "[data-platform-graph]",
  ".echarts-for-react",
  ".recharts-responsive-container",
].join(",");

declare global {
  interface Window {
    __amoPlatformSafeGraphFocusInstalled?: boolean;
  }
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
  const value = surface.dataset.graphTitle
    || surface.getAttribute("aria-label")
    || surface.querySelector("h2, h3, header span, .label")?.textContent
    || "Expanded graph";
  return value.replace(/\s+/g, " ").trim();
}

function installPlatformGraphFocus(): void {
  if (typeof window === "undefined" || typeof document === "undefined") return;
  if (window.__amoPlatformSafeGraphFocusInstalled) return;
  window.__amoPlatformSafeGraphFocusInstalled = true;

  const start = () => {
    const backdrop = document.createElement("div");
    backdrop.className = "platform-graph-safe-backdrop";
    backdrop.setAttribute("aria-hidden", "true");
    backdrop.innerHTML = `
      <div class="platform-graph-safe-toolbar" role="dialog" aria-modal="true" aria-labelledby="platform-safe-graph-title">
        <strong id="platform-safe-graph-title">Expanded graph</strong>
        <button type="button" class="platform-graph-safe-close" aria-label="Close expanded graph">×</button>
      </div>`;
    document.body.appendChild(backdrop);

    const title = backdrop.querySelector("#platform-safe-graph-title") as HTMLElement;
    const closeButton = backdrop.querySelector(".platform-graph-safe-close") as HTMLButtonElement;
    let active: HTMLElement | null = null;

    const dispatchResize = () => window.dispatchEvent(new Event("resize"));

    const close = () => {
      if (!active) return;
      const previous = active;
      previous.classList.remove("platform-graph-expanded");
      active = null;
      backdrop.classList.remove("is-open");
      backdrop.setAttribute("aria-hidden", "true");
      document.body.classList.remove("platform-graph-safe-open");
      window.setTimeout(() => {
        dispatchResize();
        previous.focus({ preventScroll: true });
      }, 0);
    };

    const open = (surface: HTMLElement) => {
      if (active === surface) return;
      if (active) active.classList.remove("platform-graph-expanded");
      active = surface;
      title.textContent = graphTitle(surface);
      surface.classList.add("platform-graph-expanded");
      backdrop.classList.add("is-open");
      backdrop.setAttribute("aria-hidden", "false");
      document.body.classList.add("platform-graph-safe-open");
      window.setTimeout(() => {
        dispatchResize();
        closeButton.focus();
      }, 0);
    };

    const prepare = (root: ParentNode = document) => {
      const candidates: HTMLElement[] = [];
      if (root instanceof Element && root.matches(GRAPH_SELECTOR)) candidates.push(root as HTMLElement);
      root.querySelectorAll<HTMLElement>(GRAPH_SELECTOR).forEach((item) => candidates.push(item));
      candidates.forEach((candidate) => {
        const surface = graphSurface(candidate) || candidate;
        if (!surface.hasAttribute("tabindex")) surface.tabIndex = 0;
        if (!surface.hasAttribute("role")) surface.setAttribute("role", "button");
        if (!surface.hasAttribute("aria-label")) surface.setAttribute("aria-label", `${graphTitle(surface)}. Activate to expand.`);
      });
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
      if (!surface || surface.classList.contains("platform-graph-expanded")) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      open(surface);
    }, true);

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && active) {
        event.preventDefault();
        event.stopImmediatePropagation();
        close();
        return;
      }
      if (event.key !== "Enter" && event.key !== " ") return;
      if (!(event.target instanceof Element)) return;
      const surface = graphSurface(event.target);
      if (!surface || surface.classList.contains("platform-graph-expanded")) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      open(surface);
    }, true);

    closeButton.addEventListener("click", (event) => {
      event.stopImmediatePropagation();
      close();
    });
    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop) close();
    });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
}

installPlatformGraphFocus();

export {};
