import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./auth", () => ({
  getToken: () => "messaging-token",
}));

vi.mock("./config", () => ({
  getApiBaseUrl: () => "https://api.example.test",
}));

import { messagingApi } from "./messaging";

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("messaging API", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("opens a direct conversation with an encoded same-tenant user id", async () => {
    const thread = {
      id: "thread-1",
      title: "Engineer One",
      kind: "DIRECT",
      created_at: "2026-07-22T00:00:00Z",
      last_message_preview: "",
      member_user_ids: ["me", "user/one"],
      members: [],
      unread_count: 0,
      notification_level: "ALL",
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(thread, 201));

    await expect(messagingApi.openDirect("user/one")).resolves.toEqual(thread);
    expect(fetchMock).toHaveBeenCalledWith(
      "https://api.example.test/api/chat/direct/user%2Fone",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        headers: expect.objectContaining({ Authorization: "Bearer messaging-token" }),
      }),
    );
  });

  it("sends an idempotent message payload with reply context", async () => {
    const response = {
      id: "message-1",
      thread_id: "thread/one",
      sender_id: "me",
      body_text: "Review completed",
      body_mime: "text/plain",
      message_type: "TEXT",
      reply_to_message_id: "message-parent",
      metadata: {},
      client_msg_id: "client-1",
      created_at: "2026-07-22T00:00:00Z",
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(response, 201));

    await messagingApi.send("thread/one", "Review completed", "client-1", "message-parent");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("https://api.example.test/api/chat/threads/thread%2Fone/messages");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      body: "Review completed",
      client_msg_id: "client-1",
      reply_to_message_id: "message-parent",
      metadata: {},
    });
  });

  it("deduplicates and sends validated mention identifiers", async () => {
    const response = {
      id: "message-2",
      thread_id: "thread-mentions",
      sender_id: "me",
      body_text: "Please review",
      body_mime: "text/plain",
      message_type: "TEXT",
      metadata: { mention_user_ids: ["user-1", "user-2"] },
      client_msg_id: "client-mentions",
      created_at: "2026-07-22T00:00:00Z",
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(response, 201));

    await messagingApi.send(
      "thread-mentions",
      "Please review",
      "client-mentions",
      null,
      ["user-1", "user-1", "user-2"],
    );

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(String(init?.body))).toMatchObject({
      metadata: { mention_user_ids: ["user-1", "user-2"] },
    });
  });

  it("keeps routine email notifications opt-in", async () => {
    const preferences = {
      in_app_enabled: true,
      desktop_enabled: true,
      sound_enabled: true,
      email_enabled: false,
      chat_enabled: true,
      quiet_hours_start: null,
      quiet_hours_end: null,
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(preferences));

    await expect(messagingApi.preferences()).resolves.toMatchObject({
      in_app_enabled: true,
      chat_enabled: true,
      email_enabled: false,
    });
  });

  it("surfaces backend membership and tenant validation details", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ detail: "User is not a member of this group" }, 403),
    );

    await expect(messagingApi.openGroup("restricted-group"))
      .rejects.toThrow("User is not a member of this group");
  });
});
