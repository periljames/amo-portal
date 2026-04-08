export type PollBroadcastMessage = {
  type: string;
  payload?: unknown;
};

const LEASE_MS = 45_000;
const HEARTBEAT_MS = 10_000;

type LeaseRecord = {
  owner: string;
  expiresAt: number;
};

function safeParseLease(raw: string | null): LeaseRecord | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as LeaseRecord;
    if (!parsed?.owner || typeof parsed.expiresAt !== "number") return null;
    return parsed;
  } catch {
    return null;
  }
}

function randomTabId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `tab-${Math.random().toString(36).slice(2)}-${Date.now()}`;
}

export class BrowserPollCoordinator {
  private readonly leaseKey: string;
  private readonly tabId: string;
  private readonly channel: BroadcastChannel | null;
  private heartbeatTimer: number | null = null;
  private storageListener?: (event: StorageEvent) => void;
  private visibilityListener?: () => void;
  private messageListener?: (event: MessageEvent<PollBroadcastMessage>) => void;

  constructor(scope: string) {
    this.leaseKey = `amo:poll-lease:${scope}`;
    this.tabId = randomTabId();
    this.channel = typeof BroadcastChannel !== "undefined" ? new BroadcastChannel(`amo:poll:${scope}`) : null;
  }

  isLeader(): boolean {
    if (typeof window === "undefined") return true;
    const lease = safeParseLease(window.localStorage.getItem(this.leaseKey));
    return Boolean(lease && lease.owner === this.tabId && lease.expiresAt > Date.now());
  }

  private writeLease(): void {
    if (typeof window === "undefined") return;
    const next: LeaseRecord = { owner: this.tabId, expiresAt: Date.now() + LEASE_MS };
    window.localStorage.setItem(this.leaseKey, JSON.stringify(next));
  }

  private tryAcquire(): boolean {
    if (typeof window === "undefined") return true;
    const now = Date.now();
    const current = safeParseLease(window.localStorage.getItem(this.leaseKey));
    if (!current || current.expiresAt <= now || current.owner === this.tabId) {
      this.writeLease();
      return true;
    }
    return false;
  }

  private maintainLease = (): void => {
    if (typeof document !== "undefined" && document.hidden) {
      return;
    }
    if (this.isLeader()) {
      this.writeLease();
      return;
    }
    this.tryAcquire();
  };

  start(onMessage?: (message: PollBroadcastMessage) => void): () => void {
    this.maintainLease();
    if (this.heartbeatTimer !== null) {
      window.clearInterval(this.heartbeatTimer);
    }
    this.heartbeatTimer = window.setInterval(this.maintainLease, HEARTBEAT_MS);

    if (onMessage && this.channel) {
      this.messageListener = (event) => onMessage(event.data);
      this.channel.addEventListener("message", this.messageListener);
    }

    this.storageListener = (event: StorageEvent) => {
      if (event.key === this.leaseKey && !this.isLeader()) {
        this.tryAcquire();
      }
    };
    window.addEventListener("storage", this.storageListener);

    this.visibilityListener = () => {
      if (!document.hidden) {
        this.maintainLease();
      }
    };
    document.addEventListener("visibilitychange", this.visibilityListener);

    return () => this.stop();
  }

  broadcast(type: string, payload?: unknown): void {
    this.channel?.postMessage({ type, payload });
  }

  stop(): void {
    if (this.heartbeatTimer !== null) {
      window.clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    if (this.storageListener) {
      window.removeEventListener("storage", this.storageListener);
      this.storageListener = undefined;
    }
    if (this.visibilityListener) {
      document.removeEventListener("visibilitychange", this.visibilityListener);
      this.visibilityListener = undefined;
    }
    if (this.channel && this.messageListener) {
      this.channel.removeEventListener("message", this.messageListener);
      this.messageListener = undefined;
    }

    if (typeof window !== "undefined" && this.isLeader()) {
      window.localStorage.removeItem(this.leaseKey);
    }
  }
}
