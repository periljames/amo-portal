// src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient } from "@tanstack/react-query";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";
import "@tinymomentum/liquid-glass-react/dist/components/LiquidGlassBase.css";
import App from "./App";
import { OfflineSyncIndicator } from "./components/offline/OfflineSyncIndicator";
import { RealtimeProvider } from "./components/realtime/RealtimeProvider";
import { clearApiResponseCache } from "./services/apiClient";
import { onSessionEvent } from "./services/auth";
import { BRANDING_EVENT } from "./services/branding";
import {
  clearAllPortalApiCaches,
  clearAllPortalOfflineData,
  currentOfflineScope,
  onOfflineSyncComplete,
  replayOfflineMutations,
} from "./services/offlinePersistence";
import { clearAllPortalQueryCaches, createPortalQueryPersister } from "./services/queryPersister";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/global.css";
import "./styles/qms.css";
import "./styles/components/app-shell.css";
import "./styles/components/page-header.css";
import "./styles/components/section-card.css";
import "./styles/components/data-table.css";
import "./styles/components/empty-state.css";
import "./styles/components/inline-error.css";
import "./styles/components/toast.css";
import "./styles/components/drawer.css";
import "./styles/components/dashboard-cockpit.css";
import "./styles/components/action-panel.css";
import "./styles/components/planning-production.css";
import "./styles/components/liquid-glass.css";
import "./styles/rostering.css";
// Theme adapters must load after all module CSS so literal legacy colours cannot win.
import "./styles/theme-contract.css";
import "./styles/theme-module-repairs.css";

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
  // Context changes are synchronous. Cancel and clear before another persistence
  // notification can write the previous AMO's QueryClient under the new scope.
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
  // This callback is a second line of defence for context mutations that happen
  // before the storage guard is installed or in non-browser test environments.
  if (nextScope === observedTenantScope) return;
  observedTenantScope = nextScope;
  clearTenantScopedRuntimeState();
});

installActiveAmoStorageGuard();
ensureManifest();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={{
        persister: queryPersister,
        buster: "amo-portal-query-v3",
        maxAge: QUERY_MAX_AGE_MS,
        dehydrateOptions: {
          shouldDehydrateQuery: shouldPersistQuery,
          shouldDehydrateMutation: (mutation) => mutation.state.isPaused,
        },
      }}
      onSuccess={() => {
        void queryClient.resumePausedMutations();
        void replayOfflineMutations();
      }}
    >
      <RealtimeProvider>
        <BrowserRouter>
          <App />
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
  onSessionEvent((detail) => {
    if (detail.type === "authenticated") {
      clearIfTenantScopeChanged();
      void replayOfflineMutations();
      return;
    }

    if (detail.type === "expired" || detail.type === "idle-logout") {
      // Clear readable caches after involuntary expiry, but retain the scoped outbox.
      // The user can sign in again and safely resume changes created while offline.
      observedTenantScope = currentOfflineScope();
      clearTenantScopedRuntimeState();
      void Promise.all([clearAllPortalApiCaches(), clearAllPortalQueryCaches()]);
      return;
    }

    if (detail.type === "manual-logout") {
      observedTenantScope = currentOfflineScope();
      clearTenantScopedRuntimeState();
      void Promise.all([clearAllPortalOfflineData(), clearAllPortalQueryCaches()]);
    }
  });

  // Superuser AMO switching uses the branding event in the same tab. The scope
  // comparison prevents ordinary logo/theme refreshes from clearing query data.
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

  window.addEventListener("online", () => void replayOfflineMutations());
  window.addEventListener("load", () => {
    void configurePortalServiceWorker().catch((error) => console.warn("[offline] Service worker unavailable", error));
  });
}
