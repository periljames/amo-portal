import type { PortalNotification } from "../../services/messaging";

export type NotificationFilter = "all" | "action" | "due" | "unread";

function metadataString(notification: PortalNotification, key: string): string {
  const value = notification.metadata?.[key];
  return typeof value === "string" ? value : "";
}

export function notificationRequiresAction(notification: PortalNotification): boolean {
  if (typeof notification.metadata?.requires_action === "boolean") return notification.metadata.requires_action;
  const text = `${notification.title} ${notification.body}`.toLowerCase();
  return /(acknowledg|approval|required|respond|review|overdue|expires|expiry|invitation|assigned)/.test(text);
}

export function notificationDueAt(notification: PortalNotification): Date | null {
  const raw = metadataString(notification, "due_at") || metadataString(notification, "due_date");
  if (!raw) return null;
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function notificationModule(notification: PortalNotification): string {
  return metadataString(notification, "module") || notification.entity_type?.split("_")[0]?.toUpperCase() || "PORTAL";
}

export function notificationPriority(notification: PortalNotification): string {
  return (metadataString(notification, "priority") || metadataString(notification, "severity") || "NORMAL").toUpperCase();
}

export function notificationActionLabel(notification: PortalNotification): string {
  const explicit = metadataString(notification, "action_label");
  if (explicit) return explicit;
  if (notification.kind === "DOCUMENT_WORKFLOW") return "Review document";
  if (notificationRequiresAction(notification)) return "Review";
  return notification.action_url ? "Open" : "View";
}

export function notificationGroupKey(notification: PortalNotification): string {
  return metadataString(notification, "group_key") || (notification.entity_type && notification.entity_id
    ? `${notification.entity_type}:${notification.entity_id}`
    : notification.id);
}

function assistantHostUrl(notification: PortalNotification): URL | null {
  if (!notification.action_url) return null;
  let source: URL;
  try {
    source = new URL(notification.action_url, "https://amo-portal.invalid");
  } catch {
    return null;
  }

  if (/\/publications\/[^/]+\/rev\/[^/]+\/read\/?$/i.test(source.pathname)) {
    return source;
  }

  const manualId = metadataString(notification, "manual_id");
  const marker = "/document-control/";
  const markerIndex = source.pathname.indexOf(marker);
  if (!manualId || markerIndex < 0) return null;

  const prefix = source.pathname.slice(0, markerIndex);
  source.pathname = `${prefix}/document-control/library/${encodeURIComponent(manualId)}`;
  source.search = "";
  source.hash = "";
  return source;
}

export function canAskAi(notification: PortalNotification): boolean {
  return assistantHostUrl(notification) !== null;
}

export function notificationAssistantUrl(notification: PortalNotification): string | null {
  const url = assistantHostUrl(notification);
  if (!url) return null;
  url.searchParams.set("assistant", "1");
  url.searchParams.set(
    "assistant_query",
    `Explain what this notification requires, why it matters, and show the controlling authorised sources: ${notification.title}. ${notification.body}`.slice(0, 500),
  );
  return `${url.pathname}${url.search}${url.hash}`;
}
