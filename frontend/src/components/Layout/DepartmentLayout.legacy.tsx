// src/components/Layout/DepartmentLayout.tsx
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { BrandContext } from "../Brand/BrandContext";
import { BrandHeader } from "../Brand/BrandHeader";
import { BrandLogo } from "../Brand/BrandLogo";
import { BrandProvider } from "../Brand/BrandProvider";
import AppShellV2 from "../AppShell/AppShellV2";
import LiveStatusIndicator from "../realtime/LiveStatusIndicator";
import {
  Activity,
  AlertTriangle,
  Bell,
  BookOpen,
  Building2,
  CalendarClock,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  CreditCard,
  Factory,
  FileText,
  FolderCog,
  GraduationCap,
  Hammer,
  LayoutDashboard,
  Mail,
  Menu,
  MoreHorizontal,
  Package,
  PanelLeftClose,
  PanelLeftOpen,
  Send,
  Settings,
  ShieldCheck,
  UserCheck,
  Users,
  Wrench,
  type LucideIcon,
  X,
} from "lucide-react";
import { useToast } from "../feedback/ToastProvider";
import { useAnalytics } from "../../hooks/useAnalytics";
import { useTimeOfDayTheme } from "../../hooks/useTimeOfDayTheme";
import { useColorScheme } from "../../hooks/useColorScheme";
import { usePortalRuntimeMode } from "../../hooks/usePortalRuntimeMode";
import { isUiShellV2Enabled } from "../../utils/featureFlags";
import {
  getNotificationPreferences,
  NOTIFICATION_PREFS_EVENT,
  playNotificationChirp,
  pushDesktopNotification,
  type NotificationPreferences,
} from "../../services/notificationPreferences";
import { fetchSubscriptionStatus, fetchEntitlements } from "../../services/billing";
import type { BillingAccessStatus, Subscription } from "../../types/billing";
import { endSession, extendSession, getCachedUser, getContext, getTokenSecondsRemaining, markSessionActivity, onSessionEvent } from "../../services/auth";
import { fetchOverviewSummary, type OverviewSummary } from "../../services/adminOverview";
import { qmsGetNotificationSummary, qmsListNotifications, qmsMarkAllNotificationsRead, qmsMarkNotificationRead, type QMSNotificationOut, type QMSNotificationSummaryOut } from "../../services/qms";
import {
  DEPARTMENT_ITEMS,
  type DepartmentId,
  canAccessDepartment,
  getAllowedDepartments,
  getAssignedDepartment,
  isAdminUser,
  isDepartmentId,
} from "../../utils/departmentAccess";
import { BrowserPollCoordinator } from "../../services/pollCoordinator";
import { preloadRoute, scheduleWorkspaceRoutePreload } from "../../app/routePreload";
import { canViewFeature } from "../../utils/roleAccess";

type Props = {
  amoCode: string;
  activeDepartment: string;
  children: React.ReactNode;
  showPollingErrorBanner?: boolean;
};

type AdminNavId =
  | "admin-overview"
  | "admin-amos"
  | "admin-users"
  | "admin-assets"
  | "admin-billing"
  | "admin-settings"
  | "admin-email-logs"
  | "admin-email-settings";

const ADMIN_NAV_ITEMS: Array<{ id: AdminNavId; label: string }> = [
  { id: "admin-overview", label: "Overview" },
  { id: "admin-amos", label: "AMO Management" },
  { id: "admin-users", label: "User Management" },
  { id: "admin-assets", label: "AMO Assets" },
  { id: "admin-billing", label: "Billing & Usage" },
  { id: "admin-settings", label: "Usage Throttling" },
  { id: "admin-email-logs", label: "Email Logs" },
  { id: "admin-email-settings", label: "Email Server" },
];

type SidebarIconKey = string | null | undefined;

const NAV_ICON_MAP: Record<string, LucideIcon> = {
  "admin-overview": LayoutDashboard,
  "admin-amos": Building2,
  "admin-users": Users,
  "admin-assets": FolderCog,
  "admin-billing": CreditCard,
  "admin-settings": Settings,
  "admin-email-logs": Mail,
  "admin-email-settings": Send,
  planning: CalendarDays,
  production: Factory,
  maintenance: Wrench,
  "document-control": FileText,
  quality: ShieldCheck,
  reliability: Activity,
  safety: AlertTriangle,
  stores: Package,
  workshops: Hammer,
  admin: Settings,
  rostering: CalendarClock,
  manuals: BookOpen,
  training: GraduationCap,
  "my-training": UserCheck,
  qms: ShieldCheck,
  more: MoreHorizontal,
};

function iconForSidebarItem(id: SidebarIconKey, label?: string, sub = false): LucideIcon {
  if (sub) return ChevronRight;
  const normalized = `${id || ""} ${label || ""}`.toLowerCase();
  if (id && NAV_ICON_MAP[id]) return NAV_ICON_MAP[id];
  if (normalized.includes("calendar") || normalized.includes("planner") || normalized.includes("rostering")) return CalendarDays;
  if (normalized.includes("audit") || normalized.includes("quality") || normalized.includes("car")) return ShieldCheck;
  if (normalized.includes("training")) return GraduationCap;
  if (normalized.includes("document") || normalized.includes("manual")) return FileText;
  if (normalized.includes("user") || normalized.includes("person")) return Users;
  if (normalized.includes("billing")) return CreditCard;
  if (normalized.includes("settings") || normalized.includes("system")) return Settings;
  if (normalized.includes("stores") || normalized.includes("parts")) return Package;
  if (normalized.includes("reliability") || normalized.includes("ehm")) return Activity;
  return LayoutDashboard;
}

function SidebarItemBody({ id, label, sub = false }: { id?: SidebarIconKey; label: string; sub?: boolean }) {
  const Icon = iconForSidebarItem(id, label, sub);
  return (
    <>
      <span className={`sidebar__item-icon${sub ? " sidebar__item-icon--sub" : ""}`} aria-hidden="true">
        <Icon size={sub ? 13 : 17} strokeWidth={2} />
      </span>
      <span className="sidebar__item-label">{label}</span>
    </>
  );
}


const IDLE_TIMEOUT_MS = 30 * 60 * 1000;
const IDLE_WARNING_MS = 10 * 1000;
const LAYOUT_CACHE_TTL_MS = 5 * 60 * 1000;
const LAYOUT_CACHE_FAST_TTL_MS = 10 * 60 * 1000;
const LAYOUT_CACHE_PREFIX = "amo_portal_layout_cache";
const layoutMemoryCache = new Map<string, LayoutCacheEntry<unknown>>();

type LayoutCacheEntry<T> = {
  value: T;
  savedAt: number;
};

function getLayoutCacheProfile(): {
  maxAgeMs: number;
  useMemory: boolean;
} {
  if (typeof window === "undefined") {
    return { maxAgeMs: LAYOUT_CACHE_TTL_MS, useMemory: false };
  }
  const deviceMemory = (navigator as Navigator & { deviceMemory?: number }).deviceMemory ?? 4;
  const connection = (navigator as Navigator & {
    connection?: { effectiveType?: string };
  }).connection;
  const effectiveType = connection?.effectiveType;
  const isFastConnection = !effectiveType || effectiveType === "4g";
  const useMemory = deviceMemory >= 8 && isFastConnection;
  return {
    maxAgeMs: useMemory ? LAYOUT_CACHE_FAST_TTL_MS : LAYOUT_CACHE_TTL_MS,
    useMemory,
  };
}

function readLayoutCache<T>(key: string, maxAgeMs: number, useMemory: boolean): T | null {
  if (typeof window === "undefined") return null;
  if (useMemory) {
    const entry = layoutMemoryCache.get(key) as LayoutCacheEntry<T> | undefined;
    if (entry) {
      if (Date.now() - entry.savedAt <= maxAgeMs) {
        return entry.value ?? null;
      }
      layoutMemoryCache.delete(key);
    }
  }
  const raw = window.localStorage.getItem(key);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as LayoutCacheEntry<T>;
    if (!parsed?.savedAt) return null;
    if (Date.now() - parsed.savedAt > maxAgeMs) {
      window.localStorage.removeItem(key);
      return null;
    }
    return parsed.value ?? null;
  } catch {
    window.localStorage.removeItem(key);
    return null;
  }
}

function writeLayoutCache<T>(key: string, value: T, useMemory: boolean): void {
  if (typeof window === "undefined") return;
  const payload: LayoutCacheEntry<T> = { value, savedAt: Date.now() };
  if (useMemory) {
    layoutMemoryCache.set(key, payload);
  }
  window.localStorage.setItem(key, JSON.stringify(payload));
}

function clearLayoutCache(prefix: string): void {
  if (typeof window === "undefined") return;
  layoutMemoryCache.forEach((_value, key) => {
    if (key.startsWith(prefix)) {
      layoutMemoryCache.delete(key);
    }
  });
  for (let i = window.localStorage.length - 1; i >= 0; i -= 1) {
    const key = window.localStorage.key(i);
    if (key && key.startsWith(prefix)) {
      window.localStorage.removeItem(key);
    }
  }
}

function isAdminNavId(v: string): v is AdminNavId {
  return ADMIN_NAV_ITEMS.some((d) => d.id === v);
}

function getUserDisplayName(u: any): string {
  if (!u) return "User";
  return (
    u.full_name ||
    u.name ||
    u.display_name ||
    u.username ||
    u.email ||
    "User"
  );
}

function getUserInitials(u: any): string {
  const name = getUserDisplayName(u).trim();
  if (!name) return "U";
  const parts = name.split(/\s+/).filter(Boolean);
  const a = parts[0]?.[0] ?? "U";
  const b = parts.length > 1 ? parts[parts.length - 1]?.[0] ?? "" : "";
  return (a + b).toUpperCase();
}


function scheduleNonCritical(task: () => void, delayMs = 600): () => void {
  if (typeof window === "undefined") {
    task();
    return () => undefined;
  }
  const run = () => window.setTimeout(task, delayMs);
  const id = "requestIdleCallback" in window
    ? (window as Window & { requestIdleCallback: (cb: () => void, opts?: { timeout: number }) => number }).requestIdleCallback(() => task(), { timeout: delayMs + 1200 })
    : run();
  return () => {
    if ("cancelIdleCallback" in window) {
      try {
        (window as Window & { cancelIdleCallback: (id: number) => void }).cancelIdleCallback(id as number);
        return;
      } catch {
        // fall through
      }
    }
    window.clearTimeout(id as number);
  };
}

function getStoredProfileAvatar(userId?: string | null): string | null {
  if (typeof window === "undefined" || !userId) return null;
  const value = window.localStorage.getItem(`amo_portal_profile_avatar:${userId}`);
  return value && value.trim() ? value : null;
}

const DepartmentLayout: React.FC<Props> = ({
  amoCode,
  activeDepartment,
  children,
  showPollingErrorBanner = true,
}) => {
  const theme = useTimeOfDayTheme();
  const { scheme: colorScheme, toggle: toggleColorScheme } = useColorScheme();
  const [sidebarPinned, setSidebarPinned] = useState(false);
  const [sidebarDrawerOpen, setSidebarDrawerOpen] = useState(false);
  const [sidebarPinnedPreferenceStorageKey, setSidebarPinnedPreferenceStorageKey] = useState<string | null>(null);
  const [isDesktopSidebar, setIsDesktopSidebar] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [notifications, setNotifications] = useState<QMSNotificationOut[]>([]);
  const [notificationsLoading, setNotificationsLoading] = useState(false);
  const [notificationsError, setNotificationsError] = useState<string | null>(null);
  const [unreadNotifications, setUnreadNotifications] = useState(0);
  const [notificationPrefs, setNotificationPrefs] = useState<NotificationPreferences>(() => getNotificationPreferences());
  const [idleWarningOpen, setIdleWarningOpen] = useState(false);
  const [idleCountdown, setIdleCountdown] = useState(IDLE_WARNING_MS / 1000);
  const [logoutReason, setLogoutReason] = useState<"idle" | "expired" | null>(
    null
  );
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [subscriptionError, setSubscriptionError] = useState<string | null>(null);
  const [billingAccessStatus, setBillingAccessStatus] = useState<BillingAccessStatus | null>(null);
  const [subscriptionMissing, setSubscriptionMissing] = useState(false);
  const [billingGateResolved, setBillingGateResolved] = useState(true);
  const [aerodocEnabled, setAerodocEnabled] = useState(false);
  const [pollingError, setPollingError] = useState<string | null>(null);
  const [overviewSummary, setOverviewSummary] = useState<OverviewSummary | null>(null);
  const [overviewSummaryUnavailable, setOverviewSummaryUnavailable] = useState(false);
  const [trialMenuOpen, setTrialMenuOpen] = useState(false);
  const [trialChipHidden, setTrialChipHidden] = useState(false);

  const navigate = useNavigate();
  const location = useLocation();
  const { trackEvent } = useAnalytics();
  const { pushToast } = useToast();
  const uiShellV2 = isUiShellV2Enabled();

  useEffect(() => {
    if (!uiShellV2) return;
    document.body.classList.add("app-shell-v2");
    return () => {
      document.body.classList.remove("app-shell-v2");
    };
  }, [uiShellV2]);

  useEffect(() => {
    if (!uiShellV2 || typeof window === "undefined") return;
    const media = window.matchMedia("(min-width: 1025px)");
    const apply = () => setIsDesktopSidebar(media.matches);
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [uiShellV2]);

  const currentUser = getCachedUser();
  const sidebarStorageKey = `amo_sidebar_pinned:${currentUser?.id || "anon"}:${currentUser?.amo_id || amoCode}`;

  useEffect(() => {
    if (!uiShellV2 || typeof window === "undefined") return;
    const stored = window.localStorage.getItem(sidebarStorageKey);
    setSidebarPinned(stored === "1");
    setSidebarPinnedPreferenceStorageKey(sidebarStorageKey);
  }, [sidebarStorageKey, uiShellV2]);

  useEffect(() => {
    if (!uiShellV2 || typeof window === "undefined") return;
    if (sidebarPinnedPreferenceStorageKey !== sidebarStorageKey) return;
    window.localStorage.setItem(sidebarStorageKey, sidebarPinned ? "1" : "0");
    if (sidebarPinned) setSidebarDrawerOpen(false);
  }, [sidebarPinned, sidebarPinnedPreferenceStorageKey, sidebarStorageKey, uiShellV2]);
  const { isDemoMode } = usePortalRuntimeMode();
  const isSuperuser = !!currentUser?.is_superuser;
  const isTenantAdmin = isSuperuser || !!currentUser?.is_amo_admin;
  const isAdminArea = isAdminNavId(activeDepartment);
  const assignedDepartment = getAssignedDepartment(currentUser, getContext().department);
  const allowedDepartments = getAllowedDepartments(currentUser, assignedDepartment);

  // Admins/SUPERUSER can see all departments and the System Admin area.
  const canAccessAdmin = isAdminUser(currentUser);

  const visibleDepartments = useMemo(() => {
    if (isAdminArea) {
      return canAccessAdmin
        ? DEPARTMENT_ITEMS.filter((dept) => dept.id !== "admin")
        : [];
    }
    if (canAccessAdmin) return DEPARTMENT_ITEMS;

    return DEPARTMENT_ITEMS.filter((dept) =>
      allowedDepartments.includes(dept.id)
    );
  }, [canAccessAdmin, isAdminArea, allowedDepartments]);

  const primaryDepartments = useMemo(() => {
    const mainOrder = new Set<DepartmentId>(["planning", "production", "maintenance", "quality", "stores", "admin"]);
    return visibleDepartments.filter((dept) => mainOrder.has(dept.id) || dept.id === activeDepartment);
  }, [activeDepartment, visibleDepartments]);

  const overflowDepartments = useMemo(() => {
    const primaryIds = new Set(primaryDepartments.map((dept) => dept.id));
    return visibleDepartments.filter((dept) => !primaryIds.has(dept.id));
  }, [primaryDepartments, visibleDepartments]);

  const visibleAdminNav = useMemo(() => {
    if (!isAdminArea) return [];
    return ADMIN_NAV_ITEMS.filter((i) => {
      if (i.id === "admin-amos" && !isSuperuser) return false;
      if (i.id === "admin-billing" && !isTenantAdmin) return false;
      if (i.id === "admin-email-settings" && !isSuperuser) return false;
      return true;
    });
  }, [isAdminArea, isSuperuser, isTenantAdmin]);

  const rosteringLandingPath = useMemo(() => {
    const canViewDashboard = canViewFeature(currentUser, "rostering.dashboard", assignedDepartment);
    return canViewDashboard
      ? `/maintenance/${amoCode}/rostering/dashboard`
      : `/maintenance/${amoCode}/rostering/my-roster`;
  }, [amoCode, assignedDepartment, currentUser]);

  useEffect(() => {
    const departmentPaths = visibleDepartments.map((department) => {
      if (department.id === "admin") return `/maintenance/${amoCode}/admin/overview`;
      if (department.id === "production") return `/maintenance/${amoCode}/production/dashboard`;
      if (department.id === "maintenance") return `/maintenance/${amoCode}/maintenance/dashboard`;
      return `/maintenance/${amoCode}/${department.id}`;
    });
    return scheduleWorkspaceRoutePreload([
      rosteringLandingPath,
      ...departmentPaths,
      `/maintenance/${amoCode}/quality`,
      `/maintenance/${amoCode}/manuals`,
    ]);
  }, [amoCode, rosteringLandingPath, visibleDepartments]);

  useEffect(() => {
    if (!currentUser) return;
    if (isAdminArea) {
      if (!canAccessAdmin) {
        const fallback = assignedDepartment || allowedDepartments[0] || "planning";
        navigate(`/maintenance/${amoCode}/${fallback}`, { replace: true });
      }
      return;
    }

    if (!canAccessAdmin && isDepartmentId(activeDepartment)) {
      if (!allowedDepartments.includes(activeDepartment)) {
        const fallback = assignedDepartment || allowedDepartments[0] || "planning";
        navigate(`/maintenance/${amoCode}/${fallback}`, { replace: true });
      }
    }
  }, [
    activeDepartment,
    allowedDepartments,
    assignedDepartment,
    canAccessAdmin,
    currentUser,
    isAdminArea,
    navigate,
    amoCode,
  ]);

  const adminBadgeMap = useMemo(() => {
    const badges = overviewSummary?.badges || {};
    return {
      "admin-amos": badges.amos,
      "admin-users": badges.users,
      "admin-assets": badges.assets,
      "admin-billing": badges.billing,
      "admin-settings": badges.usage,
    } as Record<string, OverviewSummary["badges"][string] | undefined>;
  }, [overviewSummary?.badges]);

  const overviewSummaryDown = overviewSummary?.system.status === "down";

  useEffect(() => {
    if (typeof document === "undefined") return;
    document.body.dataset.theme = theme;
  }, [theme]);


  const openSidebarDrawer = useCallback((options?: { source?: "edge" | "kbd" | "mobile" }) => {
    if (sidebarPinned) return;
    if (import.meta.env.DEV) {
      console.debug(`[sidebar] open drawer source=${options?.source ?? "unknown"}`);
    }
    setSidebarDrawerOpen(true);
  }, [sidebarPinned]);

  const closeSidebarDrawer = useCallback(() => {
    if (!sidebarPinned) setSidebarDrawerOpen(false);
  }, [sidebarPinned]);

  const navigateWithSidebarClose = useCallback(
    (path: string, options?: { replace?: boolean; state?: unknown }) => {
      // Start the lazy route import before React Router commits the new route.
      // The import is deduplicated by the browser and Vite runtime.
      void preloadRoute(path).catch(() => undefined);
      closeSidebarDrawer();
      if (!sidebarPinned) setSidebarDrawerOpen(false);
      navigate(path, options as never);
    },
    [closeSidebarDrawer, navigate, sidebarPinned]
  );

  const handleNav = (deptId: DepartmentId) => {
    const targetPath = `/maintenance/${amoCode}/${deptId}`;
    if (
      (subscription?.is_read_only || subscriptionMissing || billingAccessStatus?.redirect_to_billing) &&
      !targetPath.includes("/billing") &&
      !targetPath.includes("/upsell")
    ) {
      navigate(`/maintenance/${amoCode}/admin/billing?lockout=1`, {
        replace: true,
        state: { from: targetPath },
      });
      return;
    }

    // Non-admins should not navigate across departments.
    if (!canAccessAdmin) {
      if (
        canAccessDepartment(currentUser, assignedDepartment, deptId) &&
        isDepartmentId(deptId)
      ) {
        navigateWithSidebarClose(targetPath);
      }
      return;
    }

    // System Admin is NOT a normal department dashboard; route is explicit.
    if (deptId === "admin") {
      navigateWithSidebarClose(`/maintenance/${amoCode}/admin/overview`);
      return;
    }

    navigateWithSidebarClose(targetPath);
  };

  const handleAdminNav = (navId: AdminNavId, overrideRoute?: string) => {
    if ((subscription?.is_read_only || subscriptionMissing || billingAccessStatus?.redirect_to_billing) && navId !== "admin-billing") {
      navigate(`/maintenance/${amoCode}/admin/billing?lockout=1`, {
        replace: true,
        state: { from: location.pathname + location.search },
      });
      return;
    }

    if (overrideRoute) {
      navigateWithSidebarClose(`/maintenance/${amoCode}${overrideRoute}`);
      return;
    }

    switch (navId) {
      case "admin-overview":
        navigateWithSidebarClose(`/maintenance/${amoCode}/admin/overview`);
        break;
      case "admin-amos":
        navigateWithSidebarClose(`/maintenance/${amoCode}/admin/amos`);
        break;
      case "admin-users":
        navigateWithSidebarClose(`/maintenance/${amoCode}/admin/users`);
        break;
      case "admin-assets":
        navigateWithSidebarClose(`/maintenance/${amoCode}/admin/amo-assets`);
        break;
      case "admin-billing":
        navigateWithSidebarClose(`/maintenance/${amoCode}/admin/billing`);
        break;
      case "admin-settings":
        navigateWithSidebarClose(`/maintenance/${amoCode}/admin/settings`);
        break;
      case "admin-email-logs":
        navigateWithSidebarClose(`/maintenance/${amoCode}/admin/email-logs`);
        break;
      case "admin-email-settings":
        navigateWithSidebarClose(`/maintenance/${amoCode}/admin/email-settings`);
        break;
      default:
        break;
    }
  };

  const resolveDeptForTraining = (): string => {
    // Prefer the current department (unless admin)
    if (isDepartmentId(activeDepartment) && activeDepartment !== "admin") {
      return activeDepartment;
    }

    if (assignedDepartment && assignedDepartment !== "admin") {
      return assignedDepartment;
    }

    // Next: first visible non-admin department
    const first = visibleDepartments.find((d) => d.id !== "admin")?.id;
    if (first) return first;

    // Last resort
    return "planning";
  };

  const gotoMyTraining = () => {
    navigateWithSidebarClose(`/maintenance/${amoCode}/training`);
  };

  const resolveLoginSlug = (): string => {
    const parts = location.pathname.split("/").filter(Boolean);
    if (parts[0] === "maintenance" && parts[1]) {
      return parts[1];
    }
    const ctx = getContext();
    return ctx.amoSlug || amoCode || ctx.amoCode || "";
  };

  const handleLogout = () => {
    endSession("manual");

    // Keep AMO context when logging out
    const code = resolveLoginSlug().trim();
    if (code) {
      navigate(`/maintenance/${code}/login`, { replace: true });
    } else {
      navigate("/login", { replace: true });
    }
  };

  const amoLabel = (amoCode || "AMO").toUpperCase();
  const shellBase = uiShellV2 ? "app-shell app-shell--v2" : "app-shell";
  const sidebarOpen = sidebarPinned || sidebarDrawerOpen;
  const shellClassName = `${shellBase}${uiShellV2 ? ` app-shell--${sidebarPinned ? "pinned" : "drawer"}${sidebarOpen ? " app-shell--drawer-open" : ""}` : ""}`;
  const isBillingRoute = useMemo(() => {
    return location.pathname.includes("/billing");
  }, [location.pathname]);

  const isUpsellRoute = useMemo(() => {
    return location.pathname.includes("/upsell");
  }, [location.pathname]);

  const isQmsTrainingRoute = useMemo(() => {
    return location.pathname.includes("/training/competence") || location.pathname.includes("/training-competence");
  }, [location.pathname]);

  const isMyTrainingRoute = useMemo(() => {
    const path = location.pathname;
    if (path.includes("/training/competence") || path.includes("/training-competence")) return false;
    return /^\/maintenance\/[^/]+\/(?:[^/]+\/)?training(?:\/|$)/.test(path);
  }, [location.pathname]);


  const isManualsRoute = useMemo(() => {
    return location.pathname.includes("/manuals");
  }, [location.pathname]);

  const isQmsRoute = useMemo(() => {
    return location.pathname.includes("/quality") || location.pathname.includes("/qms");
  }, [location.pathname]);

  const isQualityCarsRoute = useMemo(() => {
    return /\/maintenance\/[^/]+\/quality\/cars(?:\/|$)/.test(location.pathname);
  }, [location.pathname]);

  const qualityCarsContentClassName = isQualityCarsRoute
    ? "app-shell__content app-shell__content--quality-cars"
    : undefined;

  const isDocControlRoute = useMemo(() => {
    return location.pathname.startsWith("/doc-control") || location.pathname.includes("/doc-control") || location.pathname.includes("/document-control");
  }, [location.pathname]);

  useEffect(() => {
    if (!uiShellV2) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.isComposing || event.key === "Process") return;
      const target = event.target as HTMLElement | null;
      const tag = target?.tagName;
      const isTextTarget =
        !!target && (target.isContentEditable || tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT");
      const matchesOpenCombo = (event.ctrlKey || event.metaKey) && event.key === "\\";
      if (matchesOpenCombo) {
        event.preventDefault();
        openSidebarDrawer({ source: "kbd" });
        return;
      }
      if (isTextTarget && !event.ctrlKey && !event.metaKey) {
        return;
      }
      if (event.key === "Escape" && !sidebarPinned) {
        setSidebarDrawerOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [openSidebarDrawer, sidebarPinned, uiShellV2]);

  useEffect(() => {
    if (!uiShellV2 || !isDesktopSidebar || sidebarPinned) return;

    const clearCloseTimer = () => {
      if (sidebarCloseTimerRef.current) {
        window.clearTimeout(sidebarCloseTimerRef.current);
        sidebarCloseTimerRef.current = null;
      }
    };

    const openDrawer = () => {
      clearCloseTimer();
      openSidebarDrawer({ source: "edge" });
    };

    const scheduleClose = () => {
      clearCloseTimer();
      sidebarCloseTimerRef.current = window.setTimeout(() => {
        setSidebarDrawerOpen(false);
      }, 280);
    };

    const sidebarEl = sidebarRef.current;
    const hotzoneEl = sidebarHotzoneRef.current;
    sidebarEl?.addEventListener("pointerenter", openDrawer);
    sidebarEl?.addEventListener("pointerleave", scheduleClose);
    hotzoneEl?.addEventListener("pointerenter", openDrawer);
    hotzoneEl?.addEventListener("pointerleave", scheduleClose);

    return () => {
      clearCloseTimer();
      sidebarEl?.removeEventListener("pointerenter", openDrawer);
      sidebarEl?.removeEventListener("pointerleave", scheduleClose);
      hotzoneEl?.removeEventListener("pointerenter", openDrawer);
      hotzoneEl?.removeEventListener("pointerleave", scheduleClose);
    };
  }, [isDesktopSidebar, openSidebarDrawer, sidebarPinned, uiShellV2]);

  useEffect(() => {
    if (!isDesktopSidebar || sidebarPinned) return;
    setSidebarDrawerOpen(false);
  }, [isDesktopSidebar, sidebarPinned]);

  type QmsNavItem = {
    id: string;
    label: string;
    path: string;
    matchPrefixes?: string[];
    children?: Array<{ id: string; label: string; path: string; matchPrefixes?: string[] }>;
  };

  const isPathMatch = (pathname: string, path: string, prefixes?: string[]) => {
    if (pathname.startsWith(path)) return true;
    return (prefixes ?? []).some((prefix) => pathname.startsWith(prefix));
  };

  const qmsNavItems = useMemo<QmsNavItem[]>(
    () => [
      {
        id: "qms-command",
        label: "Command Centre",
        path: `/maintenance/${amoCode}/quality`,
        matchPrefixes: [`/maintenance/${amoCode}/quality/cockpit`],
      },
      {
        id: "qms-inbox",
        label: "My Quality Work",
        path: `/maintenance/${amoCode}/quality/inbox/assigned-to-me`,
        children: [
          {
            id: "qms-inbox-approvals",
            label: "Approvals",
            path: `/maintenance/${amoCode}/quality/inbox/approvals`,
          },
          {
            id: "qms-inbox-overdue",
            label: "Overdue Work",
            path: `/maintenance/${amoCode}/quality/inbox/overdue`,
          },
          {
            id: "qms-inbox-completed",
            label: "Completed Work",
            path: `/maintenance/${amoCode}/quality/inbox/completed`,
          },
        ],
      },
      {
        id: "qms-calendar",
        label: "Calendar",
        path: `/maintenance/${amoCode}/quality/calendar/list`,
        children: [
          {
            id: "qms-calendar-audits",
            label: "Audit Dates",
            path: `/maintenance/${amoCode}/quality/calendar/audits`,
          },
          {
            id: "qms-calendar-cars",
            label: "CAR Deadlines",
            path: `/maintenance/${amoCode}/quality/calendar/cars`,
          },
          {
            id: "qms-calendar-training",
            label: "Training Expiry",
            path: `/maintenance/${amoCode}/quality/calendar/training`,
          },
          {
            id: "qms-calendar-reviews",
            label: "Review Dates",
            path: `/maintenance/${amoCode}/quality/calendar/management-review`,
          },
        ],
      },
      {
        id: "qms-system",
        label: "System & Processes",
        path: `/maintenance/${amoCode}/quality/system/processes`,
        children: [
          {
            id: "qms-system-process-map",
            label: "Process Map",
            path: `/maintenance/${amoCode}/quality/system/processes`,
          },
          {
            id: "qms-system-objectives",
            label: "Objectives",
            path: `/maintenance/${amoCode}/quality/system/quality-objectives`,
          },
        ],
      },
      {
        id: "qms-documents",
        label: "Controlled Documents",
        path: `/maintenance/${amoCode}/quality/documents/library`,
        children: [
          {
            id: "qms-documents-change-requests",
            label: "Change Requests",
            path: `/maintenance/${amoCode}/quality/documents/change-requests`,
          },
          {
            id: "qms-documents-approvals",
            label: "Approval Queue",
            path: `/maintenance/${amoCode}/quality/documents/approvals`,
          },
          {
            id: "qms-documents-distribution",
            label: "Distribution",
            path: `/maintenance/${amoCode}/quality/documents/distribution`,
          },
          {
            id: "qms-documents-obsolete",
            label: "Archive / Obsolete",
            path: `/maintenance/${amoCode}/quality/documents/obsolete`,
          },
        ],
      },
      {
        id: "qms-audits",
        label: "Audits",
        path: `/maintenance/${amoCode}/quality/audits/dashboard`,
        children: [
          {
            id: "qms-audits-programme",
            label: "Programme",
            path: `/maintenance/${amoCode}/quality/audits/program`,
          },
          {
            id: "qms-audits-schedule",
            label: "Schedule",
            path: `/maintenance/${amoCode}/quality/audits/schedule`,
            matchPrefixes: [`/maintenance/${amoCode}/quality/audits/schedules/`],
          },
          {
            id: "qms-audits-checklists",
            label: "Checklists",
            path: `/maintenance/${amoCode}/quality/audits/checklists`,
          },
          {
            id: "qms-audits-reports",
            label: "Reports",
            path: `/maintenance/${amoCode}/quality/audits/reports`,
          },
        ],
      },
      {
        id: "qms-findings",
        label: "Findings",
        path: `/maintenance/${amoCode}/quality/findings/register`,
      },
      {
        id: "qms-cars",
        label: "CAR / CAPA",
        path: `/maintenance/${amoCode}/quality/cars/register`,
        children: [
          {
            id: "qms-cars-overdue",
            label: "Overdue",
            path: `/maintenance/${amoCode}/quality/cars/overdue`,
          },
          {
            id: "qms-cars-due-soon",
            label: "Due Soon",
            path: `/maintenance/${amoCode}/quality/cars/due-soon`,
          },
          {
            id: "qms-cars-review",
            label: "Quality Review",
            path: `/maintenance/${amoCode}/quality/cars/awaiting-quality-review`,
          },
          {
            id: "qms-cars-closed",
            label: "Closed",
            path: `/maintenance/${amoCode}/quality/cars/closed`,
          },
        ],
      },
      {
        id: "qms-risk",
        label: "Risk & Opportunities",
        path: `/maintenance/${amoCode}/quality/risk/register`,
        children: [
          {
            id: "qms-risk-matrix",
            label: "Risk Matrix",
            path: `/maintenance/${amoCode}/quality/risk/risk-matrix`,
          },
          {
            id: "qms-risk-treatment",
            label: "Treatment Plans",
            path: `/maintenance/${amoCode}/quality/risk/treatment-plans`,
          },
        ],
      },
      {
        id: "qms-change",
        label: "Change Control",
        path: `/maintenance/${amoCode}/quality/change-control/register`,
      },
      {
        id: "qms-training",
        label: "Training & Competence",
        path: `/maintenance/${amoCode}/training/competence/dashboard`,
        matchPrefixes: [`/maintenance/${amoCode}/training/competence`],
        children: [
          {
            id: "qms-training-matrix",
            label: "Matrix",
            path: `/maintenance/${amoCode}/training/competence/matrix`,
          },
          {
            id: "qms-training-due",
            label: "Due / Overdue",
            path: `/maintenance/${amoCode}/training/competence/overdue`,
          },
        ],
      },
      {
        id: "qms-suppliers",
        label: "Suppliers",
        path: `/maintenance/${amoCode}/quality/suppliers/approved-list`,
      },
      {
        id: "qms-equipment",
        label: "Equipment & Calibration",
        path: `/maintenance/${amoCode}/quality/equipment-calibration/register`,
      },
      {
        id: "qms-external",
        label: "External Interface",
        path: `/maintenance/${amoCode}/quality/external-interface/regulator-findings`,
      },
      {
        id: "qms-review",
        label: "Management Review",
        path: `/maintenance/${amoCode}/quality/management-review/dashboard`,
      },
      {
        id: "qms-reports",
        label: "Reports & Analytics",
        path: `/maintenance/${amoCode}/quality/reports/executive-dashboard`,
      },
      {
        id: "qms-evidence",
        label: "Evidence Vault",
        path: `/maintenance/${amoCode}/quality/evidence-vault/search`,
        matchPrefixes: [`/maintenance/${amoCode}/quality/evidence-vault/`],
      },
      {
        id: "qms-settings",
        label: "Settings",
        path: `/maintenance/${amoCode}/quality/settings/general`,
      },
      ...(aerodocEnabled
        ? [
            {
              id: "qms-aerodoc-hangar",
              label: "AeroDoc Hangar",
              path: `/maintenance/${amoCode}/quality/aerodoc/hangar`,
            },
            {
              id: "qms-aerodoc-compliance",
              label: "AeroDoc Compliance",
              path: `/maintenance/${amoCode}/quality/aerodoc/compliance`,
            },
            {
              id: "qms-aerodoc-audit",
              label: "AeroDoc Audit Mode",
              path: `/maintenance/${amoCode}/quality/aerodoc/audit-mode`,
            },
          ]
        : []),
    ],
    [amoCode, aerodocEnabled]
  );


  const docControlNavItems = useMemo<Array<{ id: string; label: string; path: string; matchPrefixes?: string[] }>>(() => {
    const basePath = activeDepartment === "document-control"
      ? `/maintenance/${amoCode}/document-control`
      : `/maintenance/${amoCode}/${activeDepartment}/doc-control`;
    return [
      { id: "dc-overview", label: "Overview", path: basePath, matchPrefixes: ["/doc-control"] },
      { id: "dc-library", label: "Controlled Library", path: `${basePath}/library`, matchPrefixes: ["/doc-control/library"] },
      { id: "dc-drafts", label: "Drafts & Approval", path: `${basePath}/drafts`, matchPrefixes: ["/doc-control/drafts"] },
      { id: "dc-change", label: "Change Proposals", path: `${basePath}/change-proposals`, matchPrefixes: ["/doc-control/change-proposals"] },
      { id: "dc-revisions", label: "Revisions & LEP", path: `${basePath}/revisions/AMO-QM-001`, matchPrefixes: ["/doc-control/revisions", "/doc-control/lep"] },
      { id: "dc-tr", label: "Temporary Revisions", path: `${basePath}/tr`, matchPrefixes: ["/doc-control/tr"] },
      { id: "dc-distribution", label: "Distribution & ACK", path: `${basePath}/distribution`, matchPrefixes: ["/doc-control/distribution"] },
      { id: "dc-archive", label: "Archive / Obsolete", path: `${basePath}/archive`, matchPrefixes: ["/doc-control/archive"] },
      { id: "dc-reviews", label: "Review Planner", path: `${basePath}/reviews`, matchPrefixes: ["/doc-control/reviews"] },
      { id: "dc-registers", label: "Registers", path: `${basePath}/registers`, matchPrefixes: ["/doc-control/registers"] },
      { id: "dc-settings", label: "Settings", path: `${basePath}/settings`, matchPrefixes: ["/doc-control/settings"] },
    ];
  }, [activeDepartment, amoCode]);

  const isReliabilityRoute = useMemo(() => {
    return location.pathname.includes("/reliability");
  }, [location.pathname]);

  const isEhmDashboardRoute = useMemo(() => {
    return location.pathname.endsWith("/ehm") || location.pathname.endsWith("/ehm/dashboard");
  }, [location.pathname]);

  const isEhmTrendsRoute = useMemo(() => {
    return location.pathname.includes("/ehm/trends");
  }, [location.pathname]);

  const isEhmUploadsRoute = useMemo(() => {
    return location.pathname.includes("/ehm/uploads");
  }, [location.pathname]);


  const lockedEventRef = useRef<string | null>(null);
  const profileRef = useRef<HTMLDivElement | null>(null);
  const notificationsRef = useRef<HTMLDivElement | null>(null);
  const previousUnreadRef = useRef(0);
  const idleWarningTimeoutRef = useRef<number | null>(null);
  const idleLogoutTimeoutRef = useRef<number | null>(null);
  const idleCountdownIntervalRef = useRef<number | null>(null);
  const lastActivityRef = useRef<number>(Date.now());
  const lastActivityUiUpdateRef = useRef<number>(0);
  const lastActivityBroadcastRef = useRef<number>(0);
  const idleWarningOpenRef = useRef(false);
  const lastSessionExtendAttemptRef = useRef<number>(0);
  const pollingInFlightRef = useRef(false);
  const trialMenuRef = useRef<HTMLDivElement | null>(null);
  const lastPollingToastRef = useRef<string | null>(null);
  const sidebarRef = useRef<HTMLElement | null>(null);
  const sidebarHotzoneRef = useRef<HTMLDivElement | null>(null);
  const sidebarCloseTimerRef = useRef<number | null>(null);

  const cacheKeyBase = useMemo(() => {
    return `${LAYOUT_CACHE_PREFIX}:${amoCode}:${currentUser?.id || "anonymous"}`;
  }, [amoCode, currentUser?.id]);

  const cacheProfile = useMemo(() => getLayoutCacheProfile(), []);

  const subscriptionCacheKey = `${cacheKeyBase}:subscription`;
  const overviewCacheKey = `${cacheKeyBase}:overview-summary`;
  const unreadCacheKey = `${cacheKeyBase}:unread-count`;
  const notificationsCacheKey = `${cacheKeyBase}:notifications`;

  const notificationPollCoordinator = useMemo(() => {
    if (!currentUser?.id) return null;
    return new BrowserPollCoordinator(`qms-notifications:${amoCode}:${currentUser.id}`);
  }, [amoCode, currentUser?.id]);

  useEffect(() => {
    if (!currentUser) {
      clearLayoutCache(`${LAYOUT_CACHE_PREFIX}:`);
    }
  }, [currentUser]);

  useEffect(() => {
    // The backend remains authoritative for subscription enforcement. Do not
    // blank the workspace while the client refreshes a cached access status.
    setBillingGateResolved(true);
  }, [currentUser]);

  useEffect(() => {
    idleWarningOpenRef.current = idleWarningOpen;
  }, [idleWarningOpen]);

  useEffect(() => {
    return onSessionEvent((detail) => {
      if (detail.type === "activity") {
        lastActivityRef.current = Date.now();
        if (idleWarningOpenRef.current) {
          resetIdleTimers();
        }
        return;
      }
      if (detail.type === "expired" || detail.type === "idle-logout" || detail.type === "manual-logout") {
        clearLayoutCache(`${LAYOUT_CACHE_PREFIX}:`);
      }
    });
  }, []);

  useEffect(() => {
    if (!currentUser) return;
    const cachedSubscription = readLayoutCache<Subscription>(
      subscriptionCacheKey,
      cacheProfile.maxAgeMs,
      cacheProfile.useMemory
    );
    if (cachedSubscription) {
      setSubscription(cachedSubscription);
      setSubscriptionMissing(false);
      setBillingAccessStatus(null);
      setSubscriptionError(null);
    }

    const cachedOverview = readLayoutCache<OverviewSummary>(
      overviewCacheKey,
      cacheProfile.maxAgeMs,
      cacheProfile.useMemory
    );
    if (cachedOverview) {
      setOverviewSummary(cachedOverview);
      setOverviewSummaryUnavailable(false);
    }

    const cachedUnread = readLayoutCache<number>(
      unreadCacheKey,
      cacheProfile.maxAgeMs,
      cacheProfile.useMemory
    );
    if (typeof cachedUnread === "number") {
      previousUnreadRef.current = cachedUnread;
      setUnreadNotifications(cachedUnread);
    }

    const cachedNotifications = readLayoutCache<QMSNotificationOut[]>(
      notificationsCacheKey,
      cacheProfile.maxAgeMs,
      cacheProfile.useMemory
    );
    if (cachedNotifications?.length) {
      setNotifications(cachedNotifications);
    }
  }, [
    cacheProfile.maxAgeMs,
    cacheProfile.useMemory,
    currentUser,
    notificationsCacheKey,
    overviewCacheKey,
    subscriptionCacheKey,
    unreadCacheKey,
  ]);

  const refreshSubscription = useCallback(async (opts?: { force?: boolean }) => {
    if (!opts?.force) {
      const cached = readLayoutCache<Subscription>(
        subscriptionCacheKey,
        cacheProfile.maxAgeMs,
        cacheProfile.useMemory
      );
      if (cached) {
        setSubscription(cached);
        setSubscriptionMissing(false);
        setBillingAccessStatus(null);
        setSubscriptionError(null);
        setBillingGateResolved(true);
        return;
      }
    }
    try {
      const result = await fetchSubscriptionStatus();
      setSubscription(result.subscription);
      setSubscriptionMissing(result.subscriptionMissing);
      setBillingAccessStatus(result.accessStatus);
      setSubscriptionError(result.accessStatus?.lock_reason || null);
      if (result.subscription) {
        writeLayoutCache(subscriptionCacheKey, result.subscription, cacheProfile.useMemory);
      }
      setBillingGateResolved(true);
    } catch (err: any) {
      setSubscription(null);
      setSubscriptionMissing(false);
      setBillingAccessStatus(null);
      setSubscriptionError(err?.message || "Unable to load subscription status.");
      setBillingGateResolved(true);
      throw err;
    }
  }, [cacheProfile.maxAgeMs, cacheProfile.useMemory, subscriptionCacheKey]);
  useEffect(() => {
    if (!currentUser || isBillingRoute || isUpsellRoute) return;
    if (currentUser.is_superuser) {
      setBillingGateResolved(true);
      setSubscriptionError(null);
      setBillingAccessStatus(null);
      return;
    }
    let active = true;
    const timeout = window.setTimeout(() => {
      if (!active || billingGateResolved) return;
      setSubscriptionError("Billing access check timed out. Retry or contact support if this continues.");
      setBillingGateResolved(true);
    }, 12000);
    refreshSubscription({ force: false })
      .catch(() => undefined)
      .finally(() => window.clearTimeout(timeout));
    return () => {
      active = false;
      window.clearTimeout(timeout);
    };
  }, [currentUser, isBillingRoute, isUpsellRoute, refreshSubscription]);


  useEffect(() => {
    let active = true;
    const cacheKey = `:aerodoc-enabled`;
    const cached = readLayoutCache<boolean>(cacheKey, cacheProfile.maxAgeMs, cacheProfile.useMemory);
    if (typeof cached === "boolean") {
      setAerodocEnabled(cached);
    }
    return scheduleNonCritical(() => {
      fetchEntitlements()
        .then((rows) => {
          if (!active) return;
          const entitlement = rows.find((row) => row.key === "aerodoc_hybrid_dms");
          const enabled = Boolean(entitlement && (entitlement.is_unlimited || (entitlement.limit ?? 0) > 0));
          setAerodocEnabled(enabled);
          writeLayoutCache(cacheKey, enabled, cacheProfile.useMemory);
        })
        .catch(() => {
          if (!active) return;
          if (cached == null) setAerodocEnabled(false);
        });
    }, 900);
  }, [cacheKeyBase, cacheProfile.maxAgeMs, cacheProfile.useMemory]);

  const refreshOverviewSummary = useCallback(async (opts?: { force?: boolean }) => {
    if (!isAdminUser(currentUser)) return;
    if (!opts?.force) {
      const cached = readLayoutCache<OverviewSummary>(
        overviewCacheKey,
        cacheProfile.maxAgeMs,
        cacheProfile.useMemory
      );
      if (cached) {
        setOverviewSummary(cached);
        setOverviewSummaryUnavailable(false);
        return;
      }
    }
    try {
      const data = await fetchOverviewSummary();
      setOverviewSummary(data);
      setOverviewSummaryUnavailable(false);
      writeLayoutCache(overviewCacheKey, data, cacheProfile.useMemory);
    } catch (err) {
      console.error("Failed to refresh overview summary", err);
      setOverviewSummary(null);
      setOverviewSummaryUnavailable(true);
    }
  }, [cacheProfile.maxAgeMs, cacheProfile.useMemory, currentUser, overviewCacheKey]);

  const applyNotificationSummary = useCallback(
    (summary: QMSNotificationSummaryOut, opts?: { notify?: boolean }) => {
      const nextUnread = Math.max(0, Number(summary.unread_count || 0));
      if (opts?.notify && nextUnread > previousUnreadRef.current) {
        const delta = nextUnread - previousUnreadRef.current;
        playNotificationChirp();
        void pushDesktopNotification("New Quality notifications", `${delta} new item(s) received.`);
      }
      previousUnreadRef.current = nextUnread;
      setUnreadNotifications(nextUnread);
      writeLayoutCache(unreadCacheKey, nextUnread, cacheProfile.useMemory);
    },
    [cacheProfile.useMemory, unreadCacheKey]
  );

  const refreshUnreadNotifications = useCallback(async (opts?: { force?: boolean; notify?: boolean; broadcast?: boolean }) => {
    if (!currentUser) return;
    if (billingAccessStatus?.redirect_to_billing) {
      previousUnreadRef.current = 0;
      setUnreadNotifications(0);
      return;
    }
    if (!opts?.force) {
      const cached = readLayoutCache<number>(
        unreadCacheKey,
        cacheProfile.maxAgeMs,
        cacheProfile.useMemory
      );
      if (typeof cached === "number") {
        previousUnreadRef.current = cached;
        setUnreadNotifications(cached);
        return;
      }
    }

    const summary = await qmsGetNotificationSummary();
    applyNotificationSummary(summary, { notify: opts?.notify });
    if (opts?.broadcast && notificationPollCoordinator?.isLeader()) {
      notificationPollCoordinator.broadcast("qms-notification-summary", summary);
    }
  }, [applyNotificationSummary, billingAccessStatus?.redirect_to_billing, cacheProfile.maxAgeMs, cacheProfile.useMemory, currentUser, notificationPollCoordinator, unreadCacheKey]);

  const handlePollingFailure = useCallback(
    (err: unknown) => {
      const message = err instanceof Error ? err.message : "Unable to refresh data.";
      setPollingError(message);
    },
    []
  );

  const runPolling = useCallback(
    async (reason: "manual") => {
      if (!currentUser) return;
      if (pollingInFlightRef.current) return;
      pollingInFlightRef.current = true;
      try {
        const force = reason === "manual";
        await refreshSubscription({ force });
        if (billingAccessStatus?.redirect_to_billing) {
          setPollingError(null);
          return;
        }
        await refreshUnreadNotifications({ force });
        await refreshOverviewSummary({ force });
        setPollingError(null);
      } catch (err: unknown) {
        handlePollingFailure(err);
      } finally {
        pollingInFlightRef.current = false;
      }
    },
    [
      currentUser,
      handlePollingFailure,
      refreshSubscription,
      refreshUnreadNotifications,
      refreshOverviewSummary,
      billingAccessStatus?.redirect_to_billing,
    ]
  );

  const refreshNotifications = useCallback(
    async (opts?: { preserveVisibleItems?: boolean }) => {
      if (!currentUser) return;
      const preserveVisibleItems = opts?.preserveVisibleItems ?? true;
      const hasVisibleItems = notifications.length > 0;
      if (!(preserveVisibleItems && hasVisibleItems)) {
        setNotificationsLoading(true);
      }
      setNotificationsError(null);
      try {
        const data = await qmsListNotifications({ include_read: true, limit: 20 });
        const unreadCount = data.filter((n) => !n.read_at).length;
        const summary: QMSNotificationSummaryOut = {
          unread_count: unreadCount,
          latest_created_at: data[0]?.created_at ?? null,
        };
        setNotifications(data);
        writeLayoutCache(notificationsCacheKey, data, cacheProfile.useMemory);
        applyNotificationSummary(summary);
        notificationPollCoordinator?.broadcast("qms-notification-summary", summary);
      } catch (err: any) {
        setNotificationsError(err?.message || "Failed to load notifications.");
        handlePollingFailure(err);
      } finally {
        setNotificationsLoading(false);
      }
    },
    [applyNotificationSummary, cacheProfile.useMemory, currentUser, handlePollingFailure, notificationPollCoordinator, notifications.length, notificationsCacheKey]
  );

  const markAllNotificationsRead = useCallback(async () => {
    if (!notifications.some((note) => !note.read_at)) return;
    try {
      await qmsMarkAllNotificationsRead();
      await refreshNotifications({ preserveVisibleItems: true });
      pushToast({
        title: "Notifications cleared",
        message: "All visible unread notifications have been marked as read.",
        variant: "success",
      });
    } catch (err: any) {
      setNotificationsError(err?.message || "Failed to mark notifications as read.");
    }
  }, [notifications, pushToast, refreshNotifications]);



  const getNotificationActionUrl = useCallback((note: QMSNotificationOut): string => {
    const stored = (note.action_url || "").trim();
    if (stored) return stored;
    const match = note.message.match(/https?:\/\/[^\s)]+|\/car-invite\?[^\s)]+/i);
    return match?.[0]?.trim() ?? "";
  }, []);

  const normaliseNotificationActionUrl = useCallback((rawUrl: string): string => {
    const actionUrl = rawUrl.trim();
    if (!actionUrl) return "";
    if (!/^https?:\/\//i.test(actionUrl)) return actionUrl;
    try {
      const target = new URL(actionUrl);
      if (["localhost", "127.0.0.1", "0.0.0.0"].includes(target.hostname) && window.location.hostname) {
        target.protocol = window.location.protocol;
        target.host = window.location.host;
      }
      return target.toString();
    } catch {
      return actionUrl;
    }
  }, []);

  const openNotificationAction = useCallback(
    async (note: QMSNotificationOut) => {
      const actionUrl = normaliseNotificationActionUrl(getNotificationActionUrl(note));
      if (!actionUrl) return;
      try {
        if (!note.read_at) {
          await qmsMarkNotificationRead(note.id);
        }
      } catch {
        // Navigation is more important than blocking the user on a transient read-state failure.
      }
      setNotificationsOpen(false);
      void refreshNotifications({ preserveVisibleItems: true });

      if (/^https?:\/\//i.test(actionUrl)) {
        try {
          const target = new URL(actionUrl);
          if (target.origin === window.location.origin) {
            navigate(`${target.pathname}${target.search}${target.hash}`);
          } else {
            window.location.assign(actionUrl);
          }
        } catch {
          window.location.assign(actionUrl);
        }
        return;
      }

      navigate(actionUrl.startsWith("/") ? actionUrl : `/${actionUrl}`);
    },
    [getNotificationActionUrl, navigate, normaliseNotificationActionUrl, refreshNotifications]
  );

  const markNotificationReadOnly = useCallback(
    async (note: QMSNotificationOut) => {
      if (note.read_at) return;
      await qmsMarkNotificationRead(note.id);
      await refreshNotifications({ preserveVisibleItems: true });
    },
    [refreshNotifications]
  );

  useEffect(() => {
    if (!notificationPollCoordinator) return;
    return notificationPollCoordinator.start((message) => {
      if (message.type === "qms-notification-summary") {
        applyNotificationSummary(message.payload as QMSNotificationSummaryOut);
      }
    });
  }, [applyNotificationSummary, notificationPollCoordinator]);

  useEffect(() => {
    const handlePrefsChange = () => {
      setNotificationPrefs(getNotificationPreferences());
    };
    window.addEventListener(NOTIFICATION_PREFS_EVENT, handlePrefsChange);
    return () => window.removeEventListener(NOTIFICATION_PREFS_EVENT, handlePrefsChange);
  }, []);

  useEffect(() => {
    if (!currentUser) return;
    const tick = () => {
      if (typeof document !== "undefined" && document.hidden) return;
      if (notificationPollCoordinator && !notificationPollCoordinator.isLeader()) return;
      void refreshUnreadNotifications({ force: true, notify: true, broadcast: true });
    };
    const intervalMs = Math.max(notificationPrefs.pollIntervalSeconds * 1000, 45_000);
    const warmupId = window.setTimeout(tick, 4000);
    const id = window.setInterval(tick, intervalMs);
    return () => {
      window.clearTimeout(warmupId);
      window.clearInterval(id);
    };
  }, [currentUser, notificationPollCoordinator, notificationPrefs.pollIntervalSeconds, refreshUnreadNotifications]);

  useEffect(() => {
    if (notificationsOpen) {
      void refreshNotifications({ preserveVisibleItems: true });
    }
  }, [notificationsOpen, refreshNotifications]);

  useEffect(() => {
    if (!notificationsOpen) return;

    const onDown = (e: MouseEvent) => {
      const el = notificationsRef.current;
      if (!el) return;
      if (e.target instanceof Node && !el.contains(e.target)) {
        setNotificationsOpen(false);
      }
    };

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setNotificationsOpen(false);
    };

    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [notificationsOpen]);

  useEffect(() => {
    if (!profileOpen) return;

    const onDown = (e: MouseEvent) => {
      const el = profileRef.current;
      if (!el) return;
      if (e.target instanceof Node && !el.contains(e.target)) {
        setProfileOpen(false);
      }
    };

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setProfileOpen(false);
    };

    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [profileOpen]);

  const clearIdleTimers = () => {
    if (idleWarningTimeoutRef.current) {
      window.clearTimeout(idleWarningTimeoutRef.current);
      idleWarningTimeoutRef.current = null;
    }
    if (idleLogoutTimeoutRef.current) {
      window.clearTimeout(idleLogoutTimeoutRef.current);
      idleLogoutTimeoutRef.current = null;
    }
    if (idleCountdownIntervalRef.current) {
      window.clearInterval(idleCountdownIntervalRef.current);
      idleCountdownIntervalRef.current = null;
    }
  };

  const scheduleIdleTimers = () => {
    clearIdleTimers();
    if (!currentUser || logoutReason) return;

    const warningDelay = Math.max(IDLE_TIMEOUT_MS - IDLE_WARNING_MS, 0);

    idleWarningTimeoutRef.current = window.setTimeout(() => {
      setIdleWarningOpen(true);
      setIdleCountdown(IDLE_WARNING_MS / 1000);
    }, warningDelay);

    idleLogoutTimeoutRef.current = window.setTimeout(() => {
      const elapsed = Date.now() - lastActivityRef.current;
      // Do not log out from a stale timer while the user has been active.
      // This protects long training/Quality workflows where a route transition or API
      // save may reset activity after the original timeout was scheduled.
      if (elapsed < IDLE_TIMEOUT_MS || (typeof document !== "undefined" && !document.hidden && elapsed < IDLE_TIMEOUT_MS + IDLE_WARNING_MS)) {
        scheduleIdleTimers();
        return;
      }
      endSession("idle");
      setIdleWarningOpen(false);
      setLogoutReason("idle");
    }, IDLE_TIMEOUT_MS);
  };

  const resetIdleTimers = () => {
    if (!currentUser || logoutReason) return;
    setIdleWarningOpen(false);
    setIdleCountdown(IDLE_WARNING_MS / 1000);
    scheduleIdleTimers();
  };

  useEffect(() => {
    if (!currentUser) return;
    resetIdleTimers();
  }, [currentUser, location.pathname, location.search]);

  useEffect(() => {
    if (!currentUser) return;
    scheduleIdleTimers();

    const activityEvents: string[] = [
      "mousemove",
      "mousedown",
      "mouseup",
      "keydown",
      "click",
      "scroll",
      "wheel",
      "touchstart",
      "touchmove",
      "pointerdown",
      "pointermove",
      "focus",
      "resize",
      "selectionchange",
    ];

    const maybeExtendActiveSession = (reason: string) => {
      const remaining = getTokenSecondsRemaining();
      if (remaining == null || remaining > 5 * 60) return;
      const now = Date.now();
      if (now - lastSessionExtendAttemptRef.current < 60_000) return;
      if (typeof document !== "undefined" && document.hidden) return;
      lastSessionExtendAttemptRef.current = now;
      void extendSession(reason).catch(() => undefined);
    };

    const handleActivity = (event?: Event) => {
      if (logoutReason) return;
      const now = Date.now();
      lastActivityRef.current = now;
      const reason = event?.type || "interaction";
      if (now - lastActivityBroadcastRef.current > 10_000) {
        lastActivityBroadcastRef.current = now;
        markSessionActivity(reason);
      }
      if (idleWarningOpenRef.current || now - lastActivityUiUpdateRef.current > 5_000) {
        lastActivityUiUpdateRef.current = now;
        setIdleWarningOpen(false);
        setIdleCountdown(IDLE_WARNING_MS / 1000);
        scheduleIdleTimers();
      }
      maybeExtendActiveSession(reason);
    };

    activityEvents.forEach((evt) =>
      window.addEventListener(evt, handleActivity, { passive: true, capture: true })
    );
    document.addEventListener("scroll", handleActivity, { passive: true, capture: true });

    const handleVisibility = () => {
      if (!document.hidden) {
        handleActivity(new Event("visibility"));
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);

    return () => {
      activityEvents.forEach((evt) =>
        window.removeEventListener(evt, handleActivity, { capture: true } as EventListenerOptions)
      );
      document.removeEventListener("scroll", handleActivity, { capture: true } as EventListenerOptions);
      document.removeEventListener("visibilitychange", handleVisibility);
      clearIdleTimers();
    };
  }, [currentUser, logoutReason]);

  useEffect(() => {
    if (!currentUser || logoutReason) return;
    const timer = window.setInterval(() => {
      const now = Date.now();
      const activeRecently = now - lastActivityRef.current < 90_000;
      if (!activeRecently || document.hidden) return;
      const remaining = getTokenSecondsRemaining();
      if (remaining != null && remaining <= 5 * 60) {
        if (now - lastSessionExtendAttemptRef.current >= 60_000) {
          lastSessionExtendAttemptRef.current = now;
          void extendSession("active-portal-use").catch(() => undefined);
        }
      }
    }, 30_000);
    return () => window.clearInterval(timer);
  }, [currentUser, logoutReason]);

  useEffect(() => {
    if (!idleWarningOpen) return;

    idleCountdownIntervalRef.current = window.setInterval(() => {
      setIdleCountdown((prev) => {
        if (prev <= 1) {
          const intervalId = idleCountdownIntervalRef.current;
          if (intervalId) {
            window.clearInterval(intervalId);
            idleCountdownIntervalRef.current = null;
          }
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      if (idleCountdownIntervalRef.current) {
        window.clearInterval(idleCountdownIntervalRef.current);
        idleCountdownIntervalRef.current = null;
      }
    };
  }, [idleWarningOpen]);

  useEffect(() => {
    const unsubscribe = onSessionEvent((detail) => {
      if (detail.type !== "expired") return;
      clearIdleTimers();
      setIdleWarningOpen(false);
      setLogoutReason("expired");
    });
    return unsubscribe;
  }, []);

  useEffect(() => {
    if (typeof document === "undefined") return;
    const shouldBlur = idleWarningOpen || !!logoutReason;
    document.body.classList.toggle("session-timeout-active", shouldBlur);
  }, [idleWarningOpen, logoutReason]);

  useEffect(() => {
    const shouldRedirect = !!subscription?.is_read_only || subscriptionMissing || !!billingAccessStatus?.redirect_to_billing;
    if (!shouldRedirect) return;
    if (isBillingRoute || isUpsellRoute) return;

    const key = `${location.pathname}${location.search}`;
    if (lockedEventRef.current !== key) {
      lockedEventRef.current = key;
      trackEvent("ACCESS_BLOCKED", {
        path: location.pathname,
        query: location.search || undefined,
        amo_code: amoCode,
        reason: billingAccessStatus?.access_state || (subscriptionMissing ? "no_subscription" : "read_only_subscription"),
      });
    }

    navigate(`/maintenance/${amoCode}/admin/billing?lockout=1`, {
      replace: true,
      state: { from: location.pathname + location.search },
    });
  }, [
    subscription?.is_read_only,
    subscriptionMissing,
    billingAccessStatus?.redirect_to_billing,
    billingAccessStatus?.access_state,
    isBillingRoute,
    isUpsellRoute,
    amoCode,
    location.pathname,
    location.search,
    navigate,
    trackEvent,
  ]);

  const holdProtectedContent =
    !!currentUser &&
    !isBillingRoute &&
    !isUpsellRoute &&
    !billingGateResolved;

  const protectedContent = holdProtectedContent ? (
    <div className="card" style={{ minHeight: 220 }}>
      <div className="card-header">
        <div>
          <h3 style={{ margin: "4px 0" }}>Checking access</h3>
          <p className="text-muted" style={{ margin: 0 }}>
            {subscriptionError || "Verifying billing, subscription, and workspace access before loading this module."}
          </p>
          {subscriptionError ? (
            <button className="btn btn-primary" type="button" onClick={() => { setBillingGateResolved(false); void refreshSubscription({ force: true }); }}>Retry access check</button>
          ) : null}
        </div>
      </div>
    </div>
  ) : (
    <>{children}</>
  );

  const deptLabel =
    ADMIN_NAV_ITEMS.find((d) => d.id === (activeDepartment as AdminNavId))
      ?.label ||
    DEPARTMENT_ITEMS.find((d) => d.id === (activeDepartment as any))?.label ||
    (activeDepartment || "Department");

  const userName = getUserDisplayName(currentUser);
  const userInitials = getUserInitials(currentUser);
  const userAvatarUrl = getStoredProfileAvatar(currentUser?.id);
  const currentYear = new Date().getFullYear();
  const returnPath = location.pathname + location.search;
  const formattedCountdown = new Date(idleCountdown * 1000)
    .toISOString()
    .substring(14, 19);
  const formatCountdown = (iso?: string | null): string | null => {
    if (!iso) return null;
    const target = new Date(iso).getTime();
    const now = Date.now();
    const diff = target - now;
    if (diff <= 0) return "0d";
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    if (days > 0) return `${days}d ${hours}h`;
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
  };
  const trialCountdown = formatCountdown(subscription?.trial_ends_at || null);
  const graceCountdown = formatCountdown(subscription?.trial_grace_expires_at || null);
  const isTrialing = subscription?.status === "TRIALING";
  const isExpired = subscription?.status === "EXPIRED";
  const isReadOnly = !!subscription?.is_read_only;
  const trialHideKey = `ui_shell_trial_hide:${amoCode}:${currentUser?.id ?? "anon"}`;
  const trialSessionKey = `ui_shell_trial_hide_session:${amoCode}:${currentUser?.id ?? "anon"}`;

  useEffect(() => {
    if (!uiShellV2) return;
    const hideUntil = window.localStorage.getItem(trialHideKey);
    const hideUntilValue = hideUntil ? Number(hideUntil) : 0;
    const sessionHidden = window.sessionStorage.getItem(trialSessionKey) === "1";
    const shouldHide = sessionHidden || (hideUntilValue > 0 && hideUntilValue > Date.now());
    setTrialChipHidden(shouldHide);
  }, [trialHideKey, trialSessionKey, uiShellV2]);

  useEffect(() => {
    if (!uiShellV2) return;
    if (!pollingError) {
      lastPollingToastRef.current = null;
      return;
    }
    if (lastPollingToastRef.current === pollingError) return;
    lastPollingToastRef.current = pollingError;
    pushToast({
      title: "Sync issue",
      message: pollingError,
      variant: "error",
    });
  }, [pollingError, pushToast, uiShellV2]);

  useEffect(() => {
    if (!trialMenuOpen) return;
    const handleClick = (event: MouseEvent) => {
      if (!trialMenuRef.current?.contains(event.target as Node)) {
        setTrialMenuOpen(false);
      }
    };
    window.addEventListener("click", handleClick);
    return () => window.removeEventListener("click", handleClick);
  }, [trialMenuOpen]);

  const handleStaySignedIn = () => {
    lastActivityRef.current = Date.now();
    void extendSession("stay-signed-in").catch(() => undefined);
    resetIdleTimers();
  };

  const handleIdleLogout = () => {
    endSession("idle");
    clearIdleTimers();
    setIdleWarningOpen(false);
    setLogoutReason("idle");
  };

  const handleResumeLogin = () => {
    const code = resolveLoginSlug().trim();
    const target = code ? `/maintenance/${code}/login` : "/login";
    navigate(target, { replace: true, state: { from: returnPath } });
  };

  const handlePollingRetry = () => {
    setPollingError(null);
    runPolling("manual");
  };

  return (
    <BrandProvider
      nameOverride={amoLabel}
      preferStoredName={isAdminArea && isSuperuser}
      logoSource={isAdminArea && isSuperuser ? "platform" : "amo"}
    >
      <BrandContext.Consumer>
        {(brand) => {
          const sidebarContent = (
            <>
              <div className="sidebar__header">
                <BrandHeader variant="sidebar" />

                {uiShellV2 && !isDesktopSidebar ? (
                  <button
                    type="button"
                    className="sidebar__close-btn"
                    aria-label="Close navigation drawer"
                    onClick={() => setSidebarDrawerOpen(false)}
                  >
                    <X size={16} aria-hidden="true" />
                  </button>
                ) : null}

                {uiShellV2 && isDesktopSidebar && (
                  <button
                    type="button"
                    className="sidebar__pin-btn"
                    onClick={() => setSidebarPinned((prev) => !prev)}
                    aria-label={sidebarPinned ? "Collapse navigation" : "Expand navigation"}
                    title={sidebarPinned ? "Collapse navigation" : "Expand navigation"}
                  >
                    {sidebarPinned ? <PanelLeftClose size={17} aria-hidden="true" /> : <PanelLeftOpen size={17} aria-hidden="true" />}
                  </button>
                )}
              </div>

              <nav id="app-shell-sidebar-nav" className="sidebar__nav">
                {visibleAdminNav.map((nav) => {
                  const isActive = nav.id === activeDepartment;
                  const badge = adminBadgeMap[nav.id];
                  const badgeUnavailable =
                    overviewSummaryUnavailable || overviewSummaryDown || badge?.available === false;
                  const hasCount =
                    !!badge?.available && !badgeUnavailable && (badge?.count ?? 0) > 0;
                  const showBadge = hasCount || badgeUnavailable;
                  const badgeSeverity = badge?.severity || "info";
                  const badgeRoute = hasCount || badgeUnavailable ? badge?.route : undefined;
                  return (
                    <button
                      key={nav.id}
                      type="button"
                      onClick={() => handleAdminNav(nav.id, badgeRoute)}
                      className={
                        "sidebar__item" + (isActive ? " sidebar__item--active" : "")
                      }
                    >
                      <SidebarItemBody id={nav.id} label={nav.label} />
                      {nav.id !== "admin-overview" && showBadge && (
                        <span
                          className={`sidebar__badge sidebar__badge--${badgeSeverity} ${
                            hasCount ? "sidebar__badge--count" : "sidebar__badge--dot"
                          }`}
                        >
                          {hasCount ? badge?.count : ""}
                        </span>
                      )}
                    </button>
                  );
                })}

                {primaryDepartments.map((dept) => {
                  const isActive = dept.id === activeDepartment;
                  return (
                    <button
                      key={dept.id}
                      type="button"
                      onClick={() => handleNav(dept.id)}
                      className={
                        "sidebar__item" + (isActive ? " sidebar__item--active" : "")
                      }
                    >
                      <SidebarItemBody id={dept.id} label={dept.label} />
                    </button>
                  );
                })}

                {overflowDepartments.length > 0 && (
                  <details className="sidebar__more" open={overflowDepartments.some((dept) => dept.id === activeDepartment)}>
                    <summary className="sidebar__item sidebar__item--more">
                      <SidebarItemBody id="more" label="More" />
                    </summary>
                    <div className="sidebar__more-list">
                      {overflowDepartments.map((dept) => {
                        const isActive = dept.id === activeDepartment;
                        return (
                          <button
                            key={dept.id}
                            type="button"
                            onClick={() => handleNav(dept.id)}
                            className={"sidebar__item sidebar__item--sub" + (isActive ? " sidebar__item--active" : "")}
                            title={dept.label}
                          >
                            <SidebarItemBody id={dept.id} label={dept.label} sub />
                          </button>
                        );
                      })}
                    </div>
                  </details>
                )}

                {((!isAdminArea && visibleDepartments.length > 0) ||
                  (isAdminArea && visibleDepartments.length > 0)) && (
                  <div className="sidebar__divider" />
                )}

                {!isAdminArea && activeDepartment === "planning" && (
                  <div className="sidebar__qms-nav" aria-label="Planning modules">
                    <div className="sidebar__group-title">Planning module routes</div>
                    {[
                      { id: "pl-dash", label: "Planning Dashboard", path: `/maintenance/${amoCode}/planning/dashboard` },
                      { id: "pl-util", label: "Utilisation Monitoring", path: `/maintenance/${amoCode}/planning/utilisation-monitoring` },
                      { id: "pl-forecast", label: "Forecast / Due List", path: `/maintenance/${amoCode}/planning/forecast-due-list` },
                      { id: "pl-amp", label: "AMP", path: `/maintenance/${amoCode}/planning/amp` },
                      { id: "pl-task", label: "Task Library", path: `/maintenance/${amoCode}/planning/task-library` },
                      { id: "pl-adsb", label: "AD/SB/EO Control", path: `/maintenance/${amoCode}/planning/ad-sb-eo-control` },
                      { id: "pl-wp", label: "Work Packages", path: `/maintenance/${amoCode}/planning/work-packages` },
                      { id: "pl-wo", label: "Work Orders", path: `/maintenance/${amoCode}/planning/work-orders` },
                      { id: "pl-def", label: "Deferments", path: `/maintenance/${amoCode}/planning/deferments` },
                      { id: "pl-nr", label: "Non-Routine Review", path: `/maintenance/${amoCode}/planning/non-routine-review` },
                      { id: "pl-watch", label: "Watchlists", path: `/maintenance/${amoCode}/planning/watchlists` },
                      { id: "pl-pub", label: "Publication Review", path: `/maintenance/${amoCode}/planning/publication-review` },
                      { id: "pl-ca", label: "Compliance Actions", path: `/maintenance/${amoCode}/planning/compliance-actions` },
                    ].map((item) => {
                      const active = location.pathname === item.path;
                      return (
                        <button key={item.id} type="button" onClick={() => navigateWithSidebarClose(item.path)} className={"sidebar__item sidebar__item--sub" + (active ? " sidebar__item--active" : "") }>
                          <SidebarItemBody id={item.id} label={item.label} />
                        </button>
                      );
                    })}
                  </div>
                )}

                {!isAdminArea && activeDepartment === "maintenance" && (
                  <div className="sidebar__qms-nav" aria-label="Maintenance modules">
                    <div className="sidebar__group-title">Maintenance module routes</div>
                    {[
                      { id: "m-dash", label: "Maintenance Dashboard", path: `/maintenance/${amoCode}/maintenance/dashboard` },
                      { id: "m-wo", label: "Work Orders", path: `/maintenance/${amoCode}/maintenance/work-orders` },
                      { id: "m-wp", label: "Work Packages", path: `/maintenance/${amoCode}/maintenance/work-packages` },
                      { id: "m-def", label: "Defects", path: `/maintenance/${amoCode}/maintenance/defects` },
                      { id: "m-nr", label: "Non-Routines", path: `/maintenance/${amoCode}/maintenance/non-routines` },
                      { id: "m-ins", label: "Inspections", path: `/maintenance/${amoCode}/maintenance/inspections` },
                      { id: "m-parts", label: "Parts / Tools", path: `/maintenance/${amoCode}/maintenance/parts-tools` },
                      { id: "m-close", label: "Closeout", path: `/maintenance/${amoCode}/maintenance/closeout` },
                      { id: "m-reports", label: "Reports", path: `/maintenance/${amoCode}/maintenance/reports` },
                      { id: "m-settings", label: "Settings", path: `/maintenance/${amoCode}/maintenance/settings` },
                    ].map((item) => {
                      const active = location.pathname === item.path;
                      return (
                        <button key={item.id} type="button" onClick={() => navigateWithSidebarClose(item.path)} className={"sidebar__item sidebar__item--sub" + (active ? " sidebar__item--active" : "") }>
                          <SidebarItemBody id={item.id} label={item.label} />
                        </button>
                      );
                    })}
                  </div>
                )}

                {!isAdminArea && activeDepartment === "production" && (
                  <div className="sidebar__qms-nav" aria-label="Production modules">
                    <div className="sidebar__group-title">Production module routes</div>
                    {[
                      { id: "p-dash", label: "Production Dashboard", path: `/maintenance/${amoCode}/production/dashboard` },
                      { id: "p-board", label: "Control Board", path: `/maintenance/${amoCode}/production/control-board` },
                      { id: "p-exec", label: "Work Order Execution", path: `/maintenance/${amoCode}/production/work-order-execution` },
                      { id: "p-find", label: "Findings / Non-Routines", path: `/maintenance/${amoCode}/production/findings` },
                      { id: "p-mat", label: "Materials / Parts", path: `/maintenance/${amoCode}/production/materials` },
                      { id: "p-ri", label: "Review / Inspection", path: `/maintenance/${amoCode}/production/review-inspection` },
                      { id: "p-release", label: "Release Preparation", path: `/maintenance/${amoCode}/production/release-prep` },
                      { id: "p-comp", label: "Production Compliance Items", path: `/maintenance/${amoCode}/production/compliance-items` },
                      { id: "p-workspace", label: "Fleet Workspace", path: `/maintenance/${amoCode}/production/workspace` },
                    ].map((item) => {
                      const active = location.pathname === item.path;
                      return (
                        <button key={item.id} type="button" onClick={() => navigateWithSidebarClose(item.path)} className={"sidebar__item sidebar__item--sub" + (active ? " sidebar__item--active" : "") }>
                          <SidebarItemBody id={item.id} label={item.label} />
                        </button>
                      );
                    })}
                  </div>
                )}

                {!isAdminArea && activeDepartment === "production" && (
                  <div className="sidebar__qms-nav" aria-label="Technical records modules">
                    <div className="sidebar__group-title">Technical Records</div>
                    {[
                      { id: "tr-dash", label: "Records Dashboard", path: `/maintenance/${amoCode}/production/records` },
                      { id: "tr-aircraft", label: "Aircraft Records", path: `/maintenance/${amoCode}/production/records/aircraft` },
                      { id: "tr-logbooks", label: "Logbooks", path: `/maintenance/${amoCode}/production/records/logbooks` },
                      { id: "tr-deferrals", label: "Deferrals", path: `/maintenance/${amoCode}/production/records/deferrals` },
                      { id: "tr-maint", label: "Maintenance Records", path: `/maintenance/${amoCode}/production/records/maintenance-records` },
                      { id: "tr-airworthiness", label: "Airworthiness", path: `/maintenance/${amoCode}/production/records/airworthiness` },
                      { id: "tr-llp", label: "LLP / Components", path: `/maintenance/${amoCode}/production/records/llp` },
                      { id: "tr-recon", label: "Reconciliation", path: `/maintenance/${amoCode}/production/records/reconciliation` },
                      { id: "tr-trace", label: "Traceability", path: `/maintenance/${amoCode}/production/records/traceability` },
                      { id: "tr-packs", label: "Packs", path: `/maintenance/${amoCode}/production/records/packs` },
                      { id: "tr-settings", label: "Record Settings", path: `/maintenance/${amoCode}/production/records/settings` },
                    ].map((item) => {
                      const active = location.pathname === item.path || location.pathname.startsWith(`${item.path}/`);
                      return (
                        <button key={item.id} type="button" onClick={() => navigateWithSidebarClose(item.path)} className={"sidebar__item sidebar__item--sub" + (active ? " sidebar__item--active" : "") }>
                          <SidebarItemBody id={item.id} label={item.label} />
                        </button>
                      );
                    })}
                  </div>
                )}

                {!isAdminArea && (
                  <button
                    type="button"
                    onClick={() => navigateWithSidebarClose(rosteringLandingPath)}
                    className={
                      "sidebar__item" + (location.pathname.includes("/rostering") ? " sidebar__item--active" : "")
                    }
                    aria-label="Duty Rostering"
                    title="Duty Rostering"
                  >
                    <SidebarItemBody id="rostering" label="Duty Rostering" />
                  </button>
                )}


                {!isAdminArea && (
                  <button
                    type="button"
                    onClick={() =>
                      navigateWithSidebarClose(`/maintenance/${amoCode}/manuals`)
                    }
                    className={
                      "sidebar__item" + (isManualsRoute ? " sidebar__item--active" : "")
                    }
                    aria-label="Manuals"
                    title="Manuals"
                  >
                    <SidebarItemBody id="manuals" label="Manuals" />
                  </button>
                )}


                {!isAdminArea && activeDepartment !== "quality" && (
                  <button
                    type="button"
                    onClick={() => navigateWithSidebarClose(`/maintenance/${amoCode}/training/competence/dashboard`)}
                    className={
                      "sidebar__item" + (isQmsTrainingRoute ? " sidebar__item--active" : "")
                    }
                    aria-label="Training & Competence"
                    title="Training & Competence"
                  >
                    <SidebarItemBody id="training" label="Training & Competence" />
                  </button>
                )}

                {!isAdminArea && (
                  <button
                    type="button"
                    onClick={gotoMyTraining}
                    className={
                      "sidebar__item" + (isMyTrainingRoute ? " sidebar__item--active" : "")
                    }
                    aria-label="My Training"
                    title="My Training"
                  >
                    <SidebarItemBody id="my-training" label="My Training" />
                  </button>
                )}

                {!isAdminArea && activeDepartment === "quality" && (
                  <>
                    <button
                      type="button"
                      onClick={() => navigateWithSidebarClose(`/maintenance/${amoCode}/quality`)}
                      className={
                        "sidebar__item" +
                        (location.pathname === `/maintenance/${amoCode}/quality` || location.pathname === `/maintenance/${amoCode}/quality/`
                          ? " sidebar__item--active"
                          : (isQmsRoute || isDocControlRoute)
                            ? " sidebar__item--trail"
                            : "")
                      }
                      aria-label="Quality Management"
                      title="Quality Management"
                    >
                      <SidebarItemBody id="qms" label="Quality Command Centre" />
                    </button>
                    {(isQmsRoute || isDocControlRoute) && (
                      <div className="sidebar__qms-nav" aria-label="Quality modules">
                        {qmsNavItems.map((item) => {
                          const childActive = item.children?.some((child) => isPathMatch(location.pathname, child.path, child.matchPrefixes)) ?? false;
                          const branchActive = childActive || isPathMatch(location.pathname, item.path, item.matchPrefixes);
                          const selfExactActive = location.pathname === item.path || location.pathname === `${item.path}/`;
                          const itemClass = "sidebar__item" + (selfExactActive && !childActive ? " sidebar__item--active" : branchActive ? " sidebar__item--trail" : "");
                          return (
                              <div key={item.id} className="sidebar__qms-node">
                                <button
                                  type="button"
                                  onClick={() => navigateWithSidebarClose(item.path)}
                                  className={itemClass}
                                >
                                  <SidebarItemBody id={item.id} label={item.label} />
                                </button>
                                {branchActive && item.children?.length ? (
                                  <div className="sidebar__qms-subnav" aria-label={`${item.label} subpages`}>
                                    {item.children.map((child) => {
                                      const childActiveNow = isPathMatch(location.pathname, child.path, child.matchPrefixes);
                                      return (
                                        <button
                                          key={child.id}
                                          type="button"
                                          onClick={() => navigateWithSidebarClose(child.path)}
                                          className={
                                            "sidebar__item sidebar__item--sub" +
                                            (childActiveNow ? " sidebar__item--active" : "")
                                          }
                                        >
                                          <SidebarItemBody id={child.id} label={child.label} sub />
                                        </button>
                                      );
                                    })}
                                  </div>
                                ) : null}
                              </div>
                            );
                        })}
                      </div>
                    )}
                  </>
                )}

                {!isAdminArea && activeDepartment === "document-control" && (
                  <>
                    <button
                      type="button"
                      onClick={() => navigateWithSidebarClose(`/maintenance/${amoCode}/document-control`)}
                      className={"sidebar__item" + (isDocControlRoute ? " sidebar__item--active" : "")}
                      aria-label="Document Control workspace"
                      title="Document Control workspace"
                    >
                      <SidebarItemBody id="document-control" label="Document Control" />
                    </button>
                    <div className="sidebar__qms-nav" aria-label="Document Control pages">
                      {docControlNavItems.map((item) => {
                        const isActive = isPathMatch(location.pathname, item.path, item.matchPrefixes);
                        return (
                          <button
                            key={item.id}
                            type="button"
                            onClick={() => navigateWithSidebarClose(item.path)}
                            className={"sidebar__item sidebar__item--sub" + (isActive ? " sidebar__item--active" : "")}
                          >
                            <SidebarItemBody id={item.id} label={item.label} />
                          </button>
                        );
                      })}
                    </div>
                  </>
                )}

                {!isAdminArea && activeDepartment === "reliability" && (
                  <>
                    <button
                      type="button"
                      onClick={() => navigateWithSidebarClose(`/maintenance/${amoCode}/reliability`)}
                      className={
                        "sidebar__item" +
                        (isReliabilityRoute ? " sidebar__item--active" : "")
                      }
                      aria-label="Reliability Reports"
                      title="Reliability Reports"
                    >
                      <SidebarItemBody id="reliability" label="Reliability Reports" />
                    </button>
                    <button
                      type="button"
                      onClick={() => navigateWithSidebarClose(`/maintenance/${amoCode}/ehm/dashboard`)}
                      className={
                        "sidebar__item" +
                        (isEhmDashboardRoute ? " sidebar__item--active" : "")
                      }
                      aria-label="Engine Health Monitoring dashboard"
                      title="Engine Health Monitoring dashboard"
                    >
                      <SidebarItemBody id="reliability" label="EHM Dashboard" />
                    </button>
                    <button
                      type="button"
                      onClick={() => navigateWithSidebarClose(`/maintenance/${amoCode}/ehm/trends`)}
                      className={
                        "sidebar__item" + (isEhmTrendsRoute ? " sidebar__item--active" : "")
                      }
                      aria-label="Engine Health Monitoring trends"
                      title="Engine Health Monitoring trends"
                    >
                      <SidebarItemBody id="reliability" label="EHM Trends" />
                    </button>
                    <button
                      type="button"
                      onClick={() => navigateWithSidebarClose(`/maintenance/${amoCode}/ehm/uploads`)}
                      className={
                        "sidebar__item" + (isEhmUploadsRoute ? " sidebar__item--active" : "")
                      }
                      aria-label="Engine Health Monitoring uploads"
                      title="Engine Health Monitoring uploads"
                    >
                      <SidebarItemBody id="reliability" label="EHM Uploads" />
                    </button>
                  </>
                )}
              </nav>
            </>
          );

          const sidebar = <aside ref={sidebarRef} className="app-shell__sidebar" role={!isDesktopSidebar ? "dialog" : undefined} aria-modal={!isDesktopSidebar ? true : undefined} aria-label="Application navigation drawer">{sidebarContent}</aside>;
          const isMobileTopbar = uiShellV2 && !isDesktopSidebar;

          const header = (
            <header className={`app-shell__topbar${isMobileTopbar ? " app-shell__topbar--mobile" : ""}`}>
              {isMobileTopbar ? (
                <>
                  <button
                    type="button"
                    className="sidebar-mobile-toggle"
                    onClick={() => (sidebarDrawerOpen ? setSidebarDrawerOpen(false) : openSidebarDrawer({ source: "mobile" }))}
                    aria-label="Open navigation drawer"
                    aria-expanded={sidebarDrawerOpen}
                    aria-controls="app-shell-sidebar-nav"
                  >
                    <Menu size={18} aria-hidden="true" />
                  </button>
                  <div className="app-shell__topbar-mobile-brand" aria-label="Tenant logo">
                    <BrandLogo size={20} />
                  </div>
                  <div className="app-shell__topbar-mobile-right">
                    <LiveStatusIndicator compact />
                  </div>
                </>
              ) : (
                <>
                  <div className="app-shell__topbar-title">
                    <BrandHeader variant="topbar" />
                    <div className="app-shell__topbar-context">
                      <div className="app-shell__topbar-heading">{deptLabel}</div>
                      <div className="app-shell__topbar-subtitle">{amoLabel}</div>
                    </div>
                  </div>
                  <div className="app-shell__topbar-actions">
                    {uiShellV2 && <LiveStatusIndicator />}
                    {uiShellV2 && isDemoMode && (
                      <span className="app-shell__flight-chip app-shell__flight-chip--demo">
                        DEMO
                      </span>
                    )}
                    <div ref={notificationsRef} className="notification-menu">
                      <button
                        type="button"
                        className="notification-bell notification-bell--plain"
                        onClick={() => setNotificationsOpen((v) => !v)}
                        aria-expanded={notificationsOpen}
                        aria-label={`Notifications${unreadNotifications ? ` (${unreadNotifications} unread)` : ""}`}
                      >
                        {unreadNotifications > 0 ? <span className="notification-bell__badge">{unreadNotifications > 99 ? "99+" : unreadNotifications}</span> : null}
                        <Bell size={18} aria-hidden="true" />
                      </button>
                      {notificationsOpen && (
                        <div className="notification-panel" role="menu">
                          <div className="notification-panel__header">
                            <strong>Notifications</strong>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                              <button
                                type="button"
                                className="notification-panel__dismiss"
                                onClick={() => void refreshNotifications({ preserveVisibleItems: true })}
                              >
                                Refresh
                              </button>
                              {notifications.some((note) => !note.read_at) ? (
                                <button type="button" className="notification-panel__dismiss" onClick={() => void markAllNotificationsRead()}>
                                  Mark all read
                                </button>
                              ) : null}
                              <button type="button" className="notification-panel__dismiss" onClick={() => setNotificationsOpen(false)}>
                                Close
                              </button>
                            </div>
                          </div>
                          {notificationsLoading && !notifications.length ? <div className="notification-panel__state">Loading…</div> : null}
                          {notificationsLoading && notifications.length ? <div className="notification-panel__state">Refreshing…</div> : null}
                          {notificationsError ? <div className="notification-panel__state notification-panel__state--error">{notificationsError}</div> : null}
                          {!notificationsLoading && !notificationsError && !notifications.length ? (
                            <div className="notification-panel__state">No recent notifications.</div>
                          ) : null}
                          {!notificationsError && notifications.length ? (
                            <div className="notification-panel__list">
                              {notifications.slice(0, 12).map((note) => {
                                const actionUrl = normaliseNotificationActionUrl(getNotificationActionUrl(note));
                                return (
                                  <article
                                    key={note.id}
                                    className={`notification-item${note.read_at ? "" : " notification-item--unread"}${actionUrl ? " notification-item--actionable" : ""}`}
                                  >
                                    <button
                                      type="button"
                                      className="notification-item__body"
                                      onClick={() => actionUrl ? void openNotificationAction(note) : undefined}
                                      disabled={!actionUrl}
                                      aria-label={actionUrl ? `Open notification action: ${note.message}` : undefined}
                                    >
                                      <span className="notification-item__title">{note.message}</span>
                                      <span className="notification-item__timestamp">{new Date(note.created_at).toLocaleString()}</span>
                                    </button>
                                    <div className="notification-item__meta">
                                      {actionUrl ? (
                                        <button
                                          type="button"
                                          className="notification-item__action notification-item__action--primary"
                                          onClick={() => void openNotificationAction(note)}
                                        >
                                          {note.action_label || "Open"}
                                        </button>
                                      ) : null}
                                      {!note.read_at ? (
                                        <button
                                          type="button"
                                          className="notification-item__action"
                                          onClick={() => void markNotificationReadOnly(note)}
                                        >
                                          Mark read
                                        </button>
                                      ) : <span>Read</span>}
                                    </div>
                                  </article>
                                );
                              })}
                            </div>
                          ) : null}
                        </div>
                      )}
                    </div>
                    <div ref={profileRef} className="profile-menu">
                      <button type="button" onClick={() => setProfileOpen((v) => !v)} className="profile-menu__trigger" aria-expanded={profileOpen}>
                        <span className="profile-menu__avatar">{userAvatarUrl ? <img src={userAvatarUrl} alt={userName} className="profile-menu__avatar-image" /> : userInitials}</span>
                        <span className="profile-menu__meta"><span className="profile-menu__name">{userName}</span></span>
                      </button>
                      {profileOpen && (
                        <div role="menu" className="profile-drawer">
                          <button
                            type="button"
                            role="menuitem"
                            className="profile-drawer__item"
                            onClick={() => {
                              setProfileOpen(false);
                              navigate(`/maintenance/${amoCode}/profile`);
                            }}
                          >
                            View profile
                          </button>
                          <button type="button" role="menuitem" className="profile-drawer__item" onClick={() => { setProfileOpen(false); toggleColorScheme(); }}>
                            Toggle theme ({colorScheme})
                          </button>
                          <button type="button" role="menuitem" className="profile-drawer__item profile-drawer__item--danger" onClick={() => { setProfileOpen(false); handleLogout(); }}>
                            Sign out
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                </>
              )}
            </header>
          );

          const sessionOverlay = (idleWarningOpen || logoutReason) && (
            <div className="session-timeout-overlay" role="dialog" aria-live="polite">
              <div className="session-timeout-card">
                {idleWarningOpen && !logoutReason && (
                  <>
                    <h2>Inactivity warning</h2>
                    <p>
                      You will be logged out in{" "}
                      <strong>{formattedCountdown}</strong> due to inactivity.
                    </p>
                    <p>Please click below to stay signed in.</p>
                    <div className="session-timeout-actions">
                      <button className="btn btn-secondary" onClick={handleIdleLogout}>
                        Log out now
                      </button>
                      <button className="btn btn-primary" onClick={handleStaySignedIn}>
                        Stay signed in
                      </button>
                    </div>
                  </>
                )}

                {logoutReason && (
                  <>
                    <h2>Session ended</h2>
                    <p>
                      {logoutReason === "idle"
                        ? "You have been logged out due to inactivity."
                        : "Your session has expired. Please log in again."}
                    </p>
                    <div className="session-timeout-actions">
                      <button className="btn btn-primary" onClick={handleResumeLogin}>
                        Log in
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
          );

          if (!uiShellV2) {
            return (
              <div className={shellClassName}>
                {sidebar}
                <main className="app-shell__main">
                  {header}

                  {showPollingErrorBanner && pollingError && (
                    <div
                      className="info-banner info-banner--warning"
                      role="status"
                      style={{ margin: "12px 0" }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          gap: 12,
                        }}
                      >
                        <span>{pollingError}</span>
                        <button
                          type="button"
                          className="secondary-chip-btn"
                          onClick={handlePollingRetry}
                        >
                          Retry refresh
                        </button>
                      </div>
                    </div>
                  )}

                  {isTrialing && subscription?.trial_ends_at && !trialChipHidden && (
                    <div className="info-banner info-banner--soft" style={{ margin: "12px 16px 0" }}>
                      <div>
                        <strong>Trial in progress</strong>
                        <p className="text-muted" style={{ margin: 0 }}>
                          {trialCountdown ? `Ends in ${trialCountdown}.` : "Trial ending soon."}{" "}
                          Convert to paid to avoid any grace or lockout.
                        </p>
                      </div>
                      <div className="page-section__actions">
                        <button
                          className="btn btn-primary"
                          onClick={() => navigate(`/maintenance/${amoCode}/admin/billing`)}
                        >
                          Convert to paid
                        </button>
                        <button
                          className="btn btn-secondary"
                          onClick={() => navigate(`/maintenance/${amoCode}/upsell`)}
                        >
                          View plans
                        </button>
                      </div>
                    </div>
                  )}

                  {isExpired && (
                    <div
                      className={`card ${isReadOnly ? "card--error" : "card--warning"}`}
                      style={{ margin: "12px 16px 0" }}
                    >
                      <div className="card-header">
                        <div>
                          <h3 style={{ margin: "4px 0" }}>
                            {isReadOnly ? "Trial locked" : "Trial expired"}
                          </h3>
                          <p className="text-muted" style={{ margin: 0 }}>
                            {isReadOnly
                              ? "Grace ended; workspace is read-only until a paid plan starts."
                              : graceCountdown
                              ? `Grace expires in ${graceCountdown}.`
                              : "Grace period is in effect. Add a payment method to keep access."}
                          </p>
                          {subscriptionError && (
                            <p className="text-muted" style={{ margin: 0 }}>
                              {subscriptionError}
                            </p>
                          )}
                        </div>
                        <div className="page-section__actions">
                          <button
                            className="btn btn-primary"
                            onClick={() => navigate(`/maintenance/${amoCode}/admin/billing`)}
                          >
                            Go to billing
                          </button>
                          <button
                            className="btn btn-secondary"
                            onClick={() => navigate(`/maintenance/${amoCode}/upsell`)}
                          >
                            See plans
                          </button>
                        </div>
                      </div>
                    </div>
                  )}

                  <div className={`app-shell__main-inner${isQualityCarsRoute ? " app-shell__main-inner--quality-cars" : ""}`}>{protectedContent}</div>

                  <footer className="app-shell__footer">
                    <span>© {currentYear} {brand.name}.</span>
                    <span>{brand.tagline || "All rights reserved."}</span>
                  </footer>
                </main>
                {sessionOverlay}
              </div>
            );
          }

          return (
            <>
              {uiShellV2 && isDesktopSidebar && !sidebarPinned && (
                <div ref={sidebarHotzoneRef} className="app-shell__edge-hotzone" aria-hidden="true" />
              )}
              {uiShellV2 && !isDesktopSidebar && !sidebarPinned && sidebarDrawerOpen && (
                <button
                  type="button"
                  className="app-shell__mobile-scrim"
                  aria-label="Close navigation menu"
                  onClick={() => setSidebarDrawerOpen(false)}
                />
              )}
              <AppShellV2
                className={shellClassName}
                sidebar={sidebar}
                header={header}
                contentClassName={qualityCarsContentClassName}
                focusMode={false}
              >
                {isExpired && (
                  <div className={`card ${isReadOnly ? "card--error" : "card--warning"}`}>
                    <div className="card-header">
                      <div>
                        <h3 style={{ margin: "4px 0" }}>
                          {isReadOnly ? "Trial locked" : "Trial expired"}
                        </h3>
                        <p className="text-muted" style={{ margin: 0 }}>
                          {isReadOnly
                            ? "Grace ended; workspace is read-only until a paid plan starts."
                            : graceCountdown
                            ? `Grace expires in ${graceCountdown}.`
                            : "Grace period is in effect. Add a payment method to keep access."}
                        </p>
                        {subscriptionError && (
                          <p className="text-muted" style={{ margin: 0 }}>
                            {subscriptionError}
                          </p>
                        )}
                      </div>
                      <div className="page-section__actions">
                        <button
                          className="btn btn-primary"
                          onClick={() => navigate(`/maintenance/${amoCode}/admin/billing`)}
                        >
                          Go to billing
                        </button>
                        <button
                          className="btn btn-secondary"
                          onClick={() => navigate(`/maintenance/${amoCode}/upsell`)}
                        >
                          See plans
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {protectedContent}

                <footer className="app-shell__footer">
                  <span>© {currentYear} {brand.name}.</span>
                  <span>{brand.tagline || "All rights reserved."}</span>
                </footer>
              </AppShellV2>
              {sessionOverlay}
            </>
          );
        }}
      </BrandContext.Consumer>
    </BrandProvider>
  );
};

export default DepartmentLayout;
