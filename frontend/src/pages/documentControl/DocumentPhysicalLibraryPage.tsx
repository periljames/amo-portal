import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { getWarehouseOverview } from "../../services/documentLibrary";
import DocumentControlShell from "./DocumentControlShell";
import LibraryOperationsPanel from "./LibraryOperationsPanel";
import { useDocumentControlRoute } from "./documentControlRoute";

type PhysicalLibraryMode = "warehouse" | "catalog" | "scan" | "inventory" | "internet" | "account";
const MODES: PhysicalLibraryMode[] = ["warehouse", "catalog", "scan", "inventory", "internet", "account"];

export default function DocumentPhysicalLibraryPage() {
  const { tenant } = useDocumentControlRoute();
  const [params] = useSearchParams();
  const rawMode = params.get("view") as PhysicalLibraryMode | null;
  const mode = useMemo<PhysicalLibraryMode>(() => MODES.includes(rawMode as PhysicalLibraryMode) ? rawMode as PhysicalLibraryMode : "catalog", [rawMode]);
  const [canControl, setCanControl] = useState(false);

  useEffect(() => {
    if (!tenant) return;
    let cancelled = false;
    void getWarehouseOverview(tenant)
      .then((response) => {
        if (!cancelled) setCanControl(Boolean(response.capabilities.control));
      })
      .catch(() => {
        if (!cancelled) setCanControl(false);
      });
    return () => { cancelled = true; };
  }, [tenant]);

  return <DocumentControlShell
    title="Physical library"
    eyebrow="LIBRARY SERVICES"
    subtitle="Catalogue, circulate, inventory and trace physical knowledge assets using the same governed DMS identity and custody controls."
    canControl={canControl}
  >
    <LibraryOperationsPanel
      key={mode}
      tenant={tenant}
      canControl={canControl}
      initialMode={mode}
      initialScan={params.get("scan")}
      standalone
    />
  </DocumentControlShell>;
}
