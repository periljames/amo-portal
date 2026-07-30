import "./styles/components/clipboard-feedback.css";

type ClipboardFeedbackState = "success" | "error";

type ClipboardGuardWindow = Window & {
  __amoClipboardFeedbackInstalled?: boolean;
  __amoClipboardFeedbackRestore?: () => void;
};

const TOAST_ID = "amo-clipboard-feedback";
const TRIGGER_ATTRIBUTE = "data-copy-feedback";
const triggerTimers = new WeakMap<HTMLElement, number>();
let toastTimer: number | null = null;

function feedbackMessage(state: ClipboardFeedbackState): string {
  return state === "success"
    ? "Content copied successfully"
    : "Copy failed. Please try again.";
}

function feedbackDuration(state: ClipboardFeedbackState): number {
  return state === "success" ? 2400 : 3200;
}

function ensureToast(): HTMLDivElement | null {
  if (typeof document === "undefined" || !document.body) return null;
  const existing = document.getElementById(TOAST_ID);
  if (existing instanceof HTMLDivElement) return existing;

  const toast = document.createElement("div");
  toast.id = TOAST_ID;
  toast.className = "amo-clipboard-feedback";
  toast.setAttribute("role", "status");
  toast.setAttribute("aria-live", "polite");
  toast.setAttribute("aria-atomic", "true");
  toast.hidden = true;

  const icon = document.createElement("span");
  icon.className = "amo-clipboard-feedback__icon";
  icon.setAttribute("aria-hidden", "true");

  const message = document.createElement("span");
  message.className = "amo-clipboard-feedback__message";

  toast.append(icon, message);
  document.body.appendChild(toast);
  return toast;
}

function markTrigger(trigger: HTMLElement | null, state: ClipboardFeedbackState): void {
  if (!trigger) return;
  const previousTimer = triggerTimers.get(trigger);
  if (previousTimer !== undefined) window.clearTimeout(previousTimer);

  trigger.setAttribute(TRIGGER_ATTRIBUTE, state);
  const timer = window.setTimeout(() => {
    if (trigger.getAttribute(TRIGGER_ATTRIBUTE) === state) {
      trigger.removeAttribute(TRIGGER_ATTRIBUTE);
    }
    triggerTimers.delete(trigger);
  }, feedbackDuration(state));
  triggerTimers.set(trigger, timer);
}

function announceFeedback(state: ClipboardFeedbackState): void {
  const toast = ensureToast();
  if (!toast) return;

  if (toastTimer !== null) window.clearTimeout(toastTimer);
  const message = toast.querySelector<HTMLElement>(".amo-clipboard-feedback__message");
  if (message) message.textContent = feedbackMessage(state);

  toast.dataset.state = state;
  toast.hidden = false;
  toast.classList.remove("is-visible");
  // Restart the entrance animation when users copy repeatedly.
  void toast.offsetWidth;
  toast.classList.add("is-visible");

  toastTimer = window.setTimeout(() => {
    toast.classList.remove("is-visible");
    toast.classList.add("is-leaving");
    window.setTimeout(() => {
      toast.hidden = true;
      toast.classList.remove("is-leaving");
      delete toast.dataset.state;
    }, 180);
    toastTimer = null;
  }, feedbackDuration(state));
}

function activeCopyTrigger(): HTMLElement | null {
  const active = document.activeElement;
  if (!(active instanceof HTMLElement)) return null;
  return active.closest<HTMLElement>("button, [role='button'], [data-copy-trigger]") || active;
}

function installClipboardFeedback(): void {
  if (typeof window === "undefined" || typeof navigator === "undefined") return;
  const guardedWindow = window as ClipboardGuardWindow;
  if (guardedWindow.__amoClipboardFeedbackInstalled) return;

  const clipboard = navigator.clipboard;
  const originalWriteText = clipboard?.writeText;
  if (!clipboard || typeof originalWriteText !== "function") return;

  const boundWriteText = originalWriteText.bind(clipboard);
  const wrappedWriteText = async (text: string): Promise<void> => {
    const trigger = activeCopyTrigger();
    try {
      await boundWriteText(text);
      markTrigger(trigger, "success");
      announceFeedback("success");
    } catch (error) {
      markTrigger(trigger, "error");
      announceFeedback("error");
      throw error;
    }
  };

  try {
    Object.defineProperty(clipboard, "writeText", {
      configurable: true,
      writable: true,
      value: wrappedWriteText,
    });
  } catch {
    return;
  }

  guardedWindow.__amoClipboardFeedbackInstalled = true;
  guardedWindow.__amoClipboardFeedbackRestore = () => {
    Object.defineProperty(clipboard, "writeText", {
      configurable: true,
      writable: true,
      value: originalWriteText,
    });
    guardedWindow.__amoClipboardFeedbackInstalled = false;
  };
}

installClipboardFeedback();

if (import.meta.hot) {
  import.meta.hot.dispose(() => {
    (window as ClipboardGuardWindow).__amoClipboardFeedbackRestore?.();
  });
}
