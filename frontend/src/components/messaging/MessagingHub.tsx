import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getCachedUser, getToken } from "../../services/auth";
import {
  ChatDirectory,
  ChatThread,
  messagingApi,
  NotificationPreferences,
  PortalNotification,
} from "../../services/messaging";

const EVENT_NAME = "amo:realtime-envelope";

function initials(value?: string | null): string {
  return (value || "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("") || "?";
}

function relativeTime(raw?: string | null): string {
  if (!raw) return "";
  const value = new Date(raw).getTime();
  if (!Number.isFinite(value)) return "";
  const seconds = Math.max(0, Math.floor((Date.now() - value) / 1000));
  if (seconds < 60) return "now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function targetLabel(kind: ChatThread["kind"]): string {
  if (kind === "DIRECT") return "Direct";
  if (kind === "DEPARTMENT") return "Department";
  return "Group";
}

export function MessagingHub() {
  const queryClient = useQueryClient();
  const user = getCachedUser();
  const authenticated = Boolean(getToken() && user?.id);
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<"chats" | "notifications">("chats");
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [showDirectory, setShowDirectory] = useState(false);
  const [directoryTab, setDirectoryTab] = useState<"users" | "departments" | "groups">("users");
  const [draft, setDraft] = useState("");
  const [showSettings, setShowSettings] = useState(false);
  const messageListRef = useRef<HTMLDivElement | null>(null);
  const lastNotificationId = useRef<string | null>(null);

  const unreadQuery = useQuery({
    queryKey: ["messaging", "unread"],
    queryFn: messagingApi.unreadCount,
    enabled: authenticated,
    refetchInterval: open ? 5_000 : 15_000,
    staleTime: 2_000,
  });
  const threadsQuery = useQuery({
    queryKey: ["messaging", "threads"],
    queryFn: messagingApi.threads,
    enabled: authenticated,
    refetchInterval: open ? 5_000 : 15_000,
    staleTime: 2_000,
  });
  const notificationsQuery = useQuery({
    queryKey: ["messaging", "notifications"],
    queryFn: () => messagingApi.notifications(false),
    enabled: authenticated && (open || (unreadQuery.data?.notifications || 0) > 0),
    refetchInterval: open ? 8_000 : 20_000,
    staleTime: 3_000,
  });
  const directoryQuery = useQuery({
    queryKey: ["messaging", "directory"],
    queryFn: messagingApi.directory,
    enabled: authenticated && open && showDirectory,
    staleTime: 60_000,
  });
  const preferencesQuery = useQuery({
    queryKey: ["messaging", "preferences"],
    queryFn: messagingApi.preferences,
    enabled: authenticated && open,
    staleTime: 60_000,
  });
  const messagesQuery = useQuery({
    queryKey: ["messaging", "messages", selectedThreadId],
    queryFn: () => messagingApi.messages(selectedThreadId as string),
    enabled: authenticated && open && Boolean(selectedThreadId),
    refetchInterval: selectedThreadId ? 3_000 : false,
    staleTime: 1_000,
  });

  const threads = threadsQuery.data || [];
  const selectedThread = useMemo(
    () => threads.find((thread) => thread.id === selectedThreadId) || null,
    [threads, selectedThreadId],
  );

  useEffect(() => {
    if (!selectedThreadId && threads.length > 0 && open && tab === "chats") {
      setSelectedThreadId(threads[0].id);
    }
  }, [open, selectedThreadId, tab, threads]);

  useEffect(() => {
    const onRealtime = () => {
      void queryClient.invalidateQueries({ queryKey: ["messaging"] });
    };
    window.addEventListener(EVENT_NAME, onRealtime);
    return () => window.removeEventListener(EVENT_NAME, onRealtime);
  }, [queryClient]);

  useEffect(() => {
    if (!selectedThreadId || !open || tab !== "chats") return;
    void messagingApi.markThreadRead(selectedThreadId).then(() => {
      void queryClient.invalidateQueries({ queryKey: ["messaging", "unread"] });
      void queryClient.invalidateQueries({ queryKey: ["messaging", "threads"] });
    });
  }, [open, queryClient, selectedThreadId, tab, messagesQuery.data?.length]);

  useEffect(() => {
    const element = messageListRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [messagesQuery.data?.length, selectedThreadId]);

  useEffect(() => {
    const latest = notificationsQuery.data?.items?.[0];
    const preferences = preferencesQuery.data;
    if (!latest || latest.id === lastNotificationId.current) return;
    const previous = lastNotificationId.current;
    lastNotificationId.current = latest.id;
    if (!previous || latest.read_at || !preferences?.desktop_enabled || document.visibilityState === "visible") return;
    if ("Notification" in window && Notification.permission === "granted") {
      new Notification(latest.title, { body: latest.body, tag: latest.id });
    }
  }, [notificationsQuery.data, preferencesQuery.data]);

  const refreshMessaging = () => queryClient.invalidateQueries({ queryKey: ["messaging"] });

  const openTarget = useMutation({
    mutationFn: async (target: { kind: "users" | "departments" | "groups"; id: string }) => {
      if (target.kind === "users") return messagingApi.openDirect(target.id);
      if (target.kind === "departments") return messagingApi.openDepartment(target.id);
      return messagingApi.openGroup(target.id);
    },
    onSuccess: (thread) => {
      setSelectedThreadId(thread.id);
      setShowDirectory(false);
      setTab("chats");
      void refreshMessaging();
    },
  });

  const sendMessage = useMutation({
    mutationFn: ({ threadId, body }: { threadId: string; body: string }) => messagingApi.send(
      threadId,
      body,
      `web-${Date.now()}-${crypto.randomUUID().slice(0, 12)}`,
    ),
    onSuccess: () => {
      setDraft("");
      void refreshMessaging();
    },
  });

  const markNotification = useMutation({
    mutationFn: messagingApi.markNotificationRead,
    onSuccess: (notification) => {
      const threadId = notification.entity_type === "chat_thread" ? notification.entity_id : null;
      if (threadId) {
        setSelectedThreadId(threadId);
        setTab("chats");
      }
      void refreshMessaging();
    },
  });

  const markAll = useMutation({
    mutationFn: messagingApi.markAllNotificationsRead,
    onSuccess: () => void refreshMessaging(),
  });

  const updatePreferences = useMutation({
    mutationFn: (payload: Partial<NotificationPreferences>) => messagingApi.updatePreferences(payload),
    onSuccess: (value) => {
      queryClient.setQueryData(["messaging", "preferences"], value);
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const body = draft.trim();
    if (!selectedThreadId || !body || sendMessage.isPending) return;
    sendMessage.mutate({ threadId: selectedThreadId, body });
  };

  if (!authenticated) return null;

  const unreadTotal = unreadQuery.data?.total || 0;
  const preferences = preferencesQuery.data;

  return (
    <div className="messaging-hub" aria-live="polite">
      {open ? (
        <section className="messaging-panel" aria-label="Messages and notifications">
          <header className="messaging-header">
            <div>
              <strong>Inbox</strong>
              <span>{unreadTotal ? `${unreadTotal} unread` : "All caught up"}</span>
            </div>
            <div className="messaging-header-actions">
              <button type="button" className="messaging-icon-button" onClick={() => setShowSettings((value) => !value)} aria-label="Notification settings">⚙</button>
              <button type="button" className="messaging-icon-button" onClick={() => setOpen(false)} aria-label="Close inbox">×</button>
            </div>
          </header>

          {showSettings && preferences ? (
            <div className="messaging-settings">
              <label><input type="checkbox" checked={preferences.in_app_enabled} onChange={(event) => updatePreferences.mutate({ in_app_enabled: event.target.checked })} /> In-app alerts</label>
              <label><input type="checkbox" checked={preferences.desktop_enabled} onChange={(event) => {
                if (event.target.checked && "Notification" in window && Notification.permission === "default") void Notification.requestPermission();
                updatePreferences.mutate({ desktop_enabled: event.target.checked });
              }} /> Desktop alerts</label>
              <label><input type="checkbox" checked={preferences.sound_enabled} onChange={(event) => updatePreferences.mutate({ sound_enabled: event.target.checked })} /> Sound</label>
              <label title="Email is off by default to prevent routine chat spam"><input type="checkbox" checked={preferences.email_enabled} onChange={(event) => updatePreferences.mutate({ email_enabled: event.target.checked })} /> Email summaries</label>
            </div>
          ) : null}

          <nav className="messaging-tabs" aria-label="Inbox sections">
            <button type="button" className={tab === "chats" ? "is-active" : ""} onClick={() => setTab("chats")}>Chats <span>{unreadQuery.data?.messages || 0}</span></button>
            <button type="button" className={tab === "notifications" ? "is-active" : ""} onClick={() => setTab("notifications")}>Notifications <span>{unreadQuery.data?.notifications || 0}</span></button>
          </nav>

          {tab === "notifications" ? (
            <NotificationList
              notifications={notificationsQuery.data?.items || []}
              loading={notificationsQuery.isLoading}
              onRead={(notification) => markNotification.mutate(notification.id)}
              onReadAll={() => markAll.mutate()}
            />
          ) : (
            <div className="messaging-chat-layout">
              <aside className="messaging-thread-list">
                <div className="messaging-thread-toolbar">
                  <span>Conversations</span>
                  <button type="button" onClick={() => setShowDirectory((value) => !value)}>New</button>
                </div>
                {showDirectory ? (
                  <DirectoryPicker
                    data={directoryQuery.data}
                    loading={directoryQuery.isLoading}
                    activeTab={directoryTab}
                    onTab={setDirectoryTab}
                    onSelect={(id) => openTarget.mutate({ kind: directoryTab, id })}
                  />
                ) : null}
                <div className="messaging-thread-scroll">
                  {threads.map((thread) => (
                    <button
                      type="button"
                      className={`messaging-thread ${thread.id === selectedThreadId ? "is-selected" : ""}`}
                      key={thread.id}
                      onClick={() => { setSelectedThreadId(thread.id); setShowDirectory(false); }}
                    >
                      <span className="messaging-avatar">{initials(thread.title)}</span>
                      <span className="messaging-thread-copy">
                        <span><strong>{thread.title || "Conversation"}</strong><time>{relativeTime(thread.last_message_at || thread.updated_at)}</time></span>
                        <span>{thread.last_message_preview || targetLabel(thread.kind)}</span>
                      </span>
                      {thread.unread_count ? <b className="messaging-badge">{thread.unread_count}</b> : null}
                    </button>
                  ))}
                  {!threadsQuery.isLoading && threads.length === 0 ? <p className="messaging-empty">No conversations yet. Start with a person, department or group.</p> : null}
                </div>
              </aside>

              <main className="messaging-conversation">
                {selectedThread ? (
                  <>
                    <div className="messaging-conversation-title">
                      <div><strong>{selectedThread.title || "Conversation"}</strong><span>{targetLabel(selectedThread.kind)} · {selectedThread.members.length} member{selectedThread.members.length === 1 ? "" : "s"}</span></div>
                      <select
                        aria-label="Conversation notification level"
                        value={selectedThread.notification_level}
                        onChange={(event) => {
                          void messagingApi.updateThreadNotifications(selectedThread.id, event.target.value as "ALL" | "MENTIONS" | "NONE").then(refreshMessaging);
                        }}
                      >
                        <option value="ALL">All alerts</option>
                        <option value="MENTIONS">Mentions</option>
                        <option value="NONE">Muted</option>
                      </select>
                    </div>
                    <div className="messaging-message-list" ref={messageListRef}>
                      {(messagesQuery.data || []).map((message) => {
                        const own = message.sender_id === user?.id;
                        const sender = selectedThread.members.find((member) => member.id === message.sender_id);
                        return (
                          <article className={`messaging-message ${own ? "is-own" : ""}`} key={message.id}>
                            {!own ? <span className="messaging-avatar is-small">{initials(sender?.full_name)}</span> : null}
                            <div>
                              {!own ? <small>{sender?.full_name || "User"}</small> : null}
                              <p>{message.deleted_at ? "Message removed" : message.body_text}</p>
                              <time>{new Date(message.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}{message.edited_at ? " · edited" : ""}</time>
                            </div>
                          </article>
                        );
                      })}
                      {messagesQuery.isLoading ? <p className="messaging-empty">Loading conversation…</p> : null}
                    </div>
                    <form className="messaging-composer" onSubmit={submit}>
                      <textarea value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Write a message" rows={2} maxLength={8000} />
                      <button type="submit" disabled={!draft.trim() || sendMessage.isPending}>{sendMessage.isPending ? "Sending" : "Send"}</button>
                    </form>
                    {sendMessage.error ? <p className="messaging-error">{sendMessage.error.message}</p> : null}
                  </>
                ) : <p className="messaging-empty is-centered">Select a conversation.</p>}
              </main>
            </div>
          )}
        </section>
      ) : null}

      <button type="button" className="messaging-launcher" onClick={() => setOpen(true)} aria-label={`Open inbox${unreadTotal ? `, ${unreadTotal} unread` : ""}`}>
        <span aria-hidden="true">✉</span>
        {unreadTotal ? <b>{unreadTotal > 99 ? "99+" : unreadTotal}</b> : null}
      </button>
    </div>
  );
}

function DirectoryPicker({
  data,
  loading,
  activeTab,
  onTab,
  onSelect,
}: {
  data?: ChatDirectory;
  loading: boolean;
  activeTab: "users" | "departments" | "groups";
  onTab: (value: "users" | "departments" | "groups") => void;
  onSelect: (id: string) => void;
}) {
  const entries = data?.[activeTab] || [];
  return (
    <div className="messaging-directory">
      <div className="messaging-directory-tabs">
        <button type="button" className={activeTab === "users" ? "is-active" : ""} onClick={() => onTab("users")}>People</button>
        <button type="button" className={activeTab === "departments" ? "is-active" : ""} onClick={() => onTab("departments")}>Dept.</button>
        <button type="button" className={activeTab === "groups" ? "is-active" : ""} onClick={() => onTab("groups")}>Groups</button>
      </div>
      <div className="messaging-directory-list">
        {entries.map((entry) => (
          <button type="button" key={entry.id} onClick={() => onSelect(entry.id)}>
            <span className="messaging-avatar is-small">{initials("full_name" in entry ? entry.full_name : entry.name)}</span>
            <span><strong>{"full_name" in entry ? entry.full_name : entry.name}</strong><small>{"position_title" in entry ? entry.position_title : "code" in entry ? entry.code : entry.group_type}</small></span>
          </button>
        ))}
        {loading ? <p className="messaging-empty">Loading directory…</p> : null}
        {!loading && entries.length === 0 ? <p className="messaging-empty">Nothing available here.</p> : null}
      </div>
    </div>
  );
}

function NotificationList({ notifications, loading, onRead, onReadAll }: {
  notifications: PortalNotification[];
  loading: boolean;
  onRead: (notification: PortalNotification) => void;
  onReadAll: () => void;
}) {
  return (
    <div className="messaging-notifications">
      <div className="messaging-notification-toolbar">
        <span>{notifications.length} recent</span>
        <button type="button" onClick={onReadAll}>Mark all read</button>
      </div>
      <div className="messaging-notification-scroll">
        {notifications.map((notification) => (
          <button type="button" className={notification.read_at ? "" : "is-unread"} key={notification.id} onClick={() => onRead(notification)}>
            <span className="messaging-notification-dot" />
            <span><strong>{notification.title}</strong><p>{notification.body}</p><time>{relativeTime(notification.created_at)}</time></span>
          </button>
        ))}
        {loading ? <p className="messaging-empty">Loading notifications…</p> : null}
        {!loading && notifications.length === 0 ? <p className="messaging-empty is-centered">No notifications.</p> : null}
      </div>
    </div>
  );
}
