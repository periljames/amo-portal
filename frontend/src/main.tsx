// src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient } from "@tanstack/react-query";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";
import { createSyncStoragePersister } from "@tanstack/query-sync-storage-persister";
import App from "./App";
import { RealtimeProvider } from "./components/realtime/RealtimeProvider";
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

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 10 * 60_000,
      refetchOnWindowFocus: false,
      refetchOnReconnect: true,
      refetchInterval: false,
    },
  },
});

const queryPersister = createSyncStoragePersister({
  storage: typeof window !== "undefined" ? window.localStorage : undefined,
  key: "amodb-query-cache-v1",
  throttleTime: 1500,
});

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={{
        persister: queryPersister,
        maxAge: 24 * 60 * 60 * 1000,
      }}
    >
      <RealtimeProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </RealtimeProvider>
    </PersistQueryClientProvider>
  </React.StrictMode>
);
