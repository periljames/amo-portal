export declare function unreadCountFromNotifications(items: Array<{ read_at?: string | null; dismissed_at?: string | null }> | null | undefined): number;
export declare function sortNotificationsNewest<T extends { created_at: string }>(items: T[] | null | undefined): T[];
export declare function resolveNotificationLinkPath(item: { link_path?: string | null } | null | undefined, fallback?: string): string;
