import { useState } from "react";
import { Settings2, UsersRound, X } from "lucide-react";
import { useNavigate } from "react-router-dom";

import type { DocumentDetailResponse } from "../../services/documentControl";
import DocumentControlChangeRequestActions from "./DocumentControlChangeRequestActions";
import DocumentControlDistributionActions from "./DocumentControlDistributionActions";
import DocumentControlExternalSourceActions from "./DocumentControlExternalSourceActions";
import DocumentControlIntegrationActions from "./DocumentControlIntegrationActions";
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

type RoleAwareCapabilities = DocumentDetailResponse["capabilities"] & { review?: boolean };

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
  const capabilities = detail.capabilities as RoleAwareCapabilities;
  const canControl = Boolean(capabilities.control);
  const canReview = Boolean(capabilities.review);
  const [reviewDialogOpen, setReviewDialogOpen] = useState(false);

  if (compact) {
    if (!canControl && !canReview) return null;
    if (canReview && !canControl) {
      return <>
        <button
          type="button"
          className="dc-button dc-button--primary"
          onClick={() => setReviewDialogOpen(true)}
        >
          Review assigned change
        </button>
        {reviewDialogOpen ? <div className="publications-upload-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setReviewDialogOpen(false); }}>
          <section className="publications-upload-dialog" role="dialog" aria-modal="true" aria-label="Assigned document review">
            <header>
              <div><h2>Assigned document review</h2><p>Only decisions granted by the effective governed responsibility are available.</p></div>
              <button type="button" onClick={() => setReviewDialogOpen(false)} aria-label="Close assigned review"><X size={18} /></button>
            </header>
            <DocumentControlLifecycleActions detail={detail} tenant={tenant} activeView="workflow" onChanged={() => { onChanged(); setReviewDialogOpen(false); }} />
          </section>
        </div> : null}
      </>;
    }
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

  if (canReview && !canControl) {
    if (activeView !== "workflow") return null;
    return (
      <div id="document-control-record-actions" className="dc-record-control-stack">
        <DocumentControlSection title="Assigned review decision" description="Only the workflow actions authorized by this document's effective governed responsibility are available.">
          <div className="dc-section__body"><DocumentControlLifecycleActions detail={detail} tenant={tenant} activeView="workflow" onChanged={onChanged} /></div>
        </DocumentControlSection>
      </div>
    );
  }

  if (!canControl) return null;

  return (
    <div id="document-control-record-actions" className="dc-record-control-stack">
      {activeView === "overview" ? (
        <DocumentControlRecordActionsBase detail={detail} onChanged={onChanged} activeView="overview" />
      ) : null}

      {activeView === "content" ? (
        <DocumentControlRecordActionsBase detail={detail} onChanged={onChanged} activeView="revisions" />
      ) : null}

      {activeView === "changes" ? <>
        <DocumentControlSection title="Raise a controlled change" description="Create the change against this document and, when applicable, select the live portal record that caused it rather than entering implementation IDs.">
          <div className="dc-section__body"><DocumentControlChangeRequestActions detail={detail} tenant={tenant} onChanged={onChanged} /></div>
        </DocumentControlSection>
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
        <DocumentControlSection title="External technical-data controls" description="Register governed OEM/authority sources, retain received revision files, establish currency and create the downstream applicability-assessment obligation.">
          <div className="dc-section__body"><DocumentControlExternalSourceActions detail={detail} tenant={tenant} onChanged={onChanged} /></div>
        </DocumentControlSection>
        <DocumentControlRecordActionsBase detail={detail} onChanged={onChanged} activeView="applicability" />
      </> : null}

      {activeView === "relationships" ? (
        <DocumentControlSection title="Governed module relationships" description="Search live tenant-scoped records from QMS, Training, Workforce, Planning and other portal domains, then create a server-verified relationship.">
          <div className="dc-section__body"><DocumentControlIntegrationActions detail={detail} tenant={tenant} onChanged={onChanged} /></div>
        </DocumentControlSection>
      ) : null}
    </div>
  );
}