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

export function canAskAi(notification: PortalNotification): boolean {
  return Boolean(notification.action_url && (
    notification.metadata?.manual_id
    || notification.metadata?.revision_id
    || String(notification.entity_type || "").includes("document")
  ));
}

export function notificationAssistantUrl(notification: PortalNotification): string | null {
  if (!notification.action_url || typeof window === "undefined") return null;
  const url = new URL(notification.action_url, window.location.origin);
  url.searchParams.set("assistant", "1");
  url.searchParams.set(
    "assistant_query",
    `Explain what this notification requires, why it matters, and show the controlling authorised sources: ${notification.title}. ${notification.body}`.slice(0, 500),
  );
  return `${url.pathname}${url.search}${url.hash}`;
}
