import { getApiBaseUrl } from "./config";
import { getToken } from "./auth";

export type ChatThreadKind = "DIRECT" | "DEPARTMENT" | "GROUP";

export type ChatMember = {
  id: string;
  full_name: string;
  position_title?: string | null;
  department_id?: string | null;
  is_active?: boolean;
};

export type ChatThread = {
  id: string;
  title?: string | null;
  kind: ChatThreadKind;
  scope_key?: string | null;
  department_id?: string | null;
  user_group_id?: string | null;
  created_by?: string | null;
  created_at: string;
  updated_at?: string | null;
  last_message_at?: string | null;
  last_message_preview: string;
  member_user_ids: string[];
  members: ChatMember[];
  unread_count: number;
  notification_level: "ALL" | "MENTIONS" | "NONE";
  muted_until?: string | null;
};

export type ChatMessage = {
  id: string;
  thread_id: string;
  sender_id?: string | null;
  body_text: string;
  body_mime: string;
  message_type: string;
  reply_to_message_id?: string | null;
  metadata: Record<string, unknown>;
  client_msg_id: string;
  created_at: string;
  edited_at?: string | null;
  deleted_at?: string | null;
};

export type ChatDirectory = {
  users: Array<{ id: string; full_name: string; position_title?: string | null; department_id?: string | null }>;
  departments: Array<{ id: string; code: string; name: string }>;
  groups: Array<{ id: string; code: string; name: string; description?: string | null; group_type: string }>;
};

export type PortalNotification = {
  id: string;
  kind: string;
  title: string;
  body: string;
  entity_type?: string | null;
  entity_id?: string | null;
  action_url?: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  read_at?: string | null;
  archived_at?: string | null;
};

export type NotificationPreferences = {
  in_app_enabled: boolean;
  desktop_enabled: boolean;
  sound_enabled: boolean;
  email_enabled: boolean;
  chat_enabled: boolean;
  quiet_hours_start?: string | null;
  quiet_hours_end?: string | null;
  updated_at?: string | null;
};

export class MessagingHttpError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "MessagingHttpError";
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  if (!token) throw new MessagingHttpError("Messaging requires an authenticated session", 401);
  const controller = new AbortController();
  const timer = globalThis.setTimeout(() => controller.abort("timeout"), 15_000);
  try {
    const response = await fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      credentials: "include",
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...(init.headers || {}),
      },
    });
    if (!response.ok) {
      let message = `Messaging request failed (${response.status})`;
      try {
        const payload = await response.json() as { detail?: string };
        if (payload.detail) message = payload.detail;
      } catch {
        // Keep stable fallback message.
      }
      throw new MessagingHttpError(message, response.status);
    }
    if (response.status === 204) return undefined as T;
    return await response.json() as T;
  } finally {
    globalThis.clearTimeout(timer);
  }
}

export const messagingApi = {
  directory: () => request<ChatDirectory>("/api/chat/directory"),
  threads: () => request<ChatThread[]>("/api/chat/threads?limit=300"),
  messages: (threadId: string) => request<ChatMessage[]>(`/api/chat/threads/${encodeURIComponent(threadId)}/messages?limit=150`),
  openDirect: (userId: string) => request<ChatThread>(`/api/chat/direct/${encodeURIComponent(userId)}`, { method: "POST" }),
  openDepartment: (departmentId: string) => request<ChatThread>(`/api/chat/departments/${encodeURIComponent(departmentId)}`, { method: "POST" }),
  openGroup: (groupId: string) => request<ChatThread>(`/api/chat/groups/${encodeURIComponent(groupId)}`, { method: "POST" }),
  createGroup: (title: string, memberUserIds: string[]) => request<ChatThread>("/api/chat/threads", {
    method: "POST",
    body: JSON.stringify({ title, member_user_ids: memberUserIds }),
  }),
  send: (threadId: string, body: string, clientMsgId: string, replyToMessageId?: string | null) => request<ChatMessage>(
    `/api/chat/threads/${encodeURIComponent(threadId)}/messages`,
    {
      method: "POST",
      body: JSON.stringify({
        body,
        client_msg_id: clientMsgId,
        reply_to_message_id: replyToMessageId || null,
        metadata: {},
      }),
    },
  ),
  edit: (messageId: string, body: string) => request<ChatMessage>(`/api/chat/messages/${encodeURIComponent(messageId)}`, {
    method: "PATCH",
    body: JSON.stringify({ body }),
  }),
  remove: (messageId: string) => request<ChatMessage>(`/api/chat/messages/${encodeURIComponent(messageId)}`, { method: "DELETE" }),
  markThreadRead: (threadId: string) => request<{ thread_id: string; read_at: string }>(`/api/chat/threads/${encodeURIComponent(threadId)}/read`, { method: "POST" }),
  updateThreadNotifications: (threadId: string, notificationLevel: "ALL" | "MENTIONS" | "NONE", mutedUntil?: string | null) => request(
    `/api/chat/threads/${encodeURIComponent(threadId)}/notifications`,
    { method: "PATCH", body: JSON.stringify({ notification_level: notificationLevel, muted_until: mutedUntil || null }) },
  ),
  notifications: (unreadOnly = false) => request<{ items: PortalNotification[]; total: number }>(`/api/notifications/me?limit=150&unread_only=${unreadOnly ? "true" : "false"}`),
  unreadCount: () => request<{ notifications: number; messages: number; total: number }>("/api/notifications/me/unread-count"),
  markNotificationRead: (notificationId: string) => request<PortalNotification>(`/api/notifications/${encodeURIComponent(notificationId)}/read`, { method: "POST" }),
  markAllNotificationsRead: () => request<{ read_at: string; updated: number }>("/api/notifications/read-all", { method: "POST" }),
  preferences: () => request<NotificationPreferences>("/api/notifications/preferences"),
  updatePreferences: (payload: Partial<NotificationPreferences>) => request<NotificationPreferences>("/api/notifications/preferences", {
    method: "PUT",
    body: JSON.stringify(payload),
  }),
};
