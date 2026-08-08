import { useCallback, useEffect, useState } from "react";
import { Navigate } from "react-router-dom";

import {
  getDocumentControlDashboard,
  getDocumentReadTarget,
  type DocumentControlDashboard,
  type ReadTargetResponse,
} from "../../services/documentControl";
import DocumentControlRecordPage from "./DocumentControlRecordPage";
import DocumentControlShell, {
  DocumentControlError,
  DocumentControlLoading,
  useDocumentControlRoute,
} from "./DocumentControlShell";

/**
 * Resolve the correct role surface for one controlled document.
 *
 * Controllers enter the unified lifecycle workspace. Ordinary readers skip
 * administrative metadata and open the immutable revision they are permitted to
 * read. Detailed governance assignment tooling remains available from the
 * controller workspace through the compatibility governance route while it is
 * progressively folded into Overview/Relationships.
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
    return <DocumentControlShell title="Opening document" subtitle="Resolving the controlled workspace available to your role." canControl={false}><DocumentControlLoading label="Resolving your permitted document workspace…" /></DocumentControlShell>;
  }
  if (error) {
    return <DocumentControlShell title="Document unavailable" subtitle="The portal could not resolve a controlled workspace for this record." canControl={false}><DocumentControlError message={error} retry={() => void load()} /></DocumentControlShell>;
  }
  if (dashboard?.capabilities.control) return <DocumentControlRecordPage />;
  if (target?.revision_id) {
    return <Navigate to={`${readerBasePath}/${docId}/rev/${target.revision_id}/read`} replace />;
  }
  return <Navigate to={`${basePath}/library`} replace />;
}
