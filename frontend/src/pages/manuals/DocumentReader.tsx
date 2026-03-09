import { useEffect, useMemo, useRef, useState } from "react";

export type TocItem = { id: string; label: string; level: 1 | 2 | 3 };

type ReaderMeta = {
  revisionNumber?: string;
  issueNumber?: string | null;
  approvalStatus?: string;
  pendingAcknowledgements?: number;
  history?: Array<{ action: string; at: string; actor_id?: string | null }>;
};

type Props = {
  file: File | null;
  fallbackSections: Array<{ id: string; heading: string; level: number; anchor_slug?: string }>;
  fallbackBlocks: Array<{ section_id: string; html: string }>;
  meta: ReaderMeta;
};

function slugify(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

export default function DocumentReader({ file, fallbackSections, fallbackBlocks, meta }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [toc, setToc] = useState<TocItem[]>([]);
  const [renderError, setRenderError] = useState<string>("");
  const [loading, setLoading] = useState(false);

  const fallbackToc = useMemo<TocItem[]>(() => {
    return fallbackSections
      .filter((section) => section.level >= 1 && section.level <= 3)
      .map((section) => ({
        id: section.anchor_slug || slugify(section.heading) || section.id,
        label: section.heading,
        level: section.level as 1 | 2 | 3,
      }));
  }, [fallbackSections]);

  useEffect(() => {
    if (!containerRef.current) return;
    const node = containerRef.current;
    node.innerHTML = "";

    if (!file) {
      setToc(fallbackToc);
      setRenderError("");
      return;
    }

    let alive = true;
    setLoading(true);
    setRenderError("");

    const run = async () => {
      try {
        const [{ renderAsync }, mammoth] = await Promise.all([import("docx-preview"), import("mammoth")]);
        const buf = await file.arrayBuffer();
        if (!alive) return;
        await renderAsync(buf, node, undefined, {
          className: "docx",
          inWrapper: true,
          breakPages: true,
          ignoreLastRenderedPageBreak: false,
        });

        const html = await mammoth.convertToHtml({ arrayBuffer: buf });
        const parser = new DOMParser();
        const doc = parser.parseFromString(html.value, "text/html");
        const headings = Array.from(doc.querySelectorAll("h1, h2, h3"));
        const generated = headings.map((heading, index) => {
          const level = Number(heading.tagName.replace("H", "")) as 1 | 2 | 3;
          const label = (heading.textContent || `Section ${index + 1}`).trim();
          return { id: `${slugify(label) || `section-${index + 1}`}-${index}`, label, level };
        });
        if (alive) {
          setToc(generated);
        }
      } catch (error) {
        if (!alive) return;
        setRenderError(error instanceof Error ? error.message : "Failed to render DOCX");
      } finally {
        if (alive) setLoading(false);
      }
    };

    void run();
    return () => {
      alive = false;
    };
  }, [file, fallbackToc]);

  const tocItems = toc.length ? toc : fallbackToc;
  const blocksBySection = useMemo(() => {
    const map: Record<string, Array<{ html: string }>> = {};
    for (const block of fallbackBlocks) {
      if (!map[block.section_id]) map[block.section_id] = [];
      map[block.section_id].push({ html: block.html });
    }
    return map;
  }, [fallbackBlocks]);

  return (
    <div className="manuals-reader-grid">
      <aside className="manuals-reader-panel">
        <h3 className="manuals-panel-title">Table of contents</h3>
        {tocItems.length ? tocItems.map((item) => (
          <a key={item.id} href={`#${item.id}`} className={`manuals-toc-item manuals-toc-l${item.level}`}>
            {item.label}
          </a>
        )) : <p className="manuals-muted">No headings found.</p>}
      </aside>

      <section className="manuals-print-canvas">
        {loading ? <p className="manuals-muted">Rendering document…</p> : null}
        {renderError ? <p className="manuals-error">{renderError}</p> : null}

        {file ? <div ref={containerRef} className="manuals-docx-host" /> : (
          <div className="manuals-fallback-page" id="manual-fallback-page">
            {fallbackSections.length ? fallbackSections.map((section) => (
              <article key={section.id} id={section.anchor_slug || slugify(section.heading)}>
                <h2>{section.heading}</h2>
                {(blocksBySection[section.id] || []).map((block, index) => (
                  <div key={`${section.id}-${index}`} dangerouslySetInnerHTML={{ __html: block.html }} />
                ))}
              </article>
            )) : <p className="manuals-muted">Select a DOCX file to view high-fidelity rendering.</p>}
          </div>
        )}
      </section>

      <aside className="manuals-reader-panel">
        <h3 className="manuals-panel-title">Revision metadata</h3>
        <ul className="manuals-meta-list">
          <li><strong>Revision:</strong> {meta.revisionNumber || "—"}</li>
          <li><strong>Issue:</strong> {meta.issueNumber || "—"}</li>
          <li><strong>Status:</strong> {meta.approvalStatus || "Draft"}</li>
          <li><strong>Pending Acks:</strong> {meta.pendingAcknowledgements ?? 0}</li>
        </ul>
        <h4 className="manuals-panel-title">History</h4>
        <div className="manuals-history-list">
          {(meta.history || []).slice(0, 8).map((item, index) => (
            <div key={`${item.action}-${index}`} className="manuals-history-item">
              <div>{item.action}</div>
              <small>{new Date(item.at).toLocaleString()}</small>
            </div>
          ))}
        </div>
      </aside>
    </div>
  );
}
