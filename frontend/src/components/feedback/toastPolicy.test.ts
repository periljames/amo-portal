import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const provider = readFileSync(
  fileURLToPath(new URL("./ToastProvider.tsx", import.meta.url)),
  "utf8",
);
const policy = readFileSync(
  fileURLToPath(new URL("./toastPolicy.ts", import.meta.url)),
  "utf8",
);
const styles = readFileSync(
  fileURLToPath(new URL("../../styles/components/toast.css", import.meta.url)),
  "utf8",
);
const messaging = readFileSync(
  fileURLToPath(new URL("../messaging/MessagingHub.tsx", import.meta.url)),
  "utf8",
);
const main = readFileSync(
  fileURLToPath(new URL("../../main.tsx", import.meta.url)),
  "utf8",
);
const app = readFileSync(
  fileURLToPath(new URL("../../App.tsx", import.meta.url)),
  "utf8",
);
const auxiliaryBoundary = readFileSync(
  fileURLToPath(new URL("./PortalAuxiliaryBoundary.tsx", import.meta.url)),
  "utf8",
);
const notificationPreferences = readFileSync(
  fileURLToPath(new URL("../../services/notificationPreferences.ts", import.meta.url)),
  "utf8",
);

describe("portal notification policy", () => {
  it("uses one 7-second audible default across feature notifications", () => {
    expect(policy).toContain("TOAST_AUTO_CLOSE_MS = 7_000");
    expect(provider).toContain("duration: TOAST_AUTO_CLOSE_MS");
    expect(provider).toContain("sound: toast.sound ?? true");
    expect(provider).toContain("prepareAudio?.()");
    expect(provider).toContain("import * as notificationPreferences");
    expect(provider).not.toMatch(/import\s*\{[^}]*prepareNotificationAudio/s);
    expect(notificationPreferences).toContain("export function prepareNotificationAudio");
  });

  it("pauses auto-close while a user hovers or interacts", () => {
    expect(provider).toContain("onMouseEnter={pauseTimer}");
    expect(provider).toContain("onMouseLeave={resumeTimer}");
    expect(provider).toContain("onFocus={pauseTimer}");
    expect(styles).toContain(".toast--paused .toast__timer");
    expect(styles).toContain("animation-play-state: paused");
  });

  it("surfaces live inbox notifications through the same global channel", () => {
    expect(messaging).toContain("notificationsInitialized.current = true");
    expect(messaging).toContain("preferences?.sound_enabled !== false");
    expect(messaging).toContain("pushToast({");
    expect(messaging).toContain("Open notifications");
  });

  it("places every root notification consumer under the single toast provider", () => {
    expect(main.match(/<ToastProvider>/g)).toHaveLength(1);
    expect(main).toMatch(/<ToastProvider>[\s\S]*<OfflineSyncIndicator \/>[\s\S]*<\/ToastProvider>/);
    expect(app).not.toContain("<ToastProvider>");
    expect(app).not.toContain("components/feedback/ToastProvider");
  });

  it("isolates auxiliary messaging and sync failures from the main portal", () => {
    expect(main).toMatch(/<PortalAuxiliaryBoundary[\s\S]*<OfflineSyncIndicator \/>[\s\S]*<\/PortalAuxiliaryBoundary>/);
    expect(auxiliaryBoundary).toContain("getDerivedStateFromError");
    expect(auxiliaryBoundary).toContain("return this.state.failed ? null : this.props.children");
  });
});
