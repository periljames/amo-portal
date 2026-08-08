import { Settings2, UsersRound } from "lucide-react";
import { useNavigate } from "react-router-dom";

import type { DocumentDetailResponse } from "../../services/documentControl";
import DocumentControlDistributionActions from "./DocumentControlDistributionActions";
import DocumentControlLifecycleActions, { type LifecycleView } from "./DocumentControlLifecycleActionsGuarded";
import DocumentControlPrimaryActions from "./DocumentControlPrimaryActions";
import DocumentControlRecordActionsBase from "./DocumentControlRecordActionsBase";
import { DocumentControlSection } from "./DocumentControlShell";
import { useDocumentControlRoute } from "./documentControlRoute";

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
  const navigate = useNavigate();
  const { tenant, basePath } = useDocumentControlRoute();

  if (compact) {
    return <>
      <DocumentControlPrimaryActions detail={detail} tenant={tenant} basePath={basePath} onChanged={onChanged} />
      <button
        type="button"
        className="dc-button"
        onClick={() => navigate(`${basePath}/library/${detail.document.id}?governance=assignments`)}
      >
        <UsersRound size={14} /> Responsibilities
      </button>
      <button
        type="button"
        className="dc-button"
        onClick={() => document.getElementById("document-control-record-actions")?.scrollIntoView({ behavior: "smooth", block: "start" })}
      >
        <Settings2 size={14} /> More controls
      </button>
    </>;
  }

  if (activeView === "distribution") {
    return (
      <div id="document-control-record-actions">
        <DocumentControlSection
          title="Distribution controls"
          description="Issue this revision to eligible active tenant users, create acknowledgement obligations, and notify recipients automatically."
        >
          <div className="dc-section__body">
            <DocumentControlDistributionActions detail={detail} tenant={tenant} onChanged={onChanged} />
          </div>
        </DocumentControlSection>
      </div>
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
