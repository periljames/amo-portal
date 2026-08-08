import { Settings2, UsersRound } from "lucide-react";
import { useNavigate } from "react-router-dom";

import type { DocumentDetailResponse } from "../../services/documentControl";
import DocumentControlDistributionActions from "./DocumentControlDistributionActions";
import DocumentControlLifecycleActions from "./DocumentControlLifecycleActionsGuarded";
import DocumentControlPrimaryActions from "./DocumentControlPrimaryActions";
import DocumentControlRecordActionsBase from "./DocumentControlRecordActionsBase";
import { DocumentControlSection } from "./DocumentControlShell";
import { useDocumentControlRoute } from "./documentControlRoute";

export type DocumentWorkspaceView =
  | "overview"
  | "content"
  | "changes"
  | "workflow"
  | "distribution"
  | "compliance"
  | "relationships"
  | "history";

export default function DocumentControlRecordActions({
  detail,
  onChanged,
  compact = false,
  activeView = "overview",
}: {
  detail: DocumentDetailResponse;
  onChanged: () => void;
  compact?: boolean;
  activeView?: DocumentWorkspaceView;
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

  if (activeView === "history") return null;

  return (
    <div id="document-control-record-actions" className="dc-record-control-stack">
      {activeView === "overview" ? (
        <DocumentControlRecordActionsBase detail={detail} onChanged={onChanged} activeView="overview" />
      ) : null}

      {activeView === "content" ? (
        <DocumentControlRecordActionsBase detail={detail} onChanged={onChanged} activeView="revisions" />
      ) : null}

      {activeView === "changes" ? <>
        <DocumentControlRecordActionsBase detail={detail} onChanged={onChanged} activeView="changes" />
        <DocumentControlSection title="Temporary revision controls" description="Create, approve, place in force, incorporate or withdraw a temporary revision without leaving this document lifecycle.">
          <div className="dc-section__body"><DocumentControlLifecycleActions detail={detail} tenant={tenant} activeView="temporary-revisions" onChanged={onChanged} /></div>
        </DocumentControlSection>
      </> : null}

      {activeView === "workflow" ? <>
        <DocumentControlSection title="Revision workflow controls" description="Advance the authoritative technical, Quality, management and publication lifecycle only through server-validated decisions.">
          <div className="dc-section__body"><DocumentControlLifecycleActions detail={detail} tenant={tenant} activeView="workflow" onChanged={onChanged} /></div>
        </DocumentControlSection>
        <DocumentControlSection title="Authority controls" description="Create and update authority submissions as a stage of the revision lifecycle rather than a separate register hop.">
          <div className="dc-section__body"><DocumentControlLifecycleActions detail={detail} tenant={tenant} activeView="authority" onChanged={onChanged} /></div>
        </DocumentControlSection>
      </> : null}

      {activeView === "distribution" ? <>
        <DocumentControlSection title="Digital distribution controls" description="Issue the effective revision to eligible recipients and retain acknowledgement evidence.">
          <div className="dc-section__body"><DocumentControlDistributionActions detail={detail} tenant={tenant} onChanged={onChanged} /></div>
        </DocumentControlSection>
        <DocumentControlSection title="Physical controlled-copy controls" description="Issue numbered copies and record custody, transfer, recall, return, withdrawal and destruction evidence.">
          <div className="dc-section__body"><DocumentControlLifecycleActions detail={detail} tenant={tenant} activeView="copies" onChanged={onChanged} /></div>
        </DocumentControlSection>
      </> : null}

      {activeView === "compliance" ? <>
        <DocumentControlSection title="Periodic review controls" description="Schedule and complete continued-applicability reviews against the controlled document.">
          <div className="dc-section__body"><DocumentControlLifecycleActions detail={detail} tenant={tenant} activeView="reviews" onChanged={onChanged} /></div>
        </DocumentControlSection>
        <DocumentControlRecordActionsBase detail={detail} onChanged={onChanged} activeView="applicability" />
        <DocumentControlRecordActionsBase detail={detail} onChanged={onChanged} activeView="external" />
      </> : null}

      {activeView === "relationships" ? (
        <DocumentControlRecordActionsBase detail={detail} onChanged={onChanged} activeView="integrations" />
      ) : null}
    </div>
  );
}
