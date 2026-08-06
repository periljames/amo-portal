import { reportPortalError, type PortalErrorTarget } from "./portalError";

const ERROR_SELECTOR = '[role="alert"], .inline-error, [data-portal-inline-error], [data-error-message]';
const MIRROR_EXCLUSIONS = ".toast-stack, .portal-fatal-error, [data-portal-error-feedback]";
const MAX_MESSAGE_LENGTH = 700;

const mirroredText = new WeakMap<Element, string>();

function normalizedText(element: Element): string {
  const text = (element.getAttribute("data-error-message") || element.textContent || "")
    .replace(/\s+/g, " ")
    .trim();
  if (!text) return "";
  return text.length <= MAX_MESSAGE_LENGTH ? text : `${text.slice(0, MAX_MESSAGE_LENGTH - 1)}…`;
}

function isInsideViewport(element: HTMLElement): boolean {
  if (element.hidden || element.getAttribute("aria-hidden") === "true") return false;
  const style = window.getComputedStyle(element);
  if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) return false;
  const rect = element.getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0) return false;
  return rect.top >= 0
    && rect.left >= 0
    && rect.bottom <= window.innerHeight
    && rect.right <= window.innerWidth;
}

function describedError(target: HTMLElement): HTMLElement | null {
  const ids = (target.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean);
  for (const id of ids) {
    const description = document.getElementById(id);
    if (description && normalizedText(description)) return description;
  }
  return null;
}

function targetForError(errorElement: HTMLElement): PortalErrorTarget {
  const explicit = errorElement.getAttribute("data-error-for");
  if (explicit) return explicit;
  if (errorElement.id) {
    const describedControl = document.querySelector<HTMLElement>(`[aria-describedby~="${CSS.escape(errorElement.id)}"]`);
    if (describedControl) return describedControl;
  }
  const form = errorElement.closest("form");
  return form?.querySelector<HTMLElement>('[aria-invalid="true"], [data-error="true"], [data-invalid="true"]')
    || form?.querySelector<HTMLElement>('input[type="file"]')
    || null;
}

function mirrorError(element: HTMLElement, forcedTarget?: HTMLElement): void {
  if (element.closest(MIRROR_EXCLUSIONS)) return;
  const message = normalizedText(element);
  if (!message || mirroredText.get(element) === message) return;
  if (isInsideViewport(element)) return;

  mirroredText.set(element, message);
  const form = element.closest("form");
  const target = forcedTarget || targetForError(element);
  reportPortalError(message, {
    source: form ? "form" : "unknown",
    title: form ? "Review the highlighted information" : "Action failed",
    target,
    actionLabel: target ? "Show affected field" : undefined,
    dedupeKey: `mirrored-inline:${window.location.pathname}:${message}`,
  });
}

function inspectElement(element: Element): void {
  if (!(element instanceof HTMLElement)) return;
  if (element.matches(ERROR_SELECTOR)) mirrorError(element);
  element.querySelectorAll<HTMLElement>(ERROR_SELECTOR).forEach((candidate) => mirrorError(candidate));

  if (element.getAttribute("aria-invalid") === "true") {
    const description = describedError(element);
    if (description) mirrorError(description, element);
  }
  element.querySelectorAll<HTMLElement>('[aria-invalid="true"]').forEach((target) => {
    const description = describedError(target);
    if (description) mirrorError(description, target);
  });
}

export function installPortalInlineErrorMirror(): () => void {
  if (typeof document === "undefined" || typeof MutationObserver === "undefined") return () => undefined;

  const inspectMutation = (mutation: MutationRecord) => {
    if (mutation.type === "attributes" && mutation.target instanceof Element) {
      inspectElement(mutation.target);
      return;
    }
    if (mutation.type === "characterData") {
      const parent = mutation.target.parentElement;
      if (parent) inspectElement(parent);
      return;
    }
    mutation.addedNodes.forEach((node) => {
      if (node instanceof Element) inspectElement(node);
      else if (node.parentElement) inspectElement(node.parentElement);
    });
  };

  const observer = new MutationObserver((mutations) => {
    window.requestAnimationFrame(() => mutations.forEach(inspectMutation));
  });
  observer.observe(document.body, {
    subtree: true,
    childList: true,
    characterData: true,
    attributes: true,
    attributeFilter: ["aria-invalid", "aria-hidden"],
  });
  window.requestAnimationFrame(() => inspectElement(document.body));
  return () => observer.disconnect();
}
