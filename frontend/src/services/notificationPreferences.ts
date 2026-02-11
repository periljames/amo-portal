export const NOTIFICATION_PREFS_EVENT = "amodb:notification-prefs";
const PREFS_STORAGE_KEY = "amodb_notification_preferences";

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

export function playNotificationChirp(): void {
  if (typeof window === "undefined") return;
  const prefs = getNotificationPreferences();
  if (!prefs.audioEnabled) return;
  const AudioCtx = (window as Window & { AudioContext?: typeof AudioContext; webkitAudioContext?: typeof AudioContext }).AudioContext
    || (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioCtx) return;
  const ctx = new AudioCtx();
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = "sine";
  osc.frequency.setValueAtTime(1320, ctx.currentTime);
  gain.gain.setValueAtTime(0.001, ctx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.08, ctx.currentTime + 0.01);
  gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.16);
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start();
  osc.stop(ctx.currentTime + 0.18);
  window.setTimeout(() => {
    void ctx.close();
  }, 250);
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
    if (permission === "granted") {
      new Notification(title, { body });
    }
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
