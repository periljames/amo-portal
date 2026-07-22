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
import { onSessionEvent } from "./services/auth";
import {
  clearAllPortalOfflineData,
  createPortalQueryPersister,
  onOfflineSyncComplete,
  replayOfflineMutations,
} from "./services/offlinePersistence";
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

const queryPersister = createPortalQueryPersister();

ensureManifest();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={{
        persister: queryPersister,
        buster: "amo-portal-query-v2",
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
      void replayOfflineMutations();
      return;
    }
    if (detail.type === "expired" || detail.type === "idle-logout" || detail.type === "manual-logout") {
      queryClient.clear();
      void clearAllPortalOfflineData();
    }
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
