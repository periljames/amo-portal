import { useEffect, useRef, useState } from "react";
import { authHeaders } from "../../services/auth";
import { getApiBaseUrl } from "../../services/config";
import "./publicationDocxLayout.css";

const FRAME_DOCUMENT = `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data: blob:; font-src data: blob:;"><style>html,body{margin:0;min-height:100%;background:#e5e7eb}body{padding:12px;box-sizing:border-box;overflow:auto}#document{transform-origin:top left;contain:layout style}.docx-wrapper{padding:0!important;background:transparent!important}.docx-wrapper>section.docx{margin:0 auto 12px!important;box-shadow:0 2px 8px #0002}.docx-wrapper img,.docx-wrapper svg{max-width:none}</style></head><body><div id="styles"></div><div id="document"></div></body></html>`;

export default function PublicationDocxLayoutViewer({ fileUrl, title, zoom, onTextFallback }: {
  fileUrl: string;
  title: string;
  zoom: string;
  onTextFallback: () => void;
}) {
  const frameRef = useRef<HTMLIFrameElement | null>(null);
  const [frameReady, setFrameReady] = useState(false);
  const [status, setStatus] = useState("Opening document…");
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!frameReady) return;
    const controller = new AbortController();
    let current = true;
    const frameDocument = frameRef.current?.contentDocument;
    const host = frameDocument?.getElementById("document");
    const styles = frameDocument?.getElementById("styles");
    if (!host || !styles) return;
    const body = frameDocument!.createElement("div");
    const sheet = frameDocument!.createElement("div");
    setReady(false);
    setError("");
    setStatus("Opening document…");
    void (async () => {
      try {
        const [response, { renderAsync }] = await Promise.all([
          fetch(`${getApiBaseUrl()}${fileUrl}`, { headers: authHeaders(), signal: controller.signal }),
          import("docx-preview"),
        ]);
        if (!response.ok) throw new Error(`The Word source could not be loaded (${response.status}).`);
        const bytes = await response.arrayBuffer();
        if (!current) return;
        setStatus("Laying out pages on this device…");
        await renderAsync(bytes, body, sheet, {
          className: "docx",
          inWrapper: true,
          breakPages: true,
          ignoreWidth: false,
          ignoreHeight: false,
          ignoreFonts: false,
          ignoreLastRenderedPageBreak: false,
          renderHeaders: true,
          renderFooters: true,
          renderFootnotes: true,
          renderEndnotes: true,
          renderChanges: true,
          renderAltChunks: true,
          experimental: true,
          // Data URLs are self-contained inside the sandboxed frame. This keeps
          // package media (logos, signatures and other embedded images) alive
          // for the full reader session instead of depending on transient blob
          // URL ownership outside the frame.
          useBase64URL: true,
        });
        if (!current) return;
        host.replaceChildren(body);
        styles.replaceChildren(sheet);
        setReady(true);
        setStatus("");
        void frameDocument!.fonts.ready.catch(() => undefined);
      } catch (caught) {
        if (current) setError(caught instanceof Error ? caught.message : "The Word document could not be rendered.");
      }
    })();
    return () => { current = false; controller.abort(); host.replaceChildren(); styles.replaceChildren(); };
  }, [fileUrl, frameReady]);

  useEffect(() => {
    if (!ready) return;
    const frame = frameRef.current;
    const frameDocument = frame?.contentDocument;
    const host = frameDocument?.getElementById("document");
    const viewport = frameDocument?.scrollingElement;
    if (!frame || !host || !viewport) return;

    let previousScale = Number(host.dataset.scale || "1");
    const size = () => {
      const page = host.querySelector<HTMLElement>("section.docx");
      const pageWidth = page?.offsetWidth || 816;
      const nextScale = zoom === "fit"
        ? Math.min(1.5, Math.max(0.25, (frame.clientWidth - 32) / pageWidth))
        : Number(zoom) / 100;
      const oldHeight = Math.max(1, viewport.scrollHeight);
      const oldTop = viewport.scrollTop;
      const anchorRatio = oldTop / oldHeight;
      host.style.zoom = String(nextScale);
      host.dataset.scale = String(nextScale);
      if (Math.abs(nextScale - previousScale) > 0.001) {
        requestAnimationFrame(() => {
          viewport.scrollTop = anchorRatio * Math.max(1, viewport.scrollHeight);
        });
      }
      previousScale = nextScale;
    };

    size();
    const observer = new ResizeObserver(size);
    observer.observe(frame);
    return () => observer.disconnect();
  }, [ready, zoom]);

  return <section className="publication-docx" aria-label="Word document reader">
    {!ready && !error ? <p className="publication-docx__status" role="status">{status}</p> : null}
    {error ? <div className="publication-docx__error" role="alert"><p>{error}</p><button type="button" onClick={onTextFallback}>Open accessible text</button></div> : null}
    <iframe ref={frameRef} title={`${title} — Word layout`} sandbox="allow-same-origin" srcDoc={FRAME_DOCUMENT} onLoad={() => setFrameReady(true)} style={{ visibility: ready ? "visible" : "hidden" }} />
  </section>;
}
