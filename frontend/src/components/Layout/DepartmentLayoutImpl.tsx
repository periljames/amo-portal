import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  BarChart3,
  Bell,
  BookOpen,
  CalendarDays,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  Clock3,
  CreditCard,
  Factory,
  FileText,
  Gauge,
  GraduationCap,
  Home,
  LogOut,
  Mail,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Pin,
  PinOff,
  Search,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Star,
  User,
  Users,
  Warehouse,
  Wrench,
  X,
  type LucideIcon,
} from "lucide-react";

import {
  buildPortalNavigation,
  flattenPortalNavigation,
  isPortalPathActive,
  type PortalNavGroup,
  type PortalNavIcon,
  type PortalNavItem,
} from "../../app/portalRouteManifest";
import {
  endSession,
  getCachedUser,
} from "../../services/auth";
import {
  activateAdminProfile,
  deactivateAdminProfile,
  fetchAdminProfileState,
  onAdminProfileChange,
  readCachedAdminProfileState,
  type AdminProfileState,
} from "../../services/adminProfileMode";
import { useColorScheme } from "../../hooks/useColorScheme";
import { usePortalAppearance } from "../../hooks/usePortalAppearance";
import { BrandContext } from "../Brand/BrandContext";
import { BrandLogo } from "../Brand/BrandLogo";
import { BrandProvider } from "../Brand/BrandProvider";
import LiveStatusIndicator from "../realtime/LiveStatusIndicator";

type Props = {
  amoCode: string;
  activeDepartment: string;
  children: React.ReactNode;
  showPollingErrorBanner?: boolean;
};

type AccentId = "tenant" | "blue" | "teal" | "green" | "amber" | "violet";

type NavBranchProps = {
  item: PortalNavItem;
  pathname: string;
  level: 0 | 1 | 2;
  expanded: Set<string>;
  favourites: Set<string>;
  onToggle: (id: string) => void;
  onFavourite: (item: PortalNavItem) => void;
  onNavigate: (path: string) => void;
};

const SIDEBAR_MIN = 236;
const SIDEBAR_MAX = 420;
const SIDEBAR_DEFAULT = 284;
const MAX_RECENT = 7;

const ICONS: Record<PortalNavIcon, LucideIcon> = {
  home: Home,
  work: ClipboardCheck,
  calendar: CalendarDays,
  planning: CalendarDays,
  production: Factory,
  maintenance: Wrench,
  quality: ShieldCheck,
  documents: FileText,
  records: BookOpen,
  rostering: CalendarDays,
  training: GraduationCap,
  reliability: Gauge,
  stores: Warehouse,
  safety: ShieldCheck,
  workshops: Wrench,
  settings: Settings,
  users: Users,
  billing: CreditCard,
  mail: Mail,
  chart: BarChart3,
};

const ACCENTS: Array<{ id: AccentId; label: string }> = [
  { id: "tenant", label: "Tenant" },
  { id: "blue", label: "Blue" },
  { id: "teal", label: "Teal" },
  { id: "green", label: "Green" },
  { id: "amber", label: "Amber" },
  { id: "violet", label: "Violet" },
];

function clampSidebarWidth(value: number): number {
  return Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, Math.round(value)));
}

function readBoolean(key: string, fallback: boolean): boolean {
  if (typeof window === "undefined") return fallback;
  const value = window.localStorage.getItem(key);
  return value === null ? fallback : value === "1";
}

function readWidth(key: string): number {
  if (typeof window === "undefined") return SIDEBAR_DEFAULT;
  const value = Number(window.localStorage.getItem(key));
  return Number.isFinite(value) ? clampSidebarWidth(value) : SIDEBAR_DEFAULT;
}

function readStringArray(key: string): string[] {
  if (typeof window === "undefined") return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(key) || "[]") as unknown;
    return Array.isArray(parsed) ? parsed.filter((value): value is string => typeof value === "string") : [];
  } catch {
    return [];
  }
}

function labelForDepartment(value: string): string {
  const labels: Record<string, string> = {
    planning: "Planning",
    production: "Production",
    maintenance: "Maintenance",
    quality: "Quality & Compliance",
    "document-control": "Document Control",
    reliability: "Reliability",
    safety: "Safety Management",
    stores: "Procurement & Stores",
    workshops: "Workshops",
    admin: "Administration",
  };
  return labels[value] || value.replace(/-/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function leafItems(groups: PortalNavGroup[]): PortalNavItem[] {
  const flattened = flattenPortalNavigation(groups);
  const seen = new Set<string>();
  return flattened.filter((item) => {
    if (item.children?.length || seen.has(item.path)) return false;
    seen.add(item.path);
    return true;
  });
}

function NavBranch({
  item,
  pathname,
  level,
  expanded,
  favourites,
  onToggle,
  onFavourite,
  onNavigate,
}: NavBranchProps): React.ReactElement {
  const active = isPortalPathActive(pathname, item);
  const childActive = item.children?.some((child) => isPortalPathActive(pathname, child)) ?? false;
  const open = expanded.has(item.id) || childActive;
  const Icon = level === 0 && item.icon ? ICONS[item.icon] : null;
  const nextLevel = Math.min(2, level + 1) as 0 | 1 | 2;
  const isLeaf = !item.children?.length;

  return (
    <div className={`tenant-nav__branch tenant-nav__branch--level-${level}`}>
      <div className={`tenant-nav__row${active ? " is-active" : ""}${childActive ? " has-active-child" : ""}${isLeaf ? " is-leaf" : ""}`}>
        <button
          type="button"
          className="tenant-nav__link"
          onClick={() => onNavigate(item.path)}
          aria-current={active ? "page" : undefined}
          title={item.label}
        >
          {Icon ? <Icon size={17} strokeWidth={2} aria-hidden="true" /> : <span className="tenant-nav__rail" aria-hidden="true" />}
          <span>{item.label}</span>
        </button>
        {isLeaf ? (
          <button
            type="button"
            className={`tenant-nav__favourite${favourites.has(item.id) ? " is-selected" : ""}`}
            onClick={() => onFavourite(item)}
            aria-label={`${favourites.has(item.id) ? "Remove" : "Add"} ${item.label} ${favourites.has(item.id) ? "from" : "to"} favourites`}
            aria-pressed={favourites.has(item.id)}
            title={favourites.has(item.id) ? "Remove favourite" : "Add favourite"}
          >
            <Star size={13} fill={favourites.has(item.id) ? "currentColor" : "none"} aria-hidden="true" />
          </button>
        ) : (
          <button
            type="button"
            className="tenant-nav__expand"
            onClick={() => onToggle(item.id)}
            aria-label={`${open ? "Collapse" : "Expand"} ${item.label}`}
            aria-expanded={open}
          >
            {open ? <ChevronDown size={15} aria-hidden="true" /> : <ChevronRight size={15} aria-hidden="true" />}
          </button>
        )}
      </div>
      {open && item.children?.length ? (
        <div className="tenant-nav__children">
          {item.children.map((child) => (
            <NavBranch
              key={child.id}
              item={child}
              pathname={pathname}
              level={nextLevel}
              expanded={expanded}
              favourites={favourites}
              onToggle={onToggle}
              onFavourite={onFavourite}
              onNavigate={onNavigate}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function NavigationGroups({
  groups,
  pathname,
  expanded,
  favourites,
  onToggle,
  onFavourite,
  onNavigate,
}: {
  groups: PortalNavGroup[];
  pathname: string;
  expanded: Set<string>;
  favourites: Set<string>;
  onToggle: (id: string) => void;
  onFavourite: (item: PortalNavItem) => void;
  onNavigate: (path: string) => void;
}): React.ReactElement {
  return (
    <nav id="tenant-navigation" className="tenant-nav" aria-label="Portal navigation">
      {groups.map((group) => (
        <section key={group.id} className="tenant-nav__group" aria-labelledby={`tenant-nav-${group.id}`}>
          <h2 id={`tenant-nav-${group.id}`}>{group.label}</h2>
          <div className="tenant-nav__items">
            {group.items.map((item) => (
              <NavBranch
                key={item.id}
                item={item}
                pathname={pathname}
                level={0}
                expanded={expanded}
                favourites={favourites}
                onToggle={onToggle}
                onFavourite={onFavourite}
                onNavigate={onNavigate}
              />
            ))}
          </div>
        </section>
      ))}
    </nav>
  );
}

const DepartmentLayoutImpl: React.FC<Props> = ({
  amoCode,
  activeDepartment,
  children,
  showPollingErrorBanner = false,
}) => {
  const navigate = useNavigate();
  const location = useLocation();
  const currentUser = getCachedUser();
  const identity = `${currentUser?.id || "anon"}:${currentUser?.amo_id || amoCode}`;
  const pinnedKey = `amo_sidebar_pinned:${identity}`;
  const widthKey = `amo_sidebar_width:${identity}`;
  const accentKey = `amo_portal_accent:${identity}`;
  const recentKey = `amo_portal_recent:${identity}`;
  const favouritesKey = `amo_portal_favourites:${identity}`;
  const { scheme, setScheme } = useColorScheme();
  const { density, setDensity, motion, setMotion } = usePortalAppearance();

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [pinned, setPinned] = useState(() => readBoolean(pinnedKey, false));
  const [sidebarWidth, setSidebarWidth] = useState(() => readWidth(widthKey));
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [profileOpen, setProfileOpen] = useState(false);
  const [appearanceOpen, setAppearanceOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [recentPaths, setRecentPaths] = useState<string[]>(() => readStringArray(recentKey));
  const [favourites, setFavourites] = useState<Set<string>>(() => new Set(readStringArray(favouritesKey)));
  const [accent, setAccent] = useState<AccentId>(() => {
    if (typeof window === "undefined") return "tenant";
    const saved = window.localStorage.getItem(accentKey) as AccentId | null;
    return ACCENTS.some((item) => item.id === saved) ? (saved as AccentId) : "tenant";
  });
  const [adminProfile, setAdminProfile] = useState<AdminProfileState | null>(() => readCachedAdminProfileState(amoCode));
  const [adminProfileBusy, setAdminProfileBusy] = useState(false);
  const [adminProfileError, setAdminProfileError] = useState<string | null>(null);
  const profileRef = useRef<HTMLDivElement | null>(null);
  const sidebarRef = useRef<HTMLElement | null>(null);

  const navigation = useMemo(
    () => buildPortalNavigation({
      amoCode,
      user: currentUser,
      contextDepartment: activeDepartment,
      activeDepartment,
      adminModeActive: Boolean(adminProfile?.active),
    }),
    [activeDepartment, adminProfile?.active, amoCode, currentUser],
  );
  const leaves = useMemo(() => leafItems(navigation), [navigation]);
  const homePath = navigation[0]?.items.find((item) => item.id === "home")?.path || `/maintenance/${encodeURIComponent(amoCode)}`;
  const assignedWorkPath = leaves.find((item) => item.path.includes("/inbox/"))?.path || homePath;

  const searchResults = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return [];
    return leaves
      .filter((item) => `${item.label} ${item.path}`.toLowerCase().includes(query))
      .slice(0, 12);
  }, [leaves, searchQuery]);

  const favouriteItems = useMemo(
    () => leaves.filter((item) => favourites.has(item.id)),
    [favourites, leaves],
  );
  const recentItems = useMemo(
    () => recentPaths
      .map((path) => leaves.find((item) => item.path === path))
      .filter((item): item is PortalNavItem => Boolean(item)),
    [leaves, recentPaths],
  );

  const visibleNavigation = useMemo<PortalNavGroup[]>(() => {
    if (searchQuery.trim()) {
      return [{ id: "search-results", label: "Search results", items: searchResults }];
    }
    const utility: PortalNavGroup[] = [];
    if (favouriteItems.length) utility.push({ id: "favourites", label: "Favourites", items: favouriteItems });
    if (recentItems.length) utility.push({ id: "recent", label: "Recent", items: recentItems });
    return [...utility, ...navigation];
  }, [favouriteItems, navigation, recentItems, searchQuery, searchResults]);

  useEffect(() => {
    let active = true;
    const unsubscribe = onAdminProfileChange(({ amoCode: changedAmoCode, userId, state }) => {
      if (!active || userId !== currentUser?.id) return;
      if (changedAmoCode.trim().toLowerCase() !== amoCode.trim().toLowerCase()) return;
      setAdminProfile(state);
    });

    fetchAdminProfileState(amoCode)
      .then((state) => { if (active) setAdminProfile(state); })
      .catch(() => { if (active) setAdminProfile((previous) => previous || { eligible: false, active: false }); });

    return () => {
      active = false;
      unsubscribe();
    };
  }, [amoCode, currentUser?.id]);

  useEffect(() => {
    document.documentElement.dataset.portalAccent = accent;
    document.body.dataset.portalAccent = accent;
    window.localStorage.setItem(accentKey, accent);
  }, [accent, accentKey]);

  useEffect(() => { window.localStorage.setItem(pinnedKey, pinned ? "1" : "0"); }, [pinned, pinnedKey]);
  useEffect(() => { window.localStorage.setItem(widthKey, String(sidebarWidth)); }, [sidebarWidth, widthKey]);
  useEffect(() => { window.localStorage.setItem(recentKey, JSON.stringify(recentPaths)); }, [recentKey, recentPaths]);
  useEffect(() => { window.localStorage.setItem(favouritesKey, JSON.stringify([...favourites])); }, [favourites, favouritesKey]);

  useEffect(() => {
    const best = [...leaves]
      .filter((item) => isPortalPathActive(location.pathname, item))
      .sort((left, right) => right.path.length - left.path.length)[0];
    if (!best) return;
    setRecentPaths((previous) => [best.path, ...previous.filter((path) => path !== best.path)].slice(0, MAX_RECENT));
  }, [leaves, location.pathname]);

  useEffect(() => {
    if (!profileOpen) return;
    const onPointer = (event: PointerEvent) => {
      if (event.target instanceof Node && !profileRef.current?.contains(event.target)) {
        setProfileOpen(false);
        setAppearanceOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setProfileOpen(false);
        setAppearanceOpen(false);
      }
    };
    window.addEventListener("pointerdown", onPointer);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onPointer);
      window.removeEventListener("keydown", onKey);
    };
  }, [profileOpen]);

  useEffect(() => {
    if (!drawerOpen || pinned) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const sidebar = sidebarRef.current;
    const focusable = () => Array.from(sidebar?.querySelectorAll<HTMLElement>(
      'button:not(:disabled), input:not(:disabled), select:not(:disabled), a[href], [tabindex]:not([tabindex="-1"])',
    ) || []);
    focusable()[0]?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setDrawerOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const controls = focusable();
      if (!controls.length) return;
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      previousFocus?.focus();
    };
  }, [drawerOpen, pinned]);

  useEffect(() => {
    const activeIds = new Set<string>();
    const walk = (items: PortalNavItem[]) => {
      for (const item of items) {
        if (item.children?.some((child) => isPortalPathActive(location.pathname, child))) activeIds.add(item.id);
        if (item.children) walk(item.children);
      }
    };
    navigation.forEach((group) => walk(group.items));
    if (activeIds.size) setExpanded((previous) => new Set([...previous, ...activeIds]));
  }, [location.pathname, navigation]);

  const navigateFromDrawer = useCallback((path: string) => {
    navigate(path);
    setSearchQuery("");
    if (!pinned) setDrawerOpen(false);
  }, [navigate, pinned]);

  const toggleExpanded = useCallback((id: string) => {
    setExpanded((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleFavourite = useCallback((item: PortalNavItem) => {
    setFavourites((previous) => {
      const next = new Set(previous);
      if (next.has(item.id)) next.delete(item.id);
      else next.add(item.id);
      return next;
    });
  }, []);

  const startResize = useCallback((event: React.PointerEvent<HTMLButtonElement>) => {
    if (!pinned) return;
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = sidebarWidth;
    const onMove = (moveEvent: PointerEvent) => setSidebarWidth(clampSidebarWidth(startWidth + moveEvent.clientX - startX));
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp, { once: true });
  }, [pinned, sidebarWidth]);

  const toggleAdminProfile = useCallback(async () => {
    if (!adminProfile?.eligible || adminProfileBusy) return;
    setAdminProfileBusy(true);
    setAdminProfileError(null);
    try {
      const next = adminProfile.active
        ? await deactivateAdminProfile(amoCode)
        : await activateAdminProfile(amoCode);
      setAdminProfile(next);
      setProfileOpen(false);
      navigate(next.active ? `/maintenance/${encodeURIComponent(amoCode)}/admin/overview` : homePath);
    } catch (error) {
      setAdminProfileError(error instanceof Error ? error.message : "Admin profile could not be changed.");
    } finally {
      setAdminProfileBusy(false);
    }
  }, [adminProfile, adminProfileBusy, amoCode, homePath, navigate]);

  const handleSignOut = useCallback(() => {
    endSession("manual");
  }, []);

  const drawerVisible = pinned || drawerOpen;
  const shellStyle = { "--tenant-sidebar-width": `${sidebarWidth}px` } as React.CSSProperties;

  return (
    <BrandProvider nameOverride={amoCode.toUpperCase()} logoSource="amo">
      <BrandContext.Consumer>
        {(brand) => (
          <div
            className={`tenant-shell${pinned ? " tenant-shell--pinned" : ""}${drawerVisible ? " tenant-shell--drawer-open" : ""}`}
            style={shellStyle}
          >
            {!pinned && drawerOpen ? (
              <button className="tenant-shell__scrim" type="button" aria-label="Close navigation" onClick={() => setDrawerOpen(false)} />
            ) : null}

            <aside
              ref={sidebarRef}
              className="tenant-shell__sidebar"
              aria-label="Portal navigation drawer"
              aria-hidden={!drawerVisible}
              role={!pinned ? "dialog" : undefined}
              aria-modal={!pinned && drawerVisible ? true : undefined}
            >
              <header className="tenant-shell__sidebar-header">
                <button className="tenant-shell__brand" type="button" onClick={() => navigateFromDrawer(homePath)} title="Open department home">
                  <BrandLogo size={30} />
                  <span>
                    <strong>{brand.name || amoCode.toUpperCase()}</strong>
                    <small>AMO Portal</small>
                  </span>
                </button>
                <div className="tenant-shell__sidebar-actions">
                  <button type="button" className="tenant-shell__icon-button" onClick={() => setPinned((value) => !value)} aria-label={pinned ? "Unpin navigation" : "Pin navigation"} title={pinned ? "Unpin navigation" : "Pin navigation"}>
                    {pinned ? <PinOff size={16} /> : <Pin size={16} />}
                  </button>
                  {!pinned ? (
                    <button type="button" className="tenant-shell__icon-button" onClick={() => setDrawerOpen(false)} aria-label="Close navigation"><X size={17} /></button>
                  ) : null}
                </div>
              </header>

              <div className="tenant-shell__nav-tools">
                <label className="tenant-shell__search">
                  <Search size={15} aria-hidden="true" />
                  <span className="sr-only">Search navigation</span>
                  <input value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="Search pages" autoComplete="off" />
                  {searchQuery ? <button type="button" onClick={() => setSearchQuery("")} aria-label="Clear navigation search"><X size={13} /></button> : null}
                </label>
                {!searchQuery && (favouriteItems.length || recentItems.length) ? (
                  <div className="tenant-shell__nav-summary" aria-label="Navigation shortcuts">
                    {favouriteItems.length ? <span><Star size={12} fill="currentColor" /> {favouriteItems.length} favourite{favouriteItems.length === 1 ? "" : "s"}</span> : null}
                    {recentItems.length ? <span><Clock3 size={12} /> {recentItems.length} recent</span> : null}
                  </div>
                ) : null}
              </div>

              <NavigationGroups
                groups={visibleNavigation}
                pathname={location.pathname}
                expanded={expanded}
                favourites={favourites}
                onToggle={toggleExpanded}
                onFavourite={toggleFavourite}
                onNavigate={navigateFromDrawer}
              />

              {pinned ? <button type="button" className="tenant-shell__resize-handle" onPointerDown={startResize} aria-label="Resize navigation" title="Drag to resize navigation" /> : null}
            </aside>

            <div className="tenant-shell__workspace">
              <header className="tenant-shell__topbar">
                <div className="tenant-shell__topbar-start">
                  <button type="button" className="tenant-shell__menu-button" onClick={() => pinned ? setPinned(false) : setDrawerOpen((value) => !value)} aria-label={drawerVisible ? "Close navigation" : "Open navigation"} aria-expanded={drawerVisible} aria-controls="tenant-navigation">
                    {drawerVisible || pinned ? <PanelLeftClose size={19} /> : <Menu size={20} />}
                  </button>
                  <button className="tenant-shell__compact-brand" type="button" onClick={() => navigate(homePath)} aria-label="Open department home"><BrandLogo size={22} /></button>
                  <div className="tenant-shell__context">
                    <strong>{labelForDepartment(activeDepartment)}</strong>
                    <span>{brand.name || amoCode.toUpperCase()}</span>
                  </div>
                  {adminProfile?.active ? <span className="tenant-shell__admin-chip"><Sparkles size={13} /> Admin profile</span> : null}
                </div>

                <div className="tenant-shell__topbar-actions">
                  <LiveStatusIndicator compact />
                  <button type="button" className="tenant-shell__icon-button" onClick={() => navigateFromDrawer(assignedWorkPath)} aria-label="Notifications and assigned work" title="Notifications and assigned work"><Bell size={17} /></button>
                  <div className="tenant-shell__profile" ref={profileRef}>
                    <button type="button" className="tenant-shell__profile-trigger" onClick={() => setProfileOpen((value) => !value)} aria-expanded={profileOpen} aria-haspopup="menu">
                      <span className="tenant-shell__avatar">
                        {(currentUser?.first_name?.[0] || currentUser?.full_name?.[0] || "U").toUpperCase()}
                        {(currentUser?.last_name?.[0] || "").toUpperCase()}
                      </span>
                      <span className="tenant-shell__profile-name">{currentUser?.full_name || currentUser?.email || "User"}</span>
                      <ChevronDown size={14} aria-hidden="true" />
                    </button>

                    {profileOpen ? (
                      <div className="tenant-shell__profile-menu" role="menu">
                        <button type="button" role="menuitem" onClick={() => { setProfileOpen(false); navigate(`/maintenance/${encodeURIComponent(amoCode)}/profile`); }}><User size={15} /> View profile</button>
                        {adminProfile?.eligible ? (
                          <button type="button" role="menuitem" onClick={() => void toggleAdminProfile()} disabled={adminProfileBusy}>
                            {adminProfile.active ? <PanelLeftClose size={15} /> : <PanelLeftOpen size={15} />}
                            {adminProfileBusy ? "Updating admin profile…" : adminProfile.active ? "Admin profile Off" : "Admin profile On"}
                          </button>
                        ) : null}
                        <button type="button" role="menuitem" onClick={() => setAppearanceOpen((value) => !value)} aria-expanded={appearanceOpen}>
                          <SlidersHorizontal size={15} /> Appearance
                          <ChevronRight size={14} className="tenant-shell__profile-chevron" />
                        </button>

                        {appearanceOpen ? (
                          <div className="tenant-shell__appearance" aria-label="Appearance settings">
                            <label>
                              <span>Theme</span>
                              <select value={scheme} onChange={(event) => setScheme(event.target.value as "system" | "light" | "dark")}>
                                <option value="system">System</option>
                                <option value="light">Light</option>
                                <option value="dark">Dark</option>
                              </select>
                            </label>
                            <label>
                              <span>Density</span>
                              <select value={density} onChange={(event) => setDensity(event.target.value as "comfortable" | "compact")}>
                                <option value="comfortable">Comfortable</option>
                                <option value="compact">Compact</option>
                              </select>
                            </label>
                            <label>
                              <span>Motion</span>
                              <select value={motion} onChange={(event) => setMotion(event.target.value as "system" | "full" | "reduced")}>
                                <option value="system">System</option>
                                <option value="full">Full</option>
                                <option value="reduced">Reduced</option>
                              </select>
                            </label>
                            <div className="tenant-shell__accent-picker">
                              <span>Accent</span>
                              <div>
                                {ACCENTS.map((item) => (
                                  <button key={item.id} type="button" className={`tenant-shell__accent tenant-shell__accent--${item.id}${accent === item.id ? " is-selected" : ""}`} onClick={() => setAccent(item.id)} aria-label={`Use ${item.label} accent`} aria-pressed={accent === item.id} title={item.label} />
                                ))}
                              </div>
                            </div>
                          </div>
                        ) : null}

                        {adminProfileError ? <div className="tenant-shell__profile-error" role="alert">{adminProfileError}</div> : null}
                        <div className="tenant-shell__profile-divider" />
                        <button type="button" role="menuitem" className="is-danger" onClick={handleSignOut}><LogOut size={15} /> Sign out</button>
                      </div>
                    ) : null}
                  </div>
                </div>
              </header>

              <main className="tenant-shell__main">
                {showPollingErrorBanner ? <div className="tenant-shell__status-banner" role="status">Live data is temporarily delayed. Cached tenant data remains visible.</div> : null}
                <div className="tenant-shell__content">{children}</div>
              </main>
            </div>

          </div>
        )}
      </BrandContext.Consumer>
    </BrandProvider>
  );
};

export default DepartmentLayoutImpl;
