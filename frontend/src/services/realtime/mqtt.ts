import { getCachedUser, getContext } from "../auth";
import { fetchRealtimeToken } from "./api";
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

export class RealtimeMqttClient {
  private client: MqttLikeClient | null = null;
  private handlers: Handlers;
  private userId: string;
  private amoId: string;
  private msgpack: MsgpackModule | null = null;

  constructor(handlers: Handlers) {
    const ctx = getContext();
    this.userId = getCachedUser()?.id || "anonymous";
    this.amoId = ctx.amoCode || "unknown";
    this.handlers = handlers;
  }

  async connect(): Promise<void> {
    const [mqttLib, msgpack] = await Promise.all([getMqttLib(), getMsgpack()]);
    if (!mqttLib || !msgpack) {
      this.handlers.onState("offline");
      console.warn("Realtime MQTT dependencies are unavailable. Run: npm install");
      return;
    }
    this.msgpack = msgpack;

    const tokenData = await fetchRealtimeToken();
    this.handlers.onState("reconnecting");

    this.client = mqttLib.connect(tokenData.broker_ws_url, {
      clientId: tokenData.client_id,
      username: this.userId,
      password: tokenData.token,
      reconnectPeriod: 2000,
      keepalive: 30,
      clean: false,
      connectTimeout: 10_000,
    });

    this.client.on("connect", () => {
      this.handlers.onState("connected");
      const inbox = `amo/${this.amoId}/user/${this.userId}/inbox`;
      const ack = `amo/${this.amoId}/user/${this.userId}/ack`;
      this.client?.subscribe([inbox, ack], { qos: 1 });
      void this.flushQueue();
    });

    this.client.on("reconnect", () => this.handlers.onState("reconnecting"));
    this.client.on("offline", () => this.handlers.onState("offline"));
    this.client.on("close", () => this.handlers.onState("offline"));

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
    this.client?.end(true);
    this.client = null;
    this.handlers.onState("offline");
  }
}
