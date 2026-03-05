export const unreadCountFromNotifications = (items) => (items || []).filter((item) => !item.read_at && !item.dismissed_at).length;

export const sortNotificationsNewest = (items) => [...(items || [])].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

export const resolveNotificationLinkPath = (item, fallback = "/") => item?.link_path || fallback;
