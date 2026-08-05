import React, { useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import QualityAuditPlanScheduleBasePage from "./QualityAuditPlanScheduleBasePage";

const PLANNER_SOURCE = "planner";
const CREATE_BUTTON_LABEL = "Create schedule";

function isCreateScheduleButton(element: HTMLButtonElement): boolean {
  return element.textContent?.replace(/\s+/g, " ").trim() === CREATE_BUTTON_LABEL;
}

/**
 * Compatibility boundary for the Quality Operations Planner handoff.
 *
 * The established audit planning page owns the actual schedule form and its
 * browser-persisted draft. A planner handoff therefore opens that existing form
 * after the page mounts, rather than introducing a second creation workflow or
 * passing unsupported draft fields through a register URL.
 */
export default function QualityAuditPlanSchedulePage(): React.ReactElement {
  const [searchParams, setSearchParams] = useSearchParams();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const handledRef = useRef(false);
  const isPlannerHandoff = searchParams.get("source") === PLANNER_SOURCE;

  useEffect(() => {
    if (!isPlannerHandoff || handledRef.current) return;

    const root = rootRef.current;
    if (!root) return;

    const openAuthoritativeForm = (): boolean => {
      if (handledRef.current) return true;
      const createButton = Array.from(root.querySelectorAll<HTMLButtonElement>("button"))
        .find(isCreateScheduleButton);
      if (!createButton || createButton.disabled) return false;

      handledRef.current = true;
      createButton.click();

      const next = new URLSearchParams(searchParams);
      next.delete("source");
      next.delete("create");
      setSearchParams(next, { replace: true });
      return true;
    };

    if (openAuthoritativeForm()) return;

    const observer = new MutationObserver(() => {
      if (openAuthoritativeForm()) observer.disconnect();
    });
    observer.observe(root, { childList: true, subtree: true });

    const timeout = window.setTimeout(() => observer.disconnect(), 10_000);
    return () => {
      window.clearTimeout(timeout);
      observer.disconnect();
    };
  }, [isPlannerHandoff, searchParams, setSearchParams]);

  return (
    <div ref={rootRef} data-qms-planner-handoff-root style={{ display: "contents" }}>
      <QualityAuditPlanScheduleBasePage />
    </div>
  );
}
