// src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { onlineManager, QueryClient } from "@tanstack/react-query";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";
import "@tinymomentum/liquid-glass-react/dist/components/LiquidGlassBase.css";
import App from "./App";
import QualityEnhancementsRouteGate from "./components/QMS/QualityEnhancementsRouteGate";
import { OfflineSyncIndicator } from "./components/offline/OfflineSyncIndicator";
import { RealtimeProvider } from "./components/realtime/RealtimeProvider";
import { clearApiResponseCache } from "./services/apiClient";
import {
  flushPendingSessionRevocation,
  hasRecoverableSession,
  getToken,
  getTokenSecondsRemaining,
  onSessionEvent,
  recoverSession,
} from "./services/auth";
import { BRANDING_EVENT } from "./services/branding";
import {
  clearAllPortalApiCaches,
  currentOfflineScope,
  onOfflineSyncComplete,
  replayOfflineMutations,
} from "./services/offlinePersistence";
import { clearAllPortalQueryCaches, createPortalQueryPersister } from "./services/queryPersister";
import {
  isPortalReady,
  onPortalConnectivityChange,
  probePortalReadiness,
  startPortalConnectivity,
} from "./services/portalConnectivity";
import "./styles/index.css";

const QUERY_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;
const ACTIVE_AMO_STORAGE_KEYS = new Set(["amodb_active_amo_id", "amodb_admin_active_amo_id"]);
const SENSITIVE_QUERY_MARKERS = [
  "auth",
  "password",
  "token",
  "billing",
  "invoice",
  "email-log",
  "email-setting",
  "security",
  "diagnostic",
  "platform-control",
  "permission",
  "attachment",
  "download",
  "export",
];

type GuardedWindow = Window & {
  __amoPortalActiveAmoStorageGuardInstalled?: boolean;
};

function shouldPersistQuery(query: { queryKey: readonly unknown[]; state: { status: string } }): boolean {
  if (query.state.status !== "success") return false;
  const marker = query.queryKey.map((part) => String(part)).join(":").toLowerCase();
  return !SENSITIVE_QUERY_MARKERS.some((value) => marker.includes(value));
}

function ensureManifest(): void {
  if (typeof document === "undefined") return;
  let link = document.querySelector<HTMLLinkElement>('link[rel="manifest"]');
  if (!link) {
    link = document.createElement("link");
    link.rel = "manifest";
    document.head.appendChild(link);
  }
  link.href = "/portal.webmanifest";
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      networkMode: "offlineFirst",
      staleTime: 5 * 60_000,
      gcTime: QUERY_MAX_AGE_MS,
      refetchOnWindowFocus: false,
      refetchOnReconnect: true,
      refetchOnMount: false,
      refetchInterval: false,
      retry(failureCount, error) {
        const message = error instanceof Error ? error.message.toLowerCase() : "";
        if (
          message.includes("401")
          || message.includes("403")
          || message.includes("404")
          || message.includes("session expired")
          || message.includes("unauthorized")
          || message.includes("timeout")
          || message.includes("abort")
          || message.includes("offline")
          || message.includes("cached copy")
        ) {
          return false;
        }
        return failureCount < 1;
      },
      retryOnMount: false,
    },
    mutations: {
      networkMode: "offlineFirst",
      retry: 0,
    },
  },
});

let observedTenantScope = currentOfflineScope();

function clearTenantScopedRuntimeState(): void {
  void queryClient.cancelQueries();
  queryClient.clear();
  clearApiResponseCache();
}

function clearIfTenantScopeChanged(): boolean {
  const nextScope = currentOfflineScope();
  if (nextScope === observedTenantScope) return false;
  observedTenantScope = nextScope;
  clearTenantScopedRuntimeState();
  return true;
}

function installActiveAmoStorageGuard(): void {
  if (typeof window === "undefined" || typeof Storage === "undefined") return;
  const guardedWindow = window as GuardedWindow;
  if (guardedWindow.__amoPortalActiveAmoStorageGuardInstalled) return;

  const originalSetItem = Storage.prototype.setItem;
  const originalRemoveItem = Storage.prototype.removeItem;
  const originalClear = Storage.prototype.clear;

  Storage.prototype.setItem = function guardedSetItem(key: string, value: string): void {
    const isActiveAmoWrite = this === window.localStorage && ACTIVE_AMO_STORAGE_KEYS.has(key);
    const previous = isActiveAmoWrite ? this.getItem(key) : null;
    originalSetItem.call(this, key, value);
    if (isActiveAmoWrite && previous !== value) clearIfTenantScopeChanged();
  };

  Storage.prototype.removeItem = function guardedRemoveItem(key: string): void {
    const isActiveAmoWrite = this === window.localStorage && ACTIVE_AMO_STORAGE_KEYS.has(key);
    const previous = isActiveAmoWrite ? this.getItem(key) : null;
    originalRemoveItem.call(this, key);
    if (isActiveAmoWrite && previous !== null) clearIfTenantScopeChanged();
  };

  Storage.prototype.clear = function guardedClear(): void {
    const hadActiveAmo = this === window.localStorage
      && [...ACTIVE_AMO_STORAGE_KEYS].some((key) => this.getItem(key) !== null);
    originalClear.call(this);
    if (hadActiveAmo) clearIfTenantScopeChanged();
  };

  guardedWindow.__amoPortalActiveAmoStorageGuardInstalled = true;
}

const queryPersister = createPortalQueryPersister((_previousScope, nextScope) => {
  if (nextScope === observedTenantScope) return;
  observedTenantScope = nextScope;
  clearTenantScopedRuntimeState();
});

installActiveAmoStorageGuard();
ensureManifest();
onlineManager.setOnline(false);
startPortalConnectivity();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={{
        persister: queryPersister,
        buster: "amo-portal-query-v4",
        maxAge: QUERY_MAX_AGE_MS,
        dehydrateOptions: {
          shouldDehydrateQuery: shouldPersistQuery,
          shouldDehydrateMutation: (mutation) => mutation.state.isPaused,
        },
      }}
      onSuccess={() => {
        // The readiness subscriber owns recovery ordering: revoke a pending
        // logout, recover authentication, then resume work. Hydration alone is
        // never permission to send persisted mutations.
        if (isPortalReady()) void probePortalReadiness(true);
      }}
    >
      <RealtimeProvider>
        <BrowserRouter>
          <App />
          <QualityEnhancementsRouteGate />
        </BrowserRouter>
        <OfflineSyncIndicator />
      </RealtimeProvider>
    </PersistQueryClientProvider>
  </React.StrictMode>,
);

async function configurePortalServiceWorker(): Promise<void> {
  if (!("serviceWorker" in navigator)) return;
  const enabled = import.meta.env.PROD || import.meta.env.VITE_PORTAL_OFFLINE_ENABLED === "1";
  const registrations = await navigator.serviceWorker.getRegistrations();

  if (!enabled) {
    await Promise.all(
      registrations
        .filter((registration) => registration.active?.scriptURL.includes("/portal-sw.js"))
        .map((registration) => registration.unregister()),
    );
    return;
  }

  await Promise.all(
    registrations
      .filter((registration) => registration.active?.scriptURL.includes("/aerodoc-sw.js"))
      .map((registration) => registration.unregister()),
  );

  const hadController = Boolean(navigator.serviceWorker.controller);
  let reloadScheduled = false;
  const registration = await navigator.serviceWorker.register("/portal-sw.js", { scope: "/", updateViaCache: "none" });
  const activateWaitingWorker = () => registration.waiting?.postMessage({ type: "SKIP_WAITING" });

  registration.addEventListener("updatefound", () => {
    const worker = registration.installing;
    if (!worker) return;
    worker.addEventListener("statechange", () => {
      if (worker.state === "installed" && navigator.serviceWorker.controller) activateWaitingWorker();
    });
  });

  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (!hadController || reloadScheduled) return;
    reloadScheduled = true;
    window.location.reload();
  });

  activateWaitingWorker();
  await registration.update().catch(() => undefined);
}

if (typeof window !== "undefined") {
  let wasPortalReady = false;
  let recoverySequence: Promise<void> | null = null;
  onPortalConnectivityChange((connectivity) => {
    const ready = connectivity.state === "ONLINE";
    if (!ready) {
      wasPortalReady = false;
      onlineManager.setOnline(false);
      return;
    }
    if (wasPortalReady) return;
    wasPortalReady = true;
    recoverySequence = (async () => {
      await flushPendingSessionRevocation();
      const remaining = getTokenSecondsRemaining();
      if (hasRecoverableSession() && (!getToken() || (remaining !== null && remaining <= 0))) {
        await recoverSession("server-recovered");
        const recoveredRemaining = getTokenSecondsRemaining();
        if (!getToken() || (recoveredRemaining !== null && recoveredRemaining <= 0)) {
          wasPortalReady = false;
          onlineManager.setOnline(false);
          window.setTimeout(() => void probePortalReadiness(true), 2_000);
          return;
        }
      }
      onlineManager.setOnline(true);
      await queryClient.resumePausedMutations();
      await replayOfflineMutations();
      await queryClient.invalidateQueries();
    })().finally(() => {
      recoverySequence = null;
    });
  });

  onSessionEvent((detail) => {
    if (detail.type === "authenticated") {
      clearIfTenantScopeChanged();
      void queryClient.invalidateQueries({ queryKey: ["workforce", "permissions"] });
      if (!recoverySequence) void replayOfflineMutations();
      if (detail.reason === "session-recovered") void queryClient.invalidateQueries();
      return;
    }

    if (detail.type === "expired" || detail.type === "idle-logout") {
      observedTenantScope = currentOfflineScope();
      clearTenantScopedRuntimeState();
      void Promise.all([clearAllPortalApiCaches(), clearAllPortalQueryCaches()]);
      return;
    }

    if (detail.type === "manual-logout") {
      observedTenantScope = currentOfflineScope();
      clearTenantScopedRuntimeState();
      // Logout may clear in-memory/query state, but must never silently destroy an encrypted unsynced outbox.
      void Promise.all([clearAllPortalApiCaches(), clearAllPortalQueryCaches()]);
    }
  });

  window.addEventListener(BRANDING_EVENT, clearIfTenantScopeChanged);
  window.addEventListener("storage", (event) => {
    if (event.key && ACTIVE_AMO_STORAGE_KEYS.has(event.key)) clearIfTenantScopeChanged();
  });

  onOfflineSyncComplete((detail) => {
    const rosterChanged = detail.entityTypes.includes("roster-assignment")
      || detail.paths.some((path) => path.startsWith("/rostering/"));
    if (rosterChanged) {
      void queryClient.invalidateQueries({ queryKey: ["rostering"] });
      return;
    }
    void queryClient.invalidateQueries();
  });

  window.addEventListener("load", () => {
    void configurePortalServiceWorker().catch((error) => console.warn("[offline] Service worker unavailable", error));
  });

  navigator.serviceWorker?.addEventListener("message", (event) => {
    if (event.data?.type === "PORTAL_CONNECTIVITY_RECHECK" || event.data?.type === "PORTAL_SYNC_REQUESTED") {
      void probePortalReadiness(true);
    }
  });
}
