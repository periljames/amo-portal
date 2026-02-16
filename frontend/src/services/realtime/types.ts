export type RealtimeKind =
  | "chat.message"
  | "chat.message.edited"
  | "chat.message.deleted"
  | "chat.thread.created"
  | "prompt.authorization"
  | "prompt.task_assigned"
  | "presence.snapshot"
  | "chat.send"
  | "chat.edit"
  | "chat.delete"
  | "ack.delivered"
  | "ack.read"
  | "ack.actioned"
  | "presence.online"
  | "presence.away"
  | "presence.typing";

export type RealtimeEnvelope = {
  v: number;
  id: string;
  ts: number;
  amoId: string;
  userId: string;
  kind: RealtimeKind;
  payload: Record<string, unknown>;
};

export type BrokerState = "connected" | "reconnecting" | "offline";

export type RealtimeTokenResponse = {
  token: string;
  broker_ws_url: string;
  client_id: string;
  amo_id: string;
  expires_at: string;
  ttl_seconds: number;
};
