import mqtt from "mqtt";
import { decode, encode } from "@msgpack/msgpack";

import { getCachedUser, getContext } from "../auth";
import { fetchRealtimeToken } from "./api";
import { loadOutbound, queueOutbound, removeOutbound } from "./queue";
import type { BrokerState, RealtimeEnvelope } from "./types";

type Handlers = {
  onState: (state: BrokerState) => void;
  onMessage: (msg: RealtimeEnvelope, topic: string) => void;
};

export class RealtimeMqttClient {
  private client: mqtt.MqttClient | null = null;
  private handlers: Handlers;
  private userId: string;
  private amoId: string;

  constructor(handlers: Handlers) {
    const ctx = getContext();
    this.userId = getCachedUser()?.id || "anonymous";
    this.amoId = ctx.amoCode || "unknown";
    this.handlers = handlers;
  }

  async connect(): Promise<void> {
    const tokenData = await fetchRealtimeToken();
    this.handlers.onState("reconnecting");

    this.client = mqtt.connect(tokenData.broker_ws_url, {
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
      try {
        const decoded = decode(payload) as RealtimeEnvelope;
        this.handlers.onMessage(decoded, topic);
      } catch {
        // swallow malformed packet
      }
    });
  }

  async publish(envelope: RealtimeEnvelope): Promise<void> {
    if (!this.client || !this.client.connected) {
      await queueOutbound(envelope);
      return;
    }
    const topic = `amo/${this.amoId}/user/${this.userId}/outbox`;
    await new Promise<void>((resolve) => {
      this.client?.publish(topic, Buffer.from(encode(envelope)), { qos: 1 }, () => resolve());
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
