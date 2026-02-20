import { useParams } from "react-router-dom";
import { ManualsReaderRoutes } from "./routes";
import { TenantBrandingProvider } from "./branding";

export function ManualsReaderApp() {
  const { tenantSlug = "" } = useParams();
  return (
    <TenantBrandingProvider tenantSlug={tenantSlug}>
      <ManualsReaderRoutes />
    </TenantBrandingProvider>
  );
}
