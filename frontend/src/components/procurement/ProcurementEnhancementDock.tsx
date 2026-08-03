import { useEffect, useMemo, useState } from "react";
import { FileArchive, X } from "lucide-react";
import { useLocation } from "react-router-dom";
import ActionFeedback from "./ActionFeedback";
import ProcurementDocumentCenter from "./ProcurementDocumentCenter";
import { useActionFeedback } from "../../hooks/useActionFeedback";

export default function ProcurementEnhancementDock() {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const { feedback, clearFeedback, notify, audioEnabled, toggleAudio } = useActionFeedback();
  const amoCode = useMemo(() => {
    const parts = location.pathname.split("/").filter(Boolean);
    return decodeURIComponent(parts[1] || "UNKNOWN");
  }, [location.pathname]);

  useEffect(() => {
    const seen = new WeakSet<Element>();
    const inspect = () => {
      document.querySelectorAll(".proc-alert").forEach((element) => {
        if (seen.has(element)) return;
        seen.add(element);
        const message = element.textContent?.replace("Dismiss", "").trim();
        if (!message) return;
        notify(element.classList.contains("proc-alert--error") ? "error" : "success", message);
      });
    };
    inspect();
    const observer = new MutationObserver(inspect);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [notify]);

  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [open]);

  return (
    <>
      <ActionFeedback feedback={feedback} onDismiss={clearFeedback} audioEnabled={audioEnabled} onToggleAudio={toggleAudio} />
      <button type="button" className="proc-evidence-launcher" onClick={() => setOpen(true)}>
        <FileArchive size={17} /> Evidence & records
      </button>
      {open && (
        <div className="proc-evidence-drawer" role="dialog" aria-modal="true" aria-label="Procurement evidence and records">
          <button type="button" className="proc-evidence-backdrop" onClick={() => setOpen(false)} aria-label="Close evidence drawer" />
          <div className="proc-evidence-drawer__panel">
            <div className="proc-evidence-drawer__topbar">
              <div><strong>Procurement evidence control</strong><span>External forms, scanned records, DMS links, and Quality verification</span></div>
              <button type="button" onClick={() => setOpen(false)} aria-label="Close"><X size={18} /></button>
            </div>
            <ProcurementDocumentCenter amoCode={amoCode} onFeedback={notify} />
          </div>
        </div>
      )}
    </>
  );
}
