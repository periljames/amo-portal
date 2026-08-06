import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ModalTopLayerGuard } from "../components/shared/ModalTopLayerGuard";
import { ManualsReaderRoutes, TenantBrandingProvider } from "../packages/manuals-reader";

function App() {
  const tenantSlug = window.location.pathname.split("/")[2] || "";
  return (
    <BrowserRouter>
      <TenantBrandingProvider tenantSlug={tenantSlug}>
        <ManualsReaderRoutes />
        <ModalTopLayerGuard />
      </TenantBrandingProvider>
    </BrowserRouter>
  );
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
