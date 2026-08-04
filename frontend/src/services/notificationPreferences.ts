export const NOTIFICATION_PREFS_EVENT = "amodb:notification-prefs";
const PREFS_STORAGE_KEY = "amodb_notification_preferences";
let sharedAudioCtx: AudioContext | null = null;
let unlockBound = false;

export type NotificationCue = "info" | "success" | "warning" | "error";

export type NotificationPreferences = {
  audioEnabled: boolean;
  desktopEnabled: boolean;
  pollIntervalSeconds: number;
  enablePhotoUploads: boolean;
  enableVideoUploads: boolean;
};

const DEFAULT_PREFS: NotificationPreferences = {
  audioEnabled: true,
  desktopEnabled: false,
  pollIntervalSeconds: 60,
  enablePhotoUploads: true,
  enableVideoUploads: true,
};

export function getNotificationPreferences(): NotificationPreferences {
  if (typeof window === "undefined") return DEFAULT_PREFS;
  try {
    const raw = window.localStorage.getItem(PREFS_STORAGE_KEY);
    if (!raw) return DEFAULT_PREFS;
    const parsed = JSON.parse(raw) as Partial<NotificationPreferences>;
    return {
      ...DEFAULT_PREFS,
      ...parsed,
      pollIntervalSeconds: Math.max(15, Math.min(600, Number(parsed.pollIntervalSeconds ?? DEFAULT_PREFS.pollIntervalSeconds))),
    };
  } catch {
    return DEFAULT_PREFS;
  }
}

export function setNotificationPreferences(next: Partial<NotificationPreferences>): NotificationPreferences {
  if (typeof window === "undefined") return DEFAULT_PREFS;
  const merged = {
    ...getNotificationPreferences(),
    ...next,
  };
  merged.pollIntervalSeconds = Math.max(15, Math.min(600, Number(merged.pollIntervalSeconds)));
  window.localStorage.setItem(PREFS_STORAGE_KEY, JSON.stringify(merged));
  window.dispatchEvent(new Event(NOTIFICATION_PREFS_EVENT));
  return merged;
}

function audioConstructor(): typeof AudioContext | null {
  if (typeof window === "undefined") return null;
  const audioWindow = window as Window & {
    AudioContext?: typeof AudioContext;
    webkitAudioContext?: typeof AudioContext;
  };
  return audioWindow.AudioContext || audioWindow.webkitAudioContext || null;
}

function bindAudioUnlock(AudioCtx: typeof AudioContext): void {
  if (unlockBound || typeof window === "undefined") return;
  const unlock = () => {
    if (!sharedAudioCtx) sharedAudioCtx = new AudioCtx();
    if (sharedAudioCtx.state === "suspended") void sharedAudioCtx.resume().catch(() => undefined);
  };
  window.addEventListener("pointerdown", unlock, { passive: true });
  window.addEventListener("keydown", unlock, { passive: true });
  unlockBound = true;
}

function playTone(ctx: AudioContext, frequency: number, start: number, duration: number, volume: number): void {
  const oscillator = ctx.createOscillator();
  const gain = ctx.createGain();
  oscillator.type = "sine";
  oscillator.frequency.setValueAtTime(frequency, start);
  gain.gain.setValueAtTime(0.0001, start);
  gain.gain.exponentialRampToValueAtTime(volume, start + 0.012);
  gain.gain.exponentialRampToValueAtTime(0.0001, start + duration);
  oscillator.connect(gain);
  gain.connect(ctx.destination);
  oscillator.start(start);
  oscillator.stop(start + duration + 0.02);
}

export function playNotificationCue(cue: NotificationCue = "info"): void {
  if (typeof window === "undefined" || !getNotificationPreferences().audioEnabled) return;
  const AudioCtx = audioConstructor();
  if (!AudioCtx) return;
  bindAudioUnlock(AudioCtx);
  if (!sharedAudioCtx || sharedAudioCtx.state !== "running") {
    if (sharedAudioCtx?.state === "suspended") void sharedAudioCtx.resume().catch(() => undefined);
    return;
  }

  const ctx = sharedAudioCtx;
  const start = ctx.currentTime + 0.015;
  if (cue === "success") {
    playTone(ctx, 660, start, 0.12, 0.055);
    playTone(ctx, 880, start + 0.105, 0.17, 0.065);
    return;
  }
  if (cue === "warning") {
    playTone(ctx, 740, start, 0.14, 0.06);
    playTone(ctx, 740, start + 0.19, 0.14, 0.06);
    return;
  }
  if (cue === "error") {
    playTone(ctx, 520, start, 0.15, 0.065);
    playTone(ctx, 330, start + 0.12, 0.22, 0.075);
    return;
  }
  playTone(ctx, 980, start, 0.15, 0.05);
}

export function playNotificationChirp(): void {
  playNotificationCue("info");
}

export async function pushDesktopNotification(title: string, body: string): Promise<void> {
  if (typeof window === "undefined" || typeof Notification === "undefined") return;
  const prefs = getNotificationPreferences();
  if (!prefs.desktopEnabled) return;
  if (Notification.permission === "granted") {
    new Notification(title, { body });
    return;
  }
  if (Notification.permission !== "denied") {
    const permission = await Notification.requestPermission();
    if (permission === "granted") new Notification(title, { body });
  }
}

export function getEvidenceAcceptString(): string {
  const prefs = getNotificationPreferences();
  const mediaParts: string[] = [];
  if (prefs.enablePhotoUploads) mediaParts.push("image/*");
  if (prefs.enableVideoUploads) mediaParts.push("video/*");
  return [...mediaParts, ".pdf"].join(",");
}

export function isEvidenceFileAllowed(file: File): boolean {
  const prefs = getNotificationPreferences();
  const contentType = file.type.toLowerCase();
  const name = file.name.toLowerCase();
  if (name.endsWith(".pdf") || contentType.includes("pdf")) return true;
  if (prefs.enablePhotoUploads && contentType.startsWith("image/")) return true;
  if (prefs.enableVideoUploads && contentType.startsWith("video/")) return true;
  return false;
}
