import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  getDocumentControlDashboard,
  type DocumentControlDashboard,
} from "../../services/documentControl";
import DocumentControlRecordPage from "./DocumentControlRecordPage";
import DocumentGovernanceRecordPage from "./DocumentGovernanceRecordPage";
import DocumentControlShell, {
  DocumentControlError,
  DocumentControlLoading,
  useDocumentControlRoute,
} from "./DocumentControlShell";

/**
 * Resolve the correct role surface for one controlled document.
 *
 * Every authorised reader remains inside the unified Document Control record so
 * governance context is visible without granting mutation authority. Effective
 * reviewers receive only their assigned workflow decisions from the document
 * detail projection, while controller-only responsibility administration stays
 * behind the control capability check below.
 */
export default function DocumentControlRecordEntryPage() {
  const { tenant, docId } = useDocumentControlRoute();
  const [searchParams] = useSearchParams();
  const [dashboard, setDashboard] = useState<DocumentControlDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!tenant || !docId) return;
    setLoading(true);
    setError("");
    try {
      setDashboard(await getDocumentControlDashboard(tenant));
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
  if (dashboard?.capabilities.control && searchParams.get("governance") === "assignments") {
    return <DocumentGovernanceRecordPage />;
  }
  return <DocumentControlRecordPage />;
}
