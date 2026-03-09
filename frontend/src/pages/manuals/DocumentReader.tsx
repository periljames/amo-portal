import { useEffect, useMemo, useRef, useState } from "react";

type MetaInfo = {
  revisionNumber?: string;
  issueNumber?: string | null;
  approvalStatus?: string;
  pendingAcknowledgements?: number;
};

type FallbackSection = { id: string; heading: string; level: number; anchor_slug?: string };
type FallbackBlock = { section_id: string; html: string };

export type ReaderSection = {
  id: string;
  label: string;
  level: 1 | 2 | 3;
  html: string;
};

type ReaderState = {
  mode: "section" | "continuous";
  activeSectionId: string;
  scrollTop: number;
};

type Props = {
  file: File | null;
  fallbackSections: FallbackSection[];
  fallbackBlocks: FallbackBlock[];
  meta: MetaInfo;
  readerState: ReaderState;
  onReaderStateChange: (next: Partial<ReaderState>) => void;
};

const SECTION_BUFFER = 3;

function slugify(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

export function buildFallbackSections(sections: FallbackSection[], blocks: FallbackBlock[]): ReaderSection[] {
  const blockMap: Record<string, string[]> = {};
  for (const block of blocks) {
    if (!blockMap[block.section_id]) blockMap[block.section_id] = [];
    blockMap[block.section_id].push(block.html);
  }

  return sections
    .filter((section) => section.level >= 1 && section.level <= 3)
    .map((section, index) => ({
      id: section.anchor_slug || `${slugify(section.heading) || `section-${index + 1}`}-${index}`,
      label: section.heading,
      level: section.level as 1 | 2 | 3,
      html: (blockMap[section.id] || []).join(""),
    }));
}

export function filteredSectionRange(sections: ReaderSection[], activeSectionId: string): { start: number; end: number } {
  const activeIndex = Math.max(0, sections.findIndex((section) => section.id === activeSectionId));
  const start = Math.max(0, activeIndex - SECTION_BUFFER);
  const end = Math.min(sections.length, activeIndex + SECTION_BUFFER + 1);
  return { start, end };
}

export default function DocumentReader({ file, fallbackSections, fallbackBlocks, meta, readerState, onReaderStateChange }: Props) {
  const [sections, setSections] = useState<ReaderSection[]>([]);
  const [renderError, setRenderError] = useState("");
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const docxContainerRef = useRef<HTMLDivElement | null>(null);
  const headingRefs = useRef<Record<string, string>>({});

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    container.scrollTop = readerState.scrollTop || 0;
  }, [readerState.scrollTop]);

  useEffect(() => {
    const fallback = buildFallbackSections(fallbackSections, fallbackBlocks);
    if (!file) {
      setSections(fallback);
      setRenderError("");
      return;
    }

    let active = true;
    setLoading(true);
    setRenderError("");

    const parse = async () => {
      try {
        const mammoth = await import("mammoth");
        const buf = await file.arrayBuffer();
        if (!active) return;

        const html = await mammoth.convertToHtml({ arrayBuffer: buf });
        const parser = new DOMParser();
        const doc = parser.parseFromString(html.value, "text/html");
        const nodes = Array.from(doc.body.children);

        const parsed: ReaderSection[] = [];
        let current: ReaderSection | null = null;
        let index = 0;

        for (const node of nodes) {
          const tag = node.tagName?.toLowerCase();
          const isHeading = tag === "h1" || tag === "h2" || tag === "h3";

          if (isHeading) {
            if (current) parsed.push(current);
            const level = Number(tag.replace("h", "")) as 1 | 2 | 3;
            const label = (node.textContent || `Section ${index + 1}`).trim();
            current = {
              id: `${slugify(label) || `section-${index + 1}`}-${index}`,
              label,
              level,
              html: "",
            };
            index += 1;
            continue;
          }

          if (!current) {
            current = { id: "preface-0", label: "Preface", level: 1, html: "" };
          }
          current.html += node.outerHTML;
        }
        if (current) parsed.push(current);

        if (active) {
          setSections(parsed.length ? parsed : fallback);
        }
      } catch (error) {
        if (active) {
          setSections(fallback);
          setRenderError(error instanceof Error ? error.message : "Failed to parse DOCX");
        }
      } finally {
        if (active) setLoading(false);
      }
    };

    void parse();
    return () => {
      active = false;
    };
  }, [file, fallbackSections, fallbackBlocks]);

  useEffect(() => {
    if (!file || !docxContainerRef.current || readerState.mode !== "continuous") return;

    let alive = true;
    const target = docxContainerRef.current;
    target.innerHTML = "";

    const render = async () => {
      try {
        const [{ renderAsync }] = await Promise.all([import("docx-preview")]);
        const buf = await file.arrayBuffer();
        if (!alive) return;
        await renderAsync(buf, target, undefined, {
          className: "docx",
          inWrapper: true,
          breakPages: true,
          ignoreLastRenderedPageBreak: false,
        });
      } catch {
        // fallback path already available via sections
      }
    };

    void render();
    return () => {
      alive = false;
    };
  }, [file, readerState.mode]);

  const activeSectionId = readerState.activeSectionId || sections[0]?.id || "";

  useEffect(() => {
    if (!sections.length) return;
    if (!activeSectionId || !sections.some((section) => section.id === activeSectionId)) {
      onReaderStateChange({ activeSectionId: sections[0].id });
    }
  }, [sections, activeSectionId, onReaderStateChange]);

  const renderedSections = useMemo(() => {
    if (!sections.length) return [] as ReaderSection[];
    if (readerState.mode === "continuous") return sections;
    const { start, end } = filteredSectionRange(sections, activeSectionId);
    return sections.slice(start, end);
  }, [sections, activeSectionId, readerState.mode]);


  useEffect(() => {
    const map: Record<string, string> = {};
    for (const section of sections) {
      map[section.id] = section.label.trim().toLowerCase();
    }
    headingRefs.current = map;
  }, [sections]);

  const jumpToSection = (sectionId: string) => {
    onReaderStateChange({ activeSectionId: sectionId });
    if (readerState.mode !== "continuous" || !docxContainerRef.current) return;

    const needle = headingRefs.current[sectionId];
    if (!needle) return;

    const headings = Array.from(docxContainerRef.current.querySelectorAll("h1, h2, h3"));
    const target = headings.find((el) => (el.textContent || "").trim().toLowerCase() === needle);
    if (target) {
      (target as HTMLElement).scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  return (
    <div className="manuals-reader-grid">
      <aside className="manuals-reader-panel toc-panel">
        <h3 className="manuals-panel-title">Table of contents</h3>
        <div className="manuals-mode-toggle">
          <button className={readerState.mode === "section" ? "active" : ""} onClick={() => onReaderStateChange({ mode: "section" })}>Single Section</button>
          <button className={readerState.mode === "continuous" ? "active" : ""} onClick={() => onReaderStateChange({ mode: "continuous" })}>Continuous</button>
        </div>
        {sections.map((section) => (
          <button
            key={section.id}
            className={`manuals-toc-item manuals-toc-l${section.level} ${activeSectionId === section.id ? "active" : ""}`}
            onClick={() => jumpToSection(section.id)}
          >
            {section.label}
          </button>
        ))}
      </aside>

      <section className="manuals-print-canvas" ref={containerRef} onScroll={(event) => onReaderStateChange({ scrollTop: (event.currentTarget as HTMLDivElement).scrollTop })}>
        <header className="manuals-info-bar">
          <span>Rev {meta.revisionNumber || "—"}</span>
          <span>Issue {meta.issueNumber || "—"}</span>
          <span>Status {meta.approvalStatus || "Draft"}</span>
          <span>Acks {meta.pendingAcknowledgements ?? 0}</span>
        </header>

        {loading ? <p className="manuals-muted">Preparing section index…</p> : null}
        {renderError ? <p className="manuals-error">{renderError}</p> : null}

        {readerState.mode === "continuous" && file ? (
          <div ref={docxContainerRef} className="manuals-docx-host" />
        ) : (
          <div className="manuals-section-host">
            {renderedSections.map((section) => (
              <article key={section.id} id={section.id} className="manuals-fallback-page">
                <h2>{section.label}</h2>
                <div dangerouslySetInnerHTML={{ __html: section.html || "<p>No content for this section.</p>" }} />
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
