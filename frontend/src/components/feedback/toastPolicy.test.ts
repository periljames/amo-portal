import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";

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
const offlineIndicator = readFileSync(
  fileURLToPath(new URL("../offline/OfflineSyncIndicator.tsx", import.meta.url)),
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

  it("does not resume Web Audio from asynchronous notification callbacks", () => {
    const cue = notificationPreferences.split("export function playNotificationCue")[1]?.split("export function playNotificationChirp")[0] || "";
    expect(notificationPreferences).toContain("if (!event.isTrusted) return");
    expect(notificationPreferences).toContain("activation && !activation.isActive");
    expect(cue).not.toContain(".resume(");
    expect(cue).toContain('sharedAudioCtx.state !== "running"');
    expect(messaging).toContain("setNotificationPreferences({ audioEnabled: enabled })");
    expect(messaging).toContain("unlockNotificationAudioFromUserGesture(event.nativeEvent)");
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
    expect(main).toMatch(/<ToastProvider>[\s\S]*<MessagingHub \/>[\s\S]*<OfflineSyncIndicator \/>[\s\S]*<\/ToastProvider>/);
    expect(app).not.toContain("<ToastProvider>");
    expect(app).not.toContain("components/feedback/ToastProvider");
  });

  it("mounts router-dependent messaging inside BrowserRouter and keeps offline sync router-agnostic", () => {
    expect(main).toMatch(/<BrowserRouter>[\s\S]*<PortalAuxiliaryBoundary surface="Messaging controls">[\s\S]*<MessagingHub \/>[\s\S]*<\/PortalAuxiliaryBoundary>[\s\S]*<\/BrowserRouter>/);
    expect(main).toMatch(/<PortalAuxiliaryBoundary surface="Connection and sync controls">[\s\S]*<OfflineSyncIndicator \/>[\s\S]*<\/PortalAuxiliaryBoundary>/);
    expect(messaging).toContain("useNavigate()");
    expect(offlineIndicator).not.toContain("MessagingHub");
    expect(offlineIndicator).not.toContain("react-router-dom");
  });

  it("isolates auxiliary messaging and sync failures from the main portal", () => {
    expect(main).toContain('<PortalAuxiliaryBoundary surface="Messaging controls">');
    expect(main).toContain('<PortalAuxiliaryBoundary surface="Connection and sync controls">');
    expect(auxiliaryBoundary).toContain("getDerivedStateFromError");
    expect(auxiliaryBoundary).toContain("return this.state.failed ? null : this.props.children");
  });
});


// Real browser autoplay is controlled by transient activation: a pointerdown
// that occurs while sound is disabled cannot unlock the context; the checked
// change handler must save first and unlock during its own trusted activation.
describe("notification audio activation", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("unlocks after enabling within the same trusted checkbox gesture and plays the first cue", async () => {
    vi.resetModules();
    const storage = new Map<string, string>();
    const events = new Map<string, (event: Event) => void>();
    const start = vi.fn();
    const oscillator = {
      type: "sine", frequency: { setValueAtTime: vi.fn() },
      connect: vi.fn(), start, stop: vi.fn(),
    };
    const gain = {
      gain: { setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() },
      connect: vi.fn(),
    };
    const instances: FakeAudioContext[] = [];
    class FakeAudioContext {
      state = "suspended";
      currentTime = 0;
      destination = {};
      createOscillator = () => oscillator;
      createGain = () => gain;
      resume = vi.fn(async () => { this.state = "running"; });
      constructor() { instances.push(this); }
    }
    vi.stubGlobal("window", {
      localStorage: {
        getItem: (key: string) => storage.get(key) ?? null,
        setItem: (key: string, value: string) => { storage.set(key, value); },
      },
      AudioContext: FakeAudioContext,
      dispatchEvent: vi.fn(),
      addEventListener: (name: string, callback: (event: Event) => void) => { events.set(name, callback); },
    });
    vi.stubGlobal("navigator", { userActivation: { isActive: true } });
    const audio = await import("../../services/notificationPreferences");
    audio.setNotificationPreferences({ audioEnabled: false });
    audio.prepareNotificationAudio();
    const realGesture = { isTrusted: true } as Event;
    events.get("pointerdown")?.(realGesture); // runs before checkbox change
    expect(instances).toHaveLength(0);
    audio.setNotificationPreferences({ audioEnabled: true }); // checkbox change
    await audio.unlockNotificationAudioFromUserGesture(realGesture);
    expect(instances).toHaveLength(1);
    expect(instances[0].resume).toHaveBeenCalledTimes(1);
    expect(instances[0].state).toBe("running");
    audio.playNotificationCue("info");
    expect(start).toHaveBeenCalledTimes(1);
  });

  it("does not resume or create audio for synthetic or inactive gestures", async () => {
    vi.resetModules();
    const storage = new Map<string, string>();
    const AudioCtx = vi.fn();
    const activation = { isActive: false };
    vi.stubGlobal("window", {
      localStorage: {
        getItem: (key: string) => storage.get(key) ?? null,
        setItem: (key: string, value: string) => { storage.set(key, value); },
      },
      AudioContext: AudioCtx,
      dispatchEvent: vi.fn(),
    });
    vi.stubGlobal("navigator", { userActivation: activation });
    const audio = await import("../../services/notificationPreferences");
    audio.setNotificationPreferences({ audioEnabled: true });
    await audio.unlockNotificationAudioFromUserGesture({ isTrusted: false } as Event);
    await audio.unlockNotificationAudioFromUserGesture({ isTrusted: true } as Event);
    expect(AudioCtx).not.toHaveBeenCalled();
  });
});
