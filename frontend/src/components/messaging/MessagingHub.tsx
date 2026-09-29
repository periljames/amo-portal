import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  Bell,
  Bot,
  CheckCircle2,
  Clock3,
  ExternalLink,
  MessageCircle,
  Search,
  Settings,
  Sparkles,
  X,
} from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { useToast } from "../feedback/ToastProvider";
import { getCachedUser, getToken } from "../../services/auth";
import { assistDocumentation, type DocumentationAssistResponse } from "../../services/documentationAssistant";
import { messagingApi } from "../../services/messaging";
import type {
  ChatDirectory,
  ChatThread,
  NotificationPreferences,
  PortalNotification,
} from "../../services/messaging";
import {
  groupNotifications,
  notificationActionLabel,
  notificationBusinessState,
  notificationDueAt,
  notificationGroupHasUnread,
  notificationGroupMatches,
  notificationModule,
  notificationNeedsAttention,
  notificationTone,
  type NotificationFilter,
  type NotificationGroup,
  type NotificationView,
} from "./notificationModel";

const EVENT_NAME = "amo:realtime-envelope";
const OPEN_EVENT = "amo:messaging-open";
type DirectoryTab = "users" | "departments" | "groups";
type MessagingSurface = "messages" | "notifications";
type OpenSurfaceDetail = { surface: MessagingSurface; threadId?: string | null };

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
  const days = Math.floor(hours / 24);
  return days < 14 ? `${days}d` : new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short" }).format(new Date(raw));
}

function targetLabel(kind: ChatThread["kind"]): string {
  if (kind === "DIRECT") return "Direct";
  if (kind === "DEPARTMENT") return "Department";
  return "Group";
}

function badgeLabel(value: number): string {
  return value > 99 ? "99+" : String(value);
}

function dueLabel(notification: PortalNotification): string | null {
  const raw = notificationDueAt(notification);
  if (!raw) return null;
  const due = new Date(raw);
  if (!Number.isFinite(due.getTime())) return null;
  const dayMs = 86_400_000;
  const delta = Math.ceil((due.getTime() - Date.now()) / dayMs);
  const absolute = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: due.getFullYear() !== new Date().getFullYear() ? "numeric" : undefined }).format(due);
  if (delta < 0) return `${Math.abs(delta)} day${Math.abs(delta) === 1 ? "" : "s"} overdue · ${absolute}`;
  if (delta === 0) return `Due today · ${absolute}`;
  if (delta === 1) return `Due tomorrow · ${absolute}`;
  return `Due in ${delta} days · ${absolute}`;
}

function notificationStateLabel(notification: PortalNotification): string {
  const state = notificationBusinessState(notification);
  if (state === "ACTION_REQUIRED") return "Action required";
  if (state === "DUE_SOON") return "Due soon";
  if (state === "OVERDUE") return "Overdue";
  if (state === "COMPLETED") return "Completed";
  return notificationModule(notification);
}

function dispatchOpen(detail: OpenSurfaceDetail): void {
  window.dispatchEvent(new CustomEvent<OpenSurfaceDetail>(OPEN_EVENT, { detail }));
}

export function MessagingHeaderLaunchers() {
  const user = getCachedUser();
  const authenticated = Boolean(getToken() && user?.id && user?.amo_id);
  const unreadQuery = useQuery({
    queryKey: ["messaging", "unread"],
    queryFn: messagingApi.unreadCount,
    enabled: authenticated,
    refetchInterval: 15_000,
    staleTime: 2_000,
  });
  if (!authenticated) return null;
  const unreadMessages = unreadQuery.data?.messages || 0;
  const unreadNotifications = unreadQuery.data?.notifications || 0;

  return (
    <div className="messaging-header-launchers" aria-label="Messages and notifications">
      <button
        type="button"
        className="tenant-shell__icon-button messaging-header-button"
        onClick={() => dispatchOpen({ surface: "messages" })}
        aria-label={`Messages${unreadMessages ? `, ${unreadMessages} unread` : ""}`}
        title="Messages"
      >
        <MessageCircle size={17} aria-hidden="true" />
        {unreadMessages ? <b>{badgeLabel(unreadMessages)}</b> : null}
      </button>
      <button
        type="button"
        className="tenant-shell__icon-button messaging-header-button"
        onClick={() => dispatchOpen({ surface: "notifications" })}
        aria-label={`Notifications${unreadNotifications ? `, ${unreadNotifications} unread` : ""}`}
        title="Notifications"
      >
        <Bell size={17} aria-hidden="true" />
        {unreadNotifications ? <b>{badgeLabel(unreadNotifications)}</b> : null}
      </button>
    </div>
  );
}

export function MessagingHub() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { pushToast } = useToast();
  const user = getCachedUser();
  const authenticated = Boolean(getToken() && user?.id && user?.amo_id);
  const tenant = user?.amo_slug || user?.amo_code || "";
  const [surface, setSurface] = useState<MessagingSurface | null>(null);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [showDirectory, setShowDirectory] = useState(false);
  const [directoryTab, setDirectoryTab] = useState<DirectoryTab>("users");
  const [draft, setDraft] = useState("");
  const [mentionUserIds, setMentionUserIds] = useState<string[]>([]);
  const [showSettings, setShowSettings] = useState(false);
  const [threadSearch, setThreadSearch] = useState("");
  const [notificationView, setNotificationView] = useState<NotificationView>("for-you");
  const [notificationFilter, setNotificationFilter] = useState<NotificationFilter>("all");
  const [notificationSearch, setNotificationSearch] = useState("");
  const [aiNotificationId, setAiNotificationId] = useState<string | null>(null);
  const [aiResult, setAiResult] = useState<DocumentationAssistResponse | null>(null);
  const [aiError, setAiError] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const messageListRef = useRef<HTMLDivElement | null>(null);
  const aiSerial = useRef(0);
  const seenNotificationIds = useRef(new Set<string>());
  const notificationsInitialized = useRef(false);

  const unreadQuery = useQuery({
    queryKey: ["messaging", "unread"],
    queryFn: messagingApi.unreadCount,
    enabled: authenticated,
    refetchInterval: surface ? 5_000 : 15_000,
    staleTime: 2_000,
  });
  const threadsQuery = useQuery({
    queryKey: ["messaging", "threads"],
    queryFn: messagingApi.threads,
    enabled: authenticated,
    refetchInterval: surface === "messages" ? 5_000 : 15_000,
    staleTime: 2_000,
  });
  const notificationsQuery = useQuery({
    queryKey: ["messaging", "notifications"],
    queryFn: () => messagingApi.notifications({ limit: 150 }),
    enabled: authenticated,
    refetchInterval: surface === "notifications" ? 8_000 : 20_000,
    staleTime: 3_000,
  });
  const directoryQuery = useQuery({
    queryKey: ["messaging", "directory"],
    queryFn: messagingApi.directory,
    enabled: authenticated && surface === "messages" && showDirectory,
    staleTime: 60_000,
  });
  const preferencesQuery = useQuery({
    queryKey: ["messaging", "preferences"],
    queryFn: messagingApi.preferences,
    enabled: authenticated,
    staleTime: 60_000,
  });

  const threads = useMemo(() => threadsQuery.data || [], [threadsQuery.data]);
  const effectiveThreadId = selectedThreadId || (surface === "messages" ? threads[0]?.id || null : null);
  const selectedThread = useMemo(
    () => threads.find((thread) => thread.id === effectiveThreadId) || null,
    [effectiveThreadId, threads],
  );
  const mentionCandidates = useMemo(
    () => (selectedThread?.members || []).filter((member) => member.id !== user?.id),
    [selectedThread, user?.id],
  );
  const visibleNotifications = useMemo(
    () => (notificationsQuery.data?.items || []).filter((notification) => notification.kind !== "CHAT_MESSAGE"),
    [notificationsQuery.data?.items],
  );
  const allNotificationGroups = useMemo(
    () => groupNotifications(visibleNotifications),
    [visibleNotifications],
  );
  const attentionCount = useMemo(
    () => allNotificationGroups.filter((group) => notificationNeedsAttention(group.latest)).length,
    [allNotificationGroups],
  );
  const notificationGroups = useMemo(() => {
    const search = notificationSearch.trim().toLowerCase();
    return allNotificationGroups.filter((group) => {
      if (!notificationGroupMatches(group, notificationView, notificationFilter)) return false;
      if (!search) return true;
      return [group.latest, ...group.earlier].some((notification) => [
        notification.title,
        notification.body,
        notification.kind,
        notification.entity_type,
        notificationModule(notification),
      ].some((value) => String(value || "").toLowerCase().includes(search)));
    });
  }, [allNotificationGroups, notificationFilter, notificationSearch, notificationView]);

  const filteredThreads = useMemo(() => {
    const search = threadSearch.trim().toLowerCase();
    if (!search) return threads;
    return threads.filter((thread) => [thread.title, thread.last_message_preview, targetLabel(thread.kind)]
      .some((value) => String(value || "").toLowerCase().includes(search)));
  }, [threadSearch, threads]);

  const messagesQuery = useQuery({
    queryKey: ["messaging", "messages", effectiveThreadId],
    queryFn: () => messagingApi.messages(effectiveThreadId as string),
    enabled: authenticated && surface === "messages" && Boolean(effectiveThreadId),
    refetchInterval: effectiveThreadId && surface === "messages" ? 3_000 : false,
    staleTime: 1_000,
  });

  useEffect(() => {
    const onRealtime = () => void queryClient.invalidateQueries({ queryKey: ["messaging"] });
    window.addEventListener(EVENT_NAME, onRealtime);
    return () => window.removeEventListener(EVENT_NAME, onRealtime);
  }, [queryClient]);

  useEffect(() => {
    const onOpen = (event: Event) => {
      const detail = (event as CustomEvent<OpenSurfaceDetail>).detail;
      if (!detail?.surface) return;
      setSurface(detail.surface);
      if (detail.threadId) setSelectedThreadId(detail.threadId);
      setShowSettings(false);
      setAiNotificationId(null);
      setAiResult(null);
      setAiError("");
    };
    window.addEventListener(OPEN_EVENT, onOpen);
    return () => window.removeEventListener(OPEN_EVENT, onOpen);
  }, []);

  useEffect(() => {
    if (!surface) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSurface(null);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [surface]);

  useEffect(() => {
    if (!effectiveThreadId || surface !== "messages") return;
    void messagingApi.markThreadRead(effectiveThreadId).then(() => {
      void queryClient.invalidateQueries({ queryKey: ["messaging", "unread"] });
      void queryClient.invalidateQueries({ queryKey: ["messaging", "threads"] });
    });
  }, [effectiveThreadId, messagesQuery.data?.length, queryClient, surface]);

  useEffect(() => {
    const element = messageListRef.current;
    if (element && surface === "messages") element.scrollTop = element.scrollHeight;
  }, [effectiveThreadId, messagesQuery.data?.length, surface]);

  useEffect(() => {
    if (!notificationsQuery.isSuccess) return;
    const items = notificationsQuery.data?.items || [];
    const preferences = preferencesQuery.data;
    if (!notificationsInitialized.current) {
      notificationsInitialized.current = true;
      seenNotificationIds.current = new Set(items.map((item) => item.id));
      return;
    }
    const incoming = items.filter((item) => !seenNotificationIds.current.has(item.id) && !item.read_at);
    seenNotificationIds.current = new Set(items.map((item) => item.id));
    for (const latest of incoming.slice(0, 3)) {
      const isChat = latest.kind === "CHAT_MESSAGE";
      if (preferences?.in_app_enabled !== false) {
        const priority = String(latest.priority || latest.metadata?.priority || latest.metadata?.severity || "").toUpperCase();
        pushToast({
          title: latest.title,
          message: latest.body,
          variant: ["CRITICAL", "HIGH", "URGENT"].includes(priority) ? "warning" : "info",
          sound: preferences?.sound_enabled !== false,
          actionLabel: isChat ? "Open message" : latest.action_label || "Open notifications",
          action: () => {
            if (isChat) {
              dispatchOpen({ surface: "messages", threadId: latest.entity_type === "chat_thread" ? latest.entity_id : null });
              return;
            }
            dispatchOpen({ surface: "notifications" });
          },
          dedupeKey: `portal-notification:${latest.id}`,
        });
      }
      if (!preferences?.desktop_enabled || document.visibilityState === "visible") continue;
      if ("Notification" in window && Notification.permission === "granted") {
        new Notification(latest.title, { body: latest.body, tag: latest.id });
      }
    }
  }, [notificationsQuery.data, notificationsQuery.isSuccess, preferencesQuery.data, pushToast]);

  const refreshMessaging = () => queryClient.invalidateQueries({ queryKey: ["messaging"] });
  const selectThread = (threadId: string) => {
    setSelectedThreadId(threadId);
    setMentionUserIds([]);
    setShowDirectory(false);
  };

  const openTarget = useMutation({
    mutationFn: async (target: { kind: DirectoryTab; id: string }) => {
      if (target.kind === "users") return messagingApi.openDirect(target.id);
      if (target.kind === "departments") return messagingApi.openDepartment(target.id);
      return messagingApi.openGroup(target.id);
    },
    onSuccess: (thread) => {
      selectThread(thread.id);
      void refreshMessaging();
    },
  });

  const sendMessage = useMutation({
    mutationFn: ({ threadId, body, mentions }: { threadId: string; body: string; mentions: string[] }) => messagingApi.send(
      threadId,
      body,
      `web-${Date.now()}-${crypto.randomUUID().slice(0, 12)}`,
      null,
      mentions,
    ),
    onSuccess: () => {
      setDraft("");
      setMentionUserIds([]);
      void refreshMessaging();
    },
  });

  const markNotification = useMutation({
    mutationFn: async (group: NotificationGroup) => {
      const unread = [group.latest, ...group.earlier].filter((notification) => !notification.read_at);
      await Promise.all(unread.map((notification) => messagingApi.markNotificationRead(notification.id)));
    },
    onSuccess: () => void refreshMessaging(),
  });
  const openNotification = useMutation({
    mutationFn: async (group: NotificationGroup) => {
      const notification = group.latest;
      const earlierUnread = group.earlier.filter((item) => !item.read_at);
      if (earlierUnread.length) {
        await Promise.allSettled(earlierUnread.map((item) => messagingApi.markNotificationRead(item.id)));
      }
      const updated = notification.read_at
        ? notification
        : await messagingApi.markNotificationRead(notification.id);
      return { notification, updated };
    },
    onSuccess: ({ notification, updated }) => {
      void refreshMessaging();
      const target = updated.action_url || notification.action_url;
      if (target && updated.entity_type !== "chat_thread") navigate(target);
    },
  });
  const markAll = useMutation({
    mutationFn: messagingApi.markAllNotificationsRead,
    onSuccess: () => void refreshMessaging(),
  });
  const updatePreferences = useMutation({
    mutationFn: (payload: Partial<NotificationPreferences>) => messagingApi.updatePreferences(payload),
    onSuccess: (value) => queryClient.setQueryData(["messaging", "preferences"], value),
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const body = draft.trim();
    if (!effectiveThreadId || !body || sendMessage.isPending) return;
    sendMessage.mutate({ threadId: effectiveThreadId, body, mentions: mentionUserIds });
  };

  const askAi = async (notification: PortalNotification) => {
    const manualId = typeof notification.metadata?.manual_id === "string" ? notification.metadata.manual_id : null;
    const revisionId = typeof notification.metadata?.revision_id === "string" ? notification.metadata.revision_id : null;
    if (!tenant) return;
    const request = ++aiSerial.current;
    setAiNotificationId(notification.id);
    setAiResult(null);
    setAiError("");
    setAiBusy(true);
    try {
      const result = await assistDocumentation(tenant, {
        query: `Explain the controlled-document context for this portal notification: ${notification.title}. ${notification.body}`.slice(0, 500),
        mode: "ASSIST",
        manual_id: manualId || undefined,
        revision_id: revisionId || undefined,
        limit: 6,
      });
      if (request === aiSerial.current) setAiResult(result);
    } catch (error) {
      if (request === aiSerial.current) {
        setAiError(error instanceof Error ? error.message : "Controlled-document assistance is unavailable.");
      }
    } finally {
      if (request === aiSerial.current) setAiBusy(false);
    }
  };

  if (!authenticated) return null;
  const unreadMessages = unreadQuery.data?.messages || 0;
  const unreadNotifications = unreadQuery.data?.notifications || 0;
  const preferences = preferencesQuery.data;

  return (
    <div className="messaging-hub" aria-live="polite">
      {surface === "messages" ? (
        <section className="messaging-panel messaging-panel--messages" role="dialog" aria-modal="false" aria-labelledby="portal-messages-title">
          <header className="messaging-header">
            <div>
              <strong id="portal-messages-title">Messages</strong>
              <span>{unreadMessages ? `${unreadMessages} unread` : "No unread messages"}</span>
            </div>
            <button type="button" className="messaging-icon-button" onClick={() => setSurface(null)} aria-label="Close messages"><X size={17} /></button>
          </header>

          <div className="messaging-chat-layout">
            <aside className="messaging-thread-list">
              <div className="messaging-thread-toolbar">
                <span>Conversations</span>
                <button type="button" onClick={() => setShowDirectory((value) => !value)}>New</button>
              </div>
              <label className="messaging-search">
                <Search size={14} aria-hidden="true" />
                <span className="sr-only">Search conversations</span>
                <input value={threadSearch} onChange={(event) => setThreadSearch(event.target.value)} placeholder="Search messages" />
              </label>
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
                {filteredThreads.map((thread) => (
                  <button type="button" className={`messaging-thread ${thread.id === effectiveThreadId ? "is-selected" : ""}`} key={thread.id} onClick={() => selectThread(thread.id)}>
                    <span className="messaging-avatar">{initials(thread.title)}</span>
                    <span className="messaging-thread-copy">
                      <span><strong>{thread.title || "Conversation"}</strong><time>{relativeTime(thread.last_message_at || thread.updated_at)}</time></span>
                      <span>{thread.last_message_preview || targetLabel(thread.kind)}</span>
                    </span>
                    {thread.unread_count ? <b className="messaging-badge">{badgeLabel(thread.unread_count)}</b> : null}
                  </button>
                ))}
                {!threadsQuery.isLoading && filteredThreads.length === 0 ? <p className="messaging-empty">No matching conversations.</p> : null}
              </div>
            </aside>

            <main className="messaging-conversation">
              {selectedThread ? (
                <>
                  <div className="messaging-conversation-title">
                    <div>
                      <strong>{selectedThread.title || "Conversation"}</strong>
                      <span>{targetLabel(selectedThread.kind)} · {selectedThread.members.length} member{selectedThread.members.length === 1 ? "" : "s"}</span>
                    </div>
                    <select aria-label="Conversation notification level" value={selectedThread.notification_level} onChange={(event) => void messagingApi.updateThreadNotifications(selectedThread.id, event.target.value as "ALL" | "MENTIONS" | "NONE").then(refreshMessaging)}>
                      <option value="ALL">All alerts</option>
                      <option value="MENTIONS">Mentions</option>
                      <option value="NONE">Muted</option>
                    </select>
                  </div>
                  <div className="messaging-message-list" ref={messageListRef}>
                    {(messagesQuery.data || []).map((message) => {
                      const own = message.sender_id === user?.id;
                      const sender = selectedThread.members.find((member) => member.id === message.sender_id);
                      const mentions = Array.isArray(message.metadata.mention_user_ids) ? message.metadata.mention_user_ids.map(String) : [];
                      return (
                        <article className={`messaging-message ${own ? "is-own" : ""}`} key={message.id}>
                          {!own ? <span className="messaging-avatar is-small">{initials(sender?.full_name)}</span> : null}
                          <div>
                            {!own ? <small>{sender?.full_name || "User"}</small> : null}
                            {mentions.includes(String(user?.id)) ? <small className="messaging-mentioned">Mentioned you</small> : null}
                            <p>{message.deleted_at ? "Message removed" : message.body_text}</p>
                            <time>{new Date(message.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}{message.edited_at ? " · edited" : ""}</time>
                          </div>
                        </article>
                      );
                    })}
                    {messagesQuery.isLoading ? <p className="messaging-empty">Loading conversation…</p> : null}
                  </div>
                  <form className="messaging-composer" onSubmit={submit}>
                    {mentionCandidates.length ? (
                      <div className="messaging-mentions">
                        <select aria-label="Mention a conversation member" value="" onChange={(event) => {
                          const id = event.target.value;
                          if (id) setMentionUserIds((values) => values.includes(id) ? values : [...values, id]);
                        }}>
                          <option value="">@ Mention</option>
                          {mentionCandidates.filter((member) => !mentionUserIds.includes(member.id)).map((member) => <option value={member.id} key={member.id}>{member.full_name}</option>)}
                        </select>
                        {mentionUserIds.map((id) => {
                          const member = mentionCandidates.find((candidate) => candidate.id === id);
                          return <button type="button" key={id} onClick={() => setMentionUserIds((values) => values.filter((value) => value !== id))}>@{member?.full_name || "User"} ×</button>;
                        })}
                      </div>
                    ) : null}
                    <div className="messaging-composer-row">
                      <textarea value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Write a message" rows={2} maxLength={8000} />
                      <button type="submit" disabled={!draft.trim() || sendMessage.isPending}>{sendMessage.isPending ? "Sending" : "Send"}</button>
                    </div>
                  </form>
                  {sendMessage.error ? <p className="messaging-error">{sendMessage.error.message}</p> : null}
                </>
              ) : <p className="messaging-empty is-centered">Select a conversation.</p>}
            </main>
          </div>
        </section>
      ) : null}

      {surface === "notifications" ? (
        <section className="messaging-panel messaging-panel--notifications" role="dialog" aria-modal="false" aria-labelledby="portal-notifications-title">
          <header className="messaging-header">
            <div>
              <strong id="portal-notifications-title">Notifications</strong>
              <span>{attentionCount ? `${attentionCount} need attention` : unreadNotifications ? `${unreadNotifications} unread` : "No current actions"}</span>
            </div>
            <div className="messaging-header-actions">
              <button type="button" className="messaging-icon-button" onClick={() => setShowSettings((value) => !value)} aria-label="Notification settings" aria-expanded={showSettings}><Settings size={16} /></button>
              <button type="button" className="messaging-icon-button" onClick={() => setSurface(null)} aria-label="Close notifications"><X size={17} /></button>
            </div>
          </header>

          {showSettings && preferences ? (
            <div className="messaging-settings">
              <strong>Delivery preferences</strong>
              <label><input type="checkbox" checked={preferences.in_app_enabled} onChange={(event) => updatePreferences.mutate({ in_app_enabled: event.target.checked })} /> In-app alerts</label>
              <label><input type="checkbox" checked={preferences.desktop_enabled} onChange={(event) => {
                if (event.target.checked && "Notification" in window && Notification.permission === "default") void Notification.requestPermission();
                updatePreferences.mutate({ desktop_enabled: event.target.checked });
              }} /> Desktop alerts</label>
              <label><input type="checkbox" checked={preferences.sound_enabled} onChange={(event) => updatePreferences.mutate({ sound_enabled: event.target.checked })} /> Sound</label>
              <label><input type="checkbox" checked={preferences.email_enabled} onChange={(event) => updatePreferences.mutate({ email_enabled: event.target.checked })} /> Routine operational email</label>
              <label><input type="checkbox" checked={preferences.receipt_email_enabled} onChange={(event) => updatePreferences.mutate({ receipt_email_enabled: event.target.checked })} /> Workflow receipts</label>
              <div className="messaging-settings__required"><strong>Essential and critical compliance email</strong><small>Always active and cannot be disabled.</small></div>
            </div>
          ) : null}

          <nav className="messaging-notification-views" aria-label="Notification views">
            <button type="button" className={notificationView === "for-you" ? "is-active" : ""} onClick={() => setNotificationView("for-you")}>For you <span>{attentionCount}</span></button>
            <button type="button" className={notificationView === "updates" ? "is-active" : ""} onClick={() => setNotificationView("updates")}>Updates</button>
          </nav>

          <div className="messaging-notification-controls">
            <label className="messaging-search">
              <Search size={14} aria-hidden="true" />
              <span className="sr-only">Search notifications</span>
              <input value={notificationSearch} onChange={(event) => setNotificationSearch(event.target.value)} placeholder="Search notifications" />
            </label>
            <div className="messaging-filter-chips" aria-label="Filter notifications">
              {([
                ["all", "All"],
                ["action", "Action"],
                ["due", "Due soon"],
                ["unread", "Unread"],
              ] as Array<[NotificationFilter, string]>).map(([value, label]) => (
                <button type="button" className={notificationFilter === value ? "is-active" : ""} key={value} onClick={() => setNotificationFilter(value)}>{label}</button>
              ))}
            </div>
          </div>

          <div className="messaging-notification-toolbar">
            <span>{notificationGroups.length} grouped item{notificationGroups.length === 1 ? "" : "s"}</span>
            <button type="button" onClick={() => markAll.mutate()} disabled={markAll.isPending || unreadNotifications === 0}>Mark all read</button>
          </div>
          <p className="messaging-notification-read-note">Read status only clears the unread indicator. Required actions remain active until the underlying workflow is completed.</p>

          <div className="messaging-notification-scroll">
            {notificationGroups.map((group) => {
              const notification = group.latest;
              const canAskAi = Boolean(tenant);
              const due = dueLabel(notification);
              const aiOpen = aiNotificationId === notification.id;
              const groupUnread = notificationGroupHasUnread(group);
              return (
                <article className={`messaging-notification-card ${groupUnread ? "is-unread" : ""}`} data-tone={notificationTone(notification)} key={group.key}>
                  <div className="messaging-notification-card__marker" aria-hidden="true" />
                  <div className="messaging-notification-card__body">
                    <div className="messaging-notification-card__meta">
                      <span>{notificationStateLabel(notification)}</span>
                      <time>{relativeTime(notification.created_at)}</time>
                    </div>
                    <strong>{notification.title}</strong>
                    <p>{notification.body}</p>
                    {due ? <div className="messaging-notification-card__due"><Clock3 size={13} /> {due}</div> : null}
                    <div className="messaging-notification-card__actions">
                      {notification.action_url ? (
                        <button type="button" className="is-primary" onClick={() => openNotification.mutate(group)}>{notificationActionLabel(notification)} <ExternalLink size={13} /></button>
                      ) : groupUnread ? (
                        <button type="button" onClick={() => markNotification.mutate(group)}>Mark group read</button>
                      ) : null}
                      {canAskAi ? (
                        <button type="button" onClick={() => void askAi(notification)} disabled={aiBusy && aiOpen}><Sparkles size={13} /> {aiBusy && aiOpen ? "Checking…" : "Ask AI"}</button>
                      ) : null}
                    </div>
                    {group.earlier.length ? (
                      <details className="messaging-notification-history">
                        <summary>{group.earlier.length} earlier update{group.earlier.length === 1 ? "" : "s"}</summary>
                        {group.earlier.map((item) => (
                          <div key={item.id}>
                            <span>{item.title}</span>
                            <time>{relativeTime(item.created_at)}</time>
                          </div>
                        ))}
                      </details>
                    ) : null}
                    {aiOpen ? (
                      <div className="messaging-notification-ai">
                        <div className="messaging-notification-ai__heading">
                          <span><Bot size={14} /> Controlled-document assistance</span>
                          <button type="button" onClick={() => { aiSerial.current += 1; setAiBusy(false); setAiNotificationId(null); setAiResult(null); setAiError(""); }} aria-label="Close AI assistance"><X size={14} /></button>
                        </div>
                        {aiError ? <p className="messaging-error" role="alert">{aiError}</p> : null}
                        {aiBusy ? <p>Retrieving permission-filtered controlled context…</p> : null}
                        {aiResult ? (
                          <>
                            <p>{aiResult.answer}</p>
                            {aiResult.warning ? <small>{aiResult.warning}</small> : null}
                            <div className="messaging-notification-ai__sources">
                              {aiResult.sources.slice(0, 4).map((source) => (
                                <a href={source.reader_url} key={source.id}>{source.code} · {source.heading || source.title}{source.page_number ? ` · p.${source.page_number}` : ""}</a>
                              ))}
                            </div>
                            <div className="messaging-notification-ai__authority"><CheckCircle2 size={13} /> The controlled source remains authoritative. AI assistance cannot approve, acknowledge, publish or alter records.</div>
                          </>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                </article>
              );
            })}
            {notificationsQuery.isLoading ? <p className="messaging-empty">Loading notifications…</p> : null}
            {!notificationsQuery.isLoading && notificationGroups.length === 0 ? (
              <div className="messaging-empty-state">
                {notificationView === "for-you" ? <CheckCircle2 size={22} /> : <Bell size={22} />}
                <strong>{notificationView === "for-you" ? "No actions in this view" : "No matching updates"}</strong>
                <p>{notificationView === "for-you" ? "Unread informational updates remain available under Updates." : "Adjust the search or filter to see more notifications."}</p>
              </div>
            ) : null}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function DirectoryPicker({ data, loading, activeTab, onTab, onSelect }: {
  data?: ChatDirectory;
  loading: boolean;
  activeTab: DirectoryTab;
  onTab: (value: DirectoryTab) => void;
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
        {entries.map((entry) => {
          const label = activeTab === "users"
            ? (entry as ChatDirectory["users"][number]).full_name
            : (entry as ChatDirectory["departments"][number] | ChatDirectory["groups"][number]).name;
          const detail = activeTab === "users"
            ? (entry as ChatDirectory["users"][number]).position_title
            : activeTab === "departments"
              ? (entry as ChatDirectory["departments"][number]).code
              : (entry as ChatDirectory["groups"][number]).group_type;
          return (
            <button type="button" key={entry.id} onClick={() => onSelect(entry.id)}>
              <span className="messaging-avatar is-small">{initials(label)}</span>
              <span><strong>{label}</strong><small>{detail || ""}</small></span>
            </button>
          );
        })}
        {loading ? <p className="messaging-empty">Loading directory…</p> : null}
        {!loading && entries.length === 0 ? <p className="messaging-empty">Nothing available here.</p> : null}
      </div>
    </div>
  );
}
