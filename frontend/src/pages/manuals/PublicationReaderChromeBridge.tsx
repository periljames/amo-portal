import { useEffect, useMemo, useState } from "react";
import { Bot, FileText, History, LibraryBig, Link2, Sparkles } from "lucide-react";
import { createPortal } from "react-dom";
import { useSearchParams } from "react-router-dom";

import "./publicationReaderRealworldStability.css";

type ReaderTab = "detail" | "history" | "citations" | "subsidiary";

type PortalTargets = {
  header: HTMLElement | null;
  topbar: HTMLElement | null;
};

const TAB_VALUES = new Set<ReaderTab>(["detail", "history", "citations", "subsidiary"]);

const TABS: Array<{
  value: ReaderTab;
  label: string;
  icon: typeof FileText;
}> = [
  { value: "detail", label: "Document", icon: FileText },
  { value: "history", label: "History", icon: History },
  { value: "citations", label: "Citations", icon: Link2 },
  { value: "subsidiary", label: "Subsidiary", icon: LibraryBig },
];

function locatePortalTargets(): PortalTargets {
  return {
    header: document.querySelector<HTMLElement>(".publication-document-header"),
    topbar: document.querySelector<HTMLElement>(".tenant-shell__topbar-actions"),
  };
}

function assistantIsOpen(): boolean {
  return Boolean(document.querySelector(".documentation-assistant.is-floating"));
}

function enforceOriginalLayout(): void {
  if (!document.querySelector(".publication-html-document")) return;
  const buttons = [...document.querySelectorAll<HTMLButtonElement>(".publication-reader-controls button")];
  const original = buttons.find((button) => /original layout|pdf proof/i.test(button.textContent || ""));
  original?.click();
}

export default function PublicationReaderChromeBridge() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [targets, setTargets] = useState<PortalTargets>(() => ({ header: null, topbar: null }));
  const [assistantOpen, setAssistantOpen] = useState(false);

  const requestedTab = searchParams.get("tab") as ReaderTab | null;
  const activeTab = useMemo<ReaderTab>(
    () => requestedTab && TAB_VALUES.has(requestedTab) ? requestedTab : "detail",
    [requestedTab],
  );

  useEffect(() => {
    document.body.classList.add("publication-reader-route-active");
    let animationFrame = 0;
    let attempts = 0;

    const locate = () => {
      const next = locatePortalTargets();
      setTargets((current) => (
        current.header === next.header && current.topbar === next.topbar ? current : next
      ));
      setAssistantOpen(assistantIsOpen());
      enforceOriginalLayout();
      attempts += 1;
      if ((!next.header || !next.topbar) && attempts < 90) {
        animationFrame = window.requestAnimationFrame(locate);
      }
    };

    const synchronizeAssistantAfterClick = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      if (!target.closest(".documentation-assistant, .publication-assistant-topbar")) return;
      window.requestAnimationFrame(() => setAssistantOpen(assistantIsOpen()));
    };

    locate();
    document.addEventListener("click", synchronizeAssistantAfterClick, true);

    return () => {
      document.body.classList.remove("publication-reader-route-active");
      document.removeEventListener("click", synchronizeAssistantAfterClick, true);
      if (animationFrame) window.cancelAnimationFrame(animationFrame);
    };
  }, []);

  const setTab = (tab: ReaderTab) => {
    const next = new URLSearchParams(searchParams);
    if (tab === "detail") next.delete("tab");
    else next.set("tab", tab);
    setSearchParams(next, { replace: false });
  };

  const toggleAssistant = () => {
    const close = document.querySelector<HTMLButtonElement>(
      ".documentation-assistant.is-floating .documentation-assistant__close",
    );
    if (close) {
      close.click();
      setAssistantOpen(false);
      return;
    }

    const launcher = document.querySelector<HTMLButtonElement>(".documentation-assistant-launcher");
    launcher?.click();
    window.requestAnimationFrame(() => setAssistantOpen(assistantIsOpen()));
  };

  return <>
    {targets.header ? createPortal(
      <nav className="publication-header-tabs-bridge" aria-label="Publication record views">
        {TABS.map(({ value, label, icon: Icon }) => (
          <button
            key={value}
            type="button"
            className={activeTab === value ? "active" : ""}
            aria-current={activeTab === value ? "page" : undefined}
            onClick={() => setTab(value)}
            title={label}
          >
            <Icon size={14} aria-hidden="true" />
            <span>{label}</span>
          </button>
        ))}
      </nav>,
      targets.header,
    ) : null}

    {targets.topbar ? createPortal(
      <button
        type="button"
        className={`tenant-shell__icon-button publication-assistant-topbar${assistantOpen ? " is-active" : ""}`}
        aria-label={assistantOpen ? "Close document AI assistant" : "Open document AI assistant"}
        aria-pressed={assistantOpen}
        title={assistantOpen ? "Close document AI assistant" : "Document AI assistant"}
        onClick={toggleAssistant}
      >
        <span className="publication-assistant-topbar__glyph" aria-hidden="true">
          <Bot size={17} />
          <Sparkles size={9} />
        </span>
      </button>,
      targets.topbar,
    ) : null}
  </>;
}
