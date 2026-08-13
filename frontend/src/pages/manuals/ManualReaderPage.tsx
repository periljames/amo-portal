import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Expand, FileDiff, Maximize2, Minimize2 } from "lucide-react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import DocumentationAssistantPanel from "./DocumentationAssistantPanel";
import PublicationAssistedNavigationBridge from "./PublicationAssistedNavigationBridge";
import PublicationsReaderPage from "./PublicationsReaderPage";
import PublicationInlineReferenceController from "./PublicationInlineReferenceController";
import "./publicationReaderPost477Stability.css";
import "./dmsReaderExperience.css";
import "./publicationReaderHeaderConsolidation.css";

type ReaderExperienceMode = "standard" | "immersive";

export default function ManualReaderPage() {
  const navigate = useNavigate();
  const params = useParams<{ amoCode?: string; tenantSlug?: string; manualId?: string; revId?: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const tenant = (params.amoCode || params.tenantSlug || "").toLowerCase();
  const workspaceCode = params.amoCode || params.tenantSlug || "";
  const requestedMode = searchParams.get("readerMode");
  const mode: ReaderExperienceMode = requestedMode === "immersive" ? "immersive" : "standard";
  const shellRef = useRef<HTMLDivElement | null>(null);
  const [fullscreen, setFullscreen] = useState(Boolean(document.fullscreenElement));
  const [fullscreenError, setFullscreenError] = useState("");

  useEffect(() => {
    const update = () => setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", update);
    return () => document.removeEventListener("fullscreenchange", update);
  }, []);

  const setMode = (nextMode: ReaderExperienceMode) => {
    const next = new URLSearchParams(searchParams);
    if (nextMode === "standard") next.delete("readerMode");
    else next.set("readerMode", nextMode);
    setSearchParams(next, { replace: true });
  };

  const openReview = () => {
    if (!workspaceCode || !params.manualId || !params.revId) return;
    navigate(`/maintenance/${encodeURIComponent(workspaceCode)}/publications/${encodeURIComponent(params.manualId)}/rev/${encodeURIComponent(params.revId)}/diff`);
  };

  const toggleFullscreen = async () => {
    setFullscreenError("");
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else if (shellRef.current) await shellRef.current.requestFullscreen();
    } catch (caught) {
      setFullscreenError(caught instanceof Error ? caught.message : "Fullscreen could not be opened in this browser.");
    }
  };

  return <div
    ref={shellRef}
    className={`dms-reader-shell dms-reader-shell--${mode}${fullscreen ? " dms-reader-shell--fullscreen" : ""}`}
    data-reader-mode={mode}
  >
    <div className="dms-reader-modebar" aria-label="Reader display mode">
      {workspaceCode ? <button type="button" onClick={() => navigate(`/maintenance/${encodeURIComponent(workspaceCode)}/document-control/library`)} title="Return to Document Control library"><ArrowLeft size={14} /><span>Library</span></button> : null}
      <div role="group" aria-label="Reading mode">
        <button type="button" className={mode === "standard" ? "active" : ""} aria-pressed={mode === "standard"} onClick={() => setMode("standard")}><Expand size={14} /><span>Standard</span></button>
        <button type="button" className={mode === "immersive" ? "active" : ""} aria-pressed={mode === "immersive"} onClick={() => setMode("immersive")}><Maximize2 size={14} /><span>Immersive</span></button>
        {params.manualId && params.revId ? <button type="button" onClick={openReview} title="Review changes against the available baseline"><FileDiff size={14} /><span>Review changes</span></button> : null}
        <button type="button" className={fullscreen ? "active" : ""} aria-pressed={fullscreen} onClick={() => void toggleFullscreen()}>{fullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}<span>{fullscreen ? "Exit fullscreen" : "Fullscreen"}</span></button>
      </div>
    </div>
    {fullscreenError ? <div className="dms-reader-mode-error" role="alert">{fullscreenError}</div> : null}
    <PublicationsReaderPage />
    <PublicationAssistedNavigationBridge />
    <PublicationInlineReferenceController />
    {tenant ? <DocumentationAssistantPanel
      tenant={tenant}
      manualId={params.manualId}
      revisionId={params.revId}
    /> : null}
  </div>;
}
