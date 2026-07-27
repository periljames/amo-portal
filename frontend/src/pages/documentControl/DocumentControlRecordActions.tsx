import { Settings2 } from "lucide-react";

import type { DocumentDetailResponse } from "../../services/documentControl";
import DocumentControlLifecycleActions, { type LifecycleView } from "./DocumentControlLifecycleActionsGuarded";
import DocumentControlRecordActionsBase from "./DocumentControlRecordActionsBase";
import { DocumentControlSection, useDocumentControlRoute } from "./DocumentControlShell";

type ActiveView =
  | "overview"
  | "revisions"
  | "changes"
  | "workflow"
  | "authority"
  | "temporary-revisions"
  | "distribution"
  | "compliance"
  | "applicability"
  | "copies"
  | "reviews"
  | "integrations"
  | "external"
  | "history";

const LIFECYCLE_VIEWS = new Set<ActiveView>([
  "workflow",
  "authority",
  "temporary-revisions",
  "copies",
  "reviews",
]);

export default function DocumentControlRecordActions({
  detail,
  onChanged,
  compact = false,
  activeView = "overview",
}: {
  detail: DocumentDetailResponse;
  onChanged: () => void;
  compact?: boolean;
  activeView?: ActiveView;
}) {
  const { tenant } = useDocumentControlRoute();

  if (compact) {
    return (
      <button
        type="button"
        className="dc-button"
        onClick={() => document.getElementById("document-control-record-actions")?.scrollIntoView({ behavior: "smooth", block: "start" })}
      >
        <Settings2 size={14} /> Manage document
      </button>
    );
  }

  if (!LIFECYCLE_VIEWS.has(activeView)) {
    return (
      <div id="document-control-record-actions">
        <DocumentControlRecordActionsBase detail={detail} onChanged={onChanged} activeView={activeView} />
      </div>
    );
  }

  return (
    <div id="document-control-record-actions">
      <DocumentControlSection
        title={`${activeView.replaceAll("-", " ")} controls`}
        description="Lifecycle actions are validated against tenant data, immutable revision identity, evidence, and server-side transition rules."
      >
        <div className="dc-section__body">
          <DocumentControlLifecycleActions
            detail={detail}
            tenant={tenant}
            activeView={activeView as LifecycleView}
            onChanged={onChanged}
          />
        </div>
      </DocumentControlSection>
    </div>
  );
}
