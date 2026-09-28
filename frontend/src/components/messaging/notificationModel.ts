import type {
  PortalNotification,
  PortalNotificationBusinessState,
  PortalNotificationCategory,
  PortalNotificationPriority,
} from "../../services/messaging";

export type NotificationView = "for-you" | "updates";
export type NotificationFilter = "all" | "action" | "due" | "unread";

export type NotificationGroup = {
  key: string;
  latest: PortalNotification;
  earlier: PortalNotification[];
};

const ACTION_STATES = new Set<PortalNotificationBusinessState>([
  "ACTION_REQUIRED",
  "DUE_SOON",
  "OVERDUE",
]);

function metadataText(notification: PortalNotification, key: string): string | null {
  const value = notification.metadata?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function metadataBoolean(notification: PortalNotification, key: string): boolean | null {
  const value = notification.metadata?.[key];
  return typeof value === "boolean" ? value : null;
}

export function notificationCategory(notification: PortalNotification): PortalNotificationCategory {
  const value = String(notification.category || metadataText(notification, "category") || "").toUpperCase();
  if (value === "ACTION" || value === "WARNING" || value === "INFORMATION" || value === "UPDATE") return value;
  return notificationRequiresAction(notification) ? "ACTION" : "UPDATE";
}

export function notificationPriority(notification: PortalNotification): PortalNotificationPriority {
  const value = String(notification.priority || metadataText(notification, "priority") || "NORMAL").toUpperCase();
  if (value === "CRITICAL" || value === "HIGH" || value === "LOW" || value === "NORMAL") return value;
  return "NORMAL";
}

export function notificationBusinessState(notification: PortalNotification): PortalNotificationBusinessState {
  const value = String(notification.business_state || metadataText(notification, "business_state") || "").toUpperCase();
  if (
    value === "ACTION_REQUIRED"
    || value === "DUE_SOON"
    || value === "OVERDUE"
    || value === "COMPLETED"
    || value === "INFORMATION"
    || value === "UPDATE"
  ) return value;
  return notificationRequiresAction(notification) ? "ACTION_REQUIRED" : "UPDATE";
}

export function notificationRequiresAction(notification: PortalNotification): boolean {
  if (typeof notification.requires_action === "boolean") return notification.requires_action;
  const fromMetadata = metadataBoolean(notification, "requires_action");
  if (fromMetadata !== null) return fromMetadata;
  const state = String(notification.business_state || metadataText(notification, "business_state") || "").toUpperCase();
  return state === "ACTION_REQUIRED" || state === "DUE_SOON" || state === "OVERDUE";
}

export function notificationDueAt(notification: PortalNotification): string | null {
  return notification.due_at || metadataText(notification, "due_at");
}

export function notificationModule(notification: PortalNotification): string {
  return String(notification.module || metadataText(notification, "module") || "PORTAL").toUpperCase();
}

export function notificationActionLabel(notification: PortalNotification): string {
  return notification.action_label || metadataText(notification, "action_label") || (notificationRequiresAction(notification) ? "Review" : "Open");
}

export function notificationGroupKey(notification: PortalNotification): string {
  return notification.group_key
    || metadataText(notification, "group_key")
    || (notification.entity_type && notification.entity_id ? `${notification.entity_type}:${notification.entity_id}` : notification.id);
}

export function notificationNeedsAttention(notification: PortalNotification): boolean {
  return notificationRequiresAction(notification) || ACTION_STATES.has(notificationBusinessState(notification));
}

export function notificationIsDueSoon(notification: PortalNotification, now = Date.now(), horizonDays = 14): boolean {
  const dueAt = notificationDueAt(notification);
  if (!dueAt) return false;
  const due = new Date(dueAt).getTime();
  if (!Number.isFinite(due)) return false;
  return due <= now + horizonDays * 86_400_000;
}

export function notificationMatches(
  notification: PortalNotification,
  view: NotificationView,
  filter: NotificationFilter,
): boolean {
  const attention = notificationNeedsAttention(notification);
  if (view === "for-you" && !attention) return false;
  if (view === "updates" && attention) return false;
  if (filter === "action" && !attention) return false;
  if (filter === "due" && !notificationIsDueSoon(notification)) return false;
  if (filter === "unread" && notification.read_at) return false;
  return true;
}

export function groupNotifications(notifications: PortalNotification[]): NotificationGroup[] {
  const buckets = new Map<string, PortalNotification[]>();
  for (const notification of notifications) {
    const key = notificationGroupKey(notification);
    const bucket = buckets.get(key);
    if (bucket) bucket.push(notification);
    else buckets.set(key, [notification]);
  }

  return [...buckets.entries()]
    .map(([key, values]) => {
      values.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
      return { key, latest: values[0], earlier: values.slice(1) };
    })
    .sort((a, b) => new Date(b.latest.created_at).getTime() - new Date(a.latest.created_at).getTime());
}

export function notificationTone(notification: PortalNotification): "critical" | "warning" | "action" | "info" {
  const priority = notificationPriority(notification);
  const state = notificationBusinessState(notification);
  if (priority === "CRITICAL" || state === "OVERDUE") return "critical";
  if (priority === "HIGH" || notificationCategory(notification) === "WARNING") return "warning";
  if (notificationNeedsAttention(notification)) return "action";
  return "info";
}
