import { useEffect, useRef, useState } from "react";
import { authHeaders } from "../../services/auth";
import { getApiBaseUrl } from "../../services/config";
import "./publicationDocxLayout.css";

const FRAME_DOCUMENT = `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data: blob:; font-src data: blob:;"><style>html,body{margin:0;background:#e5e7eb}body{padding:16px;box-sizing:border-box}#document{transform-origin:top left}.docx-wrapper{padding:0!important;background:transparent!important}.docx-wrapper>section.docx{margin:0 auto 16px!important;box-shadow:0 2px 8px #0002}img{max-width:100%}</style></head><body><div id="styles"></div><div id="document"></div></body></html>`;

export default function PublicationDocxLayoutViewer({ fileUrl, title, draft, onTextFallback }: {
  fileUrl: string;
  title: string;
  draft: boolean;
  onTextFallback: () => void;
}) {
  const frameRef = useRef<HTMLIFrameElement | null>(null);
  const [frameReady, setFrameReady] = useState(false);
  const [status, setStatus] = useState("Opening Word document…");
  const [error, setError] = useState("");
  const [zoom, setZoom] = useState("fit");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!frameReady) return;
    const controller = new AbortController();
    let current = true;
    const frameDocument = frameRef.current?.contentDocument;
    const host = frameDocument?.getElementById("document");
    const styles = frameDocument?.getElementById("styles");
    if (!host || !styles) return;
    // Each generation renders into its own detached nodes. A cancelled render
    // cannot overwrite a newer revision or leave partial Word pages visible.
    const body = frameDocument!.createElement("div");
    const sheet = frameDocument!.createElement("div");
    setReady(false);
    setError("");
    setStatus("Opening Word document…");
    void (async () => {
      try {
        const response = await fetch(`${getApiBaseUrl()}${fileUrl}`, { headers: authHeaders(), signal: controller.signal });
        if (!response.ok) throw new Error(`The Word source could not be loaded (${response.status}).`);
        const bytes = await response.arrayBuffer();
        if (!current) return;
        setStatus("Laying out Word pages on this device…");
        const { renderAsync } = await import("docx-preview");
        if (!current) return;
        await renderAsync(bytes, body, sheet, {
          className: "docx", inWrapper: true, breakPages: true,
          ignoreWidth: false, ignoreHeight: false, ignoreFonts: false,
          ignoreLastRenderedPageBreak: false, renderHeaders: true,
          renderFooters: true, renderFootnotes: true, renderEndnotes: true,
          useBase64URL: true,
        });
        if (!current) return;
        host.replaceChildren(body);
        styles.replaceChildren(sheet);
        await frameDocument!.fonts.ready;
        if (current) { setReady(true); setStatus(""); }
      } catch (caught) {
        if (current) setError(caught instanceof Error ? caught.message : "The Word document could not be rendered.");
      }
    })();
    return () => { current = false; controller.abort(); host.replaceChildren(); styles.replaceChildren(); };
  }, [fileUrl, frameReady]);

  useEffect(() => {
    if (!ready) return;
    const frame = frameRef.current;
    const host = frame?.contentDocument?.getElementById("document");
    if (!frame || !host) return;
    const size = () => {
      const page = host.querySelector<HTMLElement>("section.docx");
      const pageWidth = page?.offsetWidth || 816;
      const scale = zoom === "fit" ? Math.min(1.5, Math.max(0.25, (frame.clientWidth - 48) / pageWidth)) : Number(zoom) / 100;
      // CSS zoom preserves the browser's scroll geometry and never reparses DOCX.
      host.style.zoom = String(scale);
    };
    size();
    const observer = new ResizeObserver(size);
    observer.observe(frame);
    return () => observer.disconnect();
  }, [ready, zoom]);

  return <section className="publication-docx" aria-label="Word document reader">
    <div className="publication-docx__toolbar"><strong>{draft ? "Draft" : "Word document"}</strong><label>Page size <select aria-label="Word page size" value={zoom} onChange={(event) => setZoom(event.target.value)}><option value="fit">Fit width</option>{[50, 75, 100, 125, 150, 200].map((value) => <option key={value} value={value}>{value}%</option>)}</select></label></div>
    {!ready && !error ? <p role="status">{status}</p> : null}
    {error ? <div role="alert"><p>{error}</p><button type="button" onClick={onTextFallback}>Open accessible text</button></div> : null}
    <iframe ref={frameRef} title={`${title} — Word layout`} sandbox="allow-same-origin" srcDoc={FRAME_DOCUMENT} onLoad={() => setFrameReady(true)} style={{ visibility: ready ? "visible" : "hidden" }} />
  </section>;
}
