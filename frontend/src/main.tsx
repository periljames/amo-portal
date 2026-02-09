// src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
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
      staleTime: 10_000,
      refetchInterval: 45_000,
      refetchOnWindowFocus: true,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <RealtimeProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </RealtimeProvider>
    </QueryClientProvider>
  </React.StrictMode>
);
