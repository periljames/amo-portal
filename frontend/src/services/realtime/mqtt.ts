import { getActiveAmoId, getCachedUser, getContext } from "../auth";
import { fetchRealtimeToken, RealtimeHttpError } from "./api";
import { loadOutbound, queueOutbound, removeOutbound } from "./queue";
import type { BrokerState, RealtimeEnvelope } from "./types";

type Packet = Uint8Array;

type PublishOpts = { qos?: number; retain?: boolean };

type MqttLikeClient = {
  connected: boolean;
  on: (event: string, cb: (...args: unknown[]) => void) => void;
  subscribe: (topics: string[] | string, opts?: PublishOpts) => void;
  publish: (topic: string, payload: Uint8Array, opts: PublishOpts, cb?: () => void) => void;
  end: (force?: boolean) => void;
};

type MqttModule = {
  connect: (url: string, options: Record<string, unknown>) => MqttLikeClient;
};

type MsgpackModule = {
  encode: (value: unknown) => Packet;
  decode: (value: Uint8Array) => unknown;
};

type Handlers = {
  onState: (state: BrokerState) => void;
  onMessage: (msg: RealtimeEnvelope, topic: string) => void;
};

let mqttLibPromise: Promise<MqttModule | null> | null = null;
let msgpackPromise: Promise<MsgpackModule | null> | null = null;

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

function backoffMs(attempt: number): number {
  const capped = Math.min(6, Math.max(0, attempt));
  const base = 1000 * 2 ** capped;
  const jitter = Math.floor(Math.random() * 500);
  return Math.min(30_000, base + jitter);
}

export class RealtimeMqttClient {
  private client: MqttLikeClient | null = null;
  private handlers: Handlers;
  private userId: string;
  private amoId: string;
  private msgpack: MsgpackModule | null = null;
  private reconnectTimer: number | null = null;
  private stopped = false;
  private attempt = 0;

  constructor(handlers: Handlers) {
    const ctx = getContext();
    this.userId = getCachedUser()?.id || "anonymous";
    this.amoId = getActiveAmoId() || ctx.amoCode || "unknown";
    this.handlers = handlers;
  }

  async connect(): Promise<void> {
    this.stopped = false;
    await this.connectOnce();
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private scheduleReconnect(reason: string): void {
    if (this.stopped) return;
    this.clearReconnectTimer();
    this.handlers.onState("reconnecting");
    const wait = backoffMs(this.attempt++);
    console.warn(`[realtime] mqtt reconnect scheduled in ${wait}ms (${reason})`);
    this.reconnectTimer = window.setTimeout(() => {
      void this.connectOnce();
    }, wait);
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
      this.handlers.onState("reconnecting");

      this.teardownClient();
      this.client = mqttLib.connect(tokenData.broker_ws_url, {
        clientId: tokenData.client_id,
        username: this.userId,
        password: tokenData.token,
        reconnectPeriod: 0,
        keepalive: 30,
        clean: true,
        connectTimeout: 10_000,
      });

      this.client.on("connect", () => {
        this.attempt = 0;
        this.clearReconnectTimer();
        this.handlers.onState("connected");
        const inbox = `amo/${this.amoId}/user/${this.userId}/inbox`;
        const ack = `amo/${this.amoId}/user/${this.userId}/ack`;
        this.client?.subscribe([inbox, ack], { qos: 1 });
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
          const packet = payload as Packet;
          const decoded = this.msgpack.decode(packet) as RealtimeEnvelope;
          this.handlers.onMessage(decoded, String(topic));
        } catch {
          // swallow malformed packet
        }
      });
    } catch (err) {
      this.handlers.onState("offline");
      if (err instanceof RealtimeHttpError && (err.status === 401 || err.status === 403)) {
        this.attempt = 6;
        console.info("[realtime] mqtt auth unavailable; backing off reconnect attempts");
        this.scheduleReconnect("auth");
        return;
      }
      console.warn("[realtime] token fetch/connect failed", err);
      this.scheduleReconnect("token");
    }
  }

  async publish(envelope: RealtimeEnvelope): Promise<void> {
    if (!this.client || !this.client.connected || !this.msgpack) {
      await queueOutbound(envelope);
      return;
    }
    const topic = `amo/${this.amoId}/user/${this.userId}/outbox`;
    await new Promise<void>((resolve) => {
      this.client?.publish(topic, this.msgpack!.encode(envelope), { qos: 1 }, () => resolve());
    });
  }

  async flushQueue(): Promise<void> {
    if (!this.client || !this.client.connected) return;
    const pending = await loadOutbound();
    for (const item of pending) {
      await this.publish(item);
      await removeOutbound(item.id);
    }
  }

  disconnect(): void {
    this.stopped = true;
    this.clearReconnectTimer();
    this.teardownClient();
    this.handlers.onState("offline");
  }
}
