import { getActiveAmoId, getCachedUser, getContext } from "../auth";
import { fetchRealtimeToken, RealtimeHttpError } from "./api";
import { loadOutbound, queueOutbound, removeOutbound } from "./queue";
import type { BrokerState, RealtimeEnvelope } from "./types";

type Packet = Uint8Array;
type PublishOpts = { qos?: number; retain?: boolean };
type PublishCallback = (error?: Error) => void;
type MqttLikeClient = {
  connected: boolean;
  on: (event: string, cb: (...args: unknown[]) => void) => void;
  subscribe: (topics: string[] | string, opts?: PublishOpts) => void;
  publish: (topic: string, payload: Uint8Array, opts: PublishOpts, cb?: PublishCallback) => void;
  end: (force?: boolean) => void;
};
type MqttModule = { connect: (url: string, options: Record<string, unknown>) => MqttLikeClient };
type MsgpackModule = { encode: (value: unknown) => Packet; decode: (value: Uint8Array) => unknown };
type Handlers = {
  onState: (state: BrokerState) => void;
  onMessage: (msg: RealtimeEnvelope, topic: string) => void;
  onUnavailable?: (reason: string) => void;
};

let mqttLibPromise: Promise<MqttModule | null> | null = null;
let msgpackPromise: Promise<MsgpackModule | null> | null = null;
const MAX_MQTT_RECONNECT_ATTEMPTS = 6;
const PUBLISH_TIMEOUT_MS = 10_000;

async function getMqttLib(): Promise<MqttModule | null> {
  if (!mqttLibPromise) {
    mqttLibPromise = import("mqtt")
      .then((mod) => mod.default as unknown as MqttModule)
      .catch(() => null);
  }
  return mqttLibPromise;
}

async function getMsgpack(): Promise<MsgpackModule | null> {
  if (!msgpackPromise) {
    msgpackPromise = import("@msgpack/msgpack")
      .then((mod) => ({ encode: mod.encode, decode: mod.decode }))
      .catch(() => null);
  }
  return msgpackPromise;
}

function isLikelyLocalBrokerUrl(rawUrl: string): boolean {
  try {
    const u = new URL(rawUrl);
    return u.hostname === "localhost" || u.hostname === "127.0.0.1" || u.hostname === "::1";
  } catch {
    return false;
  }
}

function isLocalAppHost(): boolean {
  const host = window.location.hostname;
  return host === "localhost" || host === "127.0.0.1" || host === "::1";
}

function resolveBrokerUrl(rawUrl: string): string {
  if (!isLikelyLocalBrokerUrl(rawUrl) || isLocalAppHost()) return rawUrl;
  try {
    const url = new URL(rawUrl);
    const app = window.location;
    url.hostname = app.hostname;
    if (!url.port && app.port) url.port = app.port;
    return url.toString();
  } catch {
    return rawUrl;
  }
}

function backoffMs(attempt: number): number {
  const capped = Math.min(6, Math.max(0, attempt));
  const base = 1000 * 2 ** capped;
  const jitter = Math.floor(Math.random() * 500);
  return Math.min(30_000, base + jitter);
}

export function publishWithAcknowledgement(
  client: MqttLikeClient,
  topic: string,
  payload: Uint8Array,
  timeoutMs = PUBLISH_TIMEOUT_MS,
): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    let settled = false;
    const finish = (error?: Error) => {
      if (settled) return;
      settled = true;
      globalThis.clearTimeout(timer);
      if (error) reject(error);
      else resolve();
    };
    const timer = globalThis.setTimeout(
      () => finish(new Error("MQTT publish acknowledgement timed out")),
      Math.max(1000, timeoutMs),
    );
    try {
      client.publish(topic, payload, { qos: 1 }, (error) => finish(error));
    } catch (error) {
      finish(error instanceof Error ? error : new Error(String(error)));
    }
  });
}

export class RealtimeMqttClient {
  private client: MqttLikeClient | null = null;
  private handlers: Handlers;
  private userId: string;
  private amoId: string;
  private msgpack: MsgpackModule | null = null;
  private reconnectTimer: number | null = null;
  private tokenRefreshTimer: number | null = null;
  private sessionToken: string | null = null;
  private stopped = false;
  private attempt = 0;
  private authBlocked = false;
  private tokenRefreshInProgress = false;
  private flushing = false;

  constructor(handlers: Handlers) {
    const ctx = getContext();
    this.userId = getCachedUser()?.id || "anonymous";
    this.amoId = getActiveAmoId() || ctx.amoCode || "unknown";
    this.handlers = handlers;
  }

  async connect(): Promise<void> {
    this.stopped = false;
    this.authBlocked = false;
    await this.connectOnce();
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private clearTokenRefreshTimer(): void {
    if (this.tokenRefreshTimer !== null) {
      window.clearTimeout(this.tokenRefreshTimer);
      this.tokenRefreshTimer = null;
    }
  }

  private scheduleReconnect(reason: string): void {
    if (this.stopped || this.tokenRefreshInProgress) return;
    if (this.attempt >= MAX_MQTT_RECONNECT_ATTEMPTS) {
      this.handlers.onState("offline");
      this.handlers.onUnavailable?.(`mqtt reconnect limit reached (${reason})`);
      console.info("[realtime] mqtt disabled for this session after repeated failures");
      return;
    }
    this.clearReconnectTimer();
    this.handlers.onState("reconnecting");
    const wait = backoffMs(this.attempt++);
    console.warn(`[realtime] mqtt reconnect scheduled in ${wait}ms (${reason})`);
    this.reconnectTimer = window.setTimeout(() => void this.connectOnce(), wait);
  }

  private scheduleTokenRefresh(ttlSeconds: number): void {
    this.clearTokenRefreshTimer();
    const refreshMs = Math.max(15_000, ttlSeconds * 1000 - 15_000);
    this.tokenRefreshTimer = window.setTimeout(() => {
      if (this.stopped) return;
      this.tokenRefreshInProgress = true;
      this.teardownClient();
      void this.connectOnce().finally(() => {
        this.tokenRefreshInProgress = false;
      });
    }, refreshMs);
  }

  private teardownClient(): void {
    if (this.client) {
      try {
        this.client.end(true);
      } catch {
        // noop
      }
      this.client = null;
    }
  }

  private async connectOnce(): Promise<void> {
    if (this.authBlocked || this.stopped) {
      this.handlers.onState("offline");
      return;
    }
    const [mqttLib, msgpack] = await Promise.all([getMqttLib(), getMsgpack()]);
    if (!mqttLib || !msgpack) {
      this.handlers.onState("offline");
      console.warn("Realtime MQTT dependencies are unavailable. Run: npm install");
      return;
    }
    this.msgpack = msgpack;

    try {
      const tokenData = await fetchRealtimeToken();
      this.amoId = tokenData.amo_id || this.amoId;
      this.sessionToken = tokenData.token;
      this.handlers.onState("reconnecting");
      const brokerUrl = resolveBrokerUrl(tokenData.broker_ws_url);
      if (brokerUrl !== tokenData.broker_ws_url) {
        console.warn(`[realtime] MQTT broker URL ${tokenData.broker_ws_url} was rewritten for the current host`);
      }
      this.teardownClient();
      this.client = mqttLib.connect(brokerUrl, {
        clientId: tokenData.client_id,
        username: this.userId,
        password: tokenData.token,
        reconnectPeriod: 0,
        keepalive: 30,
        clean: true,
        connectTimeout: 4_000,
      });
      this.scheduleTokenRefresh(tokenData.ttl_seconds);

      this.client.on("connect", () => {
        this.attempt = 0;
        this.clearReconnectTimer();
        this.handlers.onState("connected");
        this.client?.subscribe([
          `amo/${this.amoId}/user/${this.userId}/inbox`,
          `amo/${this.amoId}/user/${this.userId}/ack`,
        ], { qos: 1 });
        void this.flushQueue();
      });
      this.client.on("offline", () => {
        this.handlers.onState("offline");
        this.scheduleReconnect("offline");
      });
      this.client.on("close", () => {
        this.handlers.onState("offline");
        this.scheduleReconnect("close");
      });
      this.client.on("error", (err) => {
        this.handlers.onState("offline");
        console.warn("[realtime] mqtt error", err);
        this.scheduleReconnect("error");
      });
      this.client.on("message", (topic, payload) => {
        if (!this.msgpack) return;
        try {
          const decoded = this.msgpack.decode(payload as Packet) as RealtimeEnvelope;
          delete decoded.authToken;
          this.handlers.onMessage(decoded, String(topic));
        } catch {
          // Ignore malformed broker packets.
        }
      });
    } catch (err) {
      this.handlers.onState("offline");
      this.sessionToken = null;
      this.clearTokenRefreshTimer();
      if (err instanceof RealtimeHttpError && (err.status === 401 || err.status === 403)) {
        this.authBlocked = true;
        this.clearReconnectTimer();
        console.info("[realtime] mqtt auth unavailable; reconnect paused until next authenticated session");
        return;
      }
      console.warn("[realtime] token fetch/connect failed", err);
      this.scheduleReconnect("token");
    }
  }

  private async publishConnected(envelope: RealtimeEnvelope): Promise<void> {
    const client = this.client;
    const msgpack = this.msgpack;
    const token = this.sessionToken;
    if (!client || !client.connected || !msgpack || !token) {
      throw new Error("MQTT connection is not ready")
    }
    const topic = `amo/${this.amoId}/user/${this.userId}/outbox`;
    const wireEnvelope: RealtimeEnvelope = { ...envelope, authToken: token };
    await publishWithAcknowledgement(client, topic, msgpack.encode(wireEnvelope));
  }

  async publish(envelope: RealtimeEnvelope): Promise<void> {
    const queued = { ...envelope };
    delete queued.authToken;
    if (!this.client || !this.client.connected || !this.msgpack || !this.sessionToken) {
      await queueOutbound(queued);
      return;
    }
    try {
      await this.publishConnected(queued);
    } catch (error) {
      await queueOutbound(queued);
      this.handlers.onState("offline");
      this.scheduleReconnect("publish");
      throw error;
    }
  }

  async flushQueue(): Promise<void> {
    if (this.flushing || !this.client || !this.client.connected || !this.sessionToken) return;
    this.flushing = true;
    try {
      const pending = await loadOutbound();
      for (const item of pending) {
        try {
          await this.publishConnected(item);
          await removeOutbound(item.id);
        } catch (error) {
          console.warn("[realtime] queued MQTT publish retained for retry", error);
          this.handlers.onState("offline");
          this.scheduleReconnect("queued-publish");
          break;
        }
      }
    } finally {
      this.flushing = false;
    }
  }

  disconnect(): void {
    this.stopped = true;
    this.sessionToken = null;
    this.clearReconnectTimer();
    this.clearTokenRefreshTimer();
    this.teardownClient();
    this.handlers.onState("offline");
  }
}
