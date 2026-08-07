import { useCallback, useEffect, useState } from "react";
import { Navigate } from "react-router-dom";

import {
  getDocumentControlDashboard,
  getDocumentReadTarget,
  type DocumentControlDashboard,
  type ReadTargetResponse,
} from "../../services/documentControl";
import DocumentGovernanceRecordPage from "./DocumentGovernanceRecordPage";
import DocumentControlShell, {
  DocumentControlError,
  DocumentControlLoading,
  useDocumentControlRoute,
} from "./DocumentControlShell";

/**
 * Keeps governance records controller-only without making ordinary readers wander
 * through an empty control record. Controllers receive the full governed record;
 * readers are sent directly to the immutable revision they are permitted to open.
 */
export default function DocumentControlRecordEntryPage() {
  const { tenant, docId, basePath, readerBasePath } = useDocumentControlRoute();
  const [dashboard, setDashboard] = useState<DocumentControlDashboard | null>(null);
  const [target, setTarget] = useState<ReadTargetResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!tenant || !docId) return;
    setLoading(true);
    setError("");
    try {
      const summary = await getDocumentControlDashboard(tenant);
      setDashboard(summary);
      if (!summary.capabilities.control) {
        setTarget(await getDocumentReadTarget(tenant, docId));
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The document could not be opened.");
    } finally {
      setLoading(false);
    }
  }, [docId, tenant]);

  useEffect(() => { void load(); }, [load]);

  if (loading) {
    return <DocumentControlShell title="Opening document" subtitle="Resolving the immutable revision available to your role." canControl={false}><DocumentControlLoading label="Resolving your permitted revision…" /></DocumentControlShell>;
  }
  if (error) {
    return <DocumentControlShell title="Document unavailable" subtitle="The portal could not resolve a readable revision for this record." canControl={false}><DocumentControlError message={error} retry={() => void load()} /></DocumentControlShell>;
  }
  if (dashboard?.capabilities.control) return <DocumentGovernanceRecordPage />;
  if (target?.revision_id) {
    return <Navigate to={`${readerBasePath}/${docId}/rev/${target.revision_id}/read`} replace />;
  }
  return <Navigate to={`${basePath}/library`} replace />;
}
