import React, { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ArrowRight } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";

import { Button } from "../../components/UI/Admin";
import "../../styles/admin-setup-workflow-navigation.css";

type StepKey = "bases" | "departments" | "users" | "workforce" | "assets" | "modules";
type BaseReadiness = "loading" | "needs-base" | "needs-location" | "ready" | "unknown";

const STEP_KEYS: StepKey[] = ["bases", "departments", "users", "workforce", "assets", "modules"];

function stepFromSearch(search: string): StepKey | null {
  const value = new URLSearchParams(search).get("section");
  return STEP_KEYS.includes(value as StepKey) ? value as StepKey : null;
}

function prefersReducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

const AdminSetupWorkflowNavigator: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [baseReadiness, setBaseReadiness] = useState<BaseReadiness>("loading");
  const [portalTarget, setPortalTarget] = useState<HTMLElement | null>(null);
  const previousReadinessRef = useRef<BaseReadiness>("loading");
  const refreshTimerRef = useRef<number | null>(null);

  const activeStep = stepFromSearch(location.search)
    || (() => {
      const steps = Array.from(document.querySelectorAll<HTMLElement>(".setup-resend__step"));
      const activeIndex = steps.findIndex((step) => step.classList.contains("is-active"));
      return activeIndex >= 0 ? STEP_KEYS[activeIndex] : null;
    })()
    || "bases";

  const selectStep = useCallback((step: StepKey, skipped?: StepKey) => {
    const params = new URLSearchParams(location.search);
    params.set("section", step);
    if (skipped) params.set("skip", skipped);
    else params.delete("skip");
    navigate({ pathname: location.pathname, search: `?${params.toString()}` }, { replace: true });
  }, [location.pathname, location.search, navigate]);

  const refreshBaseReadiness = useCallback(() => {
    const summary = document.querySelector<HTMLElement>(
      ".setup-resend__step:first-child .setup-resend__step-heading small",
    )?.textContent?.trim() || "";
    const counts = summary.match(/(\d+)\s+active\s+·\s+(\d+)\s+located/i);
    const next: BaseReadiness = counts
      ? Number(counts[1]) > Number(counts[2]) ? "needs-location" : "ready"
      : /required before employment contracts/i.test(summary)
        ? "needs-base"
        : summary ? "unknown" : "loading";
    const previous = previousReadinessRef.current;
    previousReadinessRef.current = next;
    setBaseReadiness(next);

    const params = new URLSearchParams(location.search);
    const skipped = params.get("skip");
    const current = stepFromSearch(location.search);
    if (next === "needs-location" && skipped !== "bases" && current !== "bases") {
      params.set("section", "bases");
      params.delete("skip");
      navigate({ pathname: location.pathname, search: `?${params.toString()}` }, { replace: true });
      return;
    }
    if ((previous === "needs-base" || previous === "needs-location") && next === "ready" && (current || "bases") === "bases") {
      params.set("section", "departments");
      params.delete("skip");
      navigate({ pathname: location.pathname, search: `?${params.toString()}` }, { replace: true });
    }
  }, [location.pathname, location.search, navigate]);

  const scheduleRefresh = useCallback((delay = 250) => {
    if (refreshTimerRef.current != null) window.clearTimeout(refreshTimerRef.current);
    refreshTimerRef.current = window.setTimeout(() => {
      refreshTimerRef.current = null;
      refreshBaseReadiness();
    }, delay);
  }, [refreshBaseReadiness]);

  const alignActiveStep = useCallback(() => {
    const active = document.querySelector<HTMLElement>(".setup-resend__step.is-active");
    if (!active) return;
    active.scrollIntoView({
      behavior: prefersReducedMotion() ? "auto" : "smooth",
      block: "center",
      inline: "nearest",
    });
    const body = active.querySelector<HTMLElement>(".setup-resend__step-body");
    setPortalTarget(body?.querySelector(".setup-resend__step-navigation") ? null : body);
  }, []);

  const correctReadinessPresentation = useCallback(() => {
    const root = document.querySelector<HTMLElement>(".setup-resend");
    if (!root) return;
    root.dataset.baseReadiness = baseReadiness;
    if (baseReadiness !== "needs-location" && baseReadiness !== "ready") return;

    const steps = Array.from(root.querySelectorAll<HTMLElement>(".setup-resend__step"));
    const baseStep = steps[0];
    if (baseReadiness === "needs-location") {
      baseStep?.classList.remove("is-complete");
      baseStep?.classList.add("is-pending");
    } else {
      baseStep?.classList.remove("is-pending");
      baseStep?.classList.add("is-complete");
    }

    const completed = steps.slice(0, Math.max(0, steps.length - 1))
      .filter((step) => step.classList.contains("is-complete")).length;
    const coreCount = Math.max(1, steps.length - 1);
    const percent = Math.round((completed / coreCount) * 100);
    const context = root.querySelector<HTMLElement>(".setup-resend__context-progress");
    const label = context?.querySelector<HTMLElement>("span");
    const progress = context?.querySelector<HTMLProgressElement>("progress");
    const detail = context?.querySelector<HTMLElement>("small");
    if (label) label.textContent = `${percent}% ready`;
    if (progress) progress.value = percent;
    if (detail) detail.textContent = `${completed} of ${coreCount} core stages complete`;
  }, [baseReadiness]);

  useEffect(() => {
    refreshBaseReadiness();
    return () => {
      if (refreshTimerRef.current != null) window.clearTimeout(refreshTimerRef.current);
    };
  }, [refreshBaseReadiness]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      alignActiveStep();
      correctReadinessPresentation();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [alignActiveStep, correctReadinessPresentation, location.search]);

  useEffect(() => {
    const rail = document.querySelector(".setup-resend__rail");
    if (!rail) return;
    const observer = new MutationObserver(() => scheduleRefresh(60));
    observer.observe(rail, { childList: true, subtree: true, characterData: true });
    return () => observer.disconnect();
  }, [scheduleRefresh]);

  useEffect(() => {
    let dialogWasOpen = Boolean(document.querySelector(".setup-dialog-backdrop"));
    const observer = new MutationObserver(() => {
      const dialogOpen = Boolean(document.querySelector(".setup-dialog-backdrop"));
      if (dialogWasOpen && !dialogOpen) scheduleRefresh(450);
      dialogWasOpen = dialogOpen;
      window.requestAnimationFrame(() => {
        alignActiveStep();
        correctReadinessPresentation();
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });

    const clickHandler = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target : null;
      if (!target) return;
      if (target.closest(".setup-resend__header-actions button")) scheduleRefresh(350);
    };
    document.addEventListener("click", clickHandler);
    return () => {
      observer.disconnect();
      document.removeEventListener("click", clickHandler);
    };
  }, [alignActiveStep, correctReadinessPresentation, scheduleRefresh]);

  useEffect(() => () => {
    const root = document.querySelector<HTMLElement>(".setup-resend");
    if (root) delete root.dataset.baseReadiness;
  }, []);

  if (!portalTarget) return null;
  const index = STEP_KEYS.indexOf(activeStep);
  const nextStep = STEP_KEYS[Math.min(index + 1, STEP_KEYS.length - 1)];
  if (!nextStep || nextStep === activeStep) return null;

  return createPortal(
    <div className="setup-resend__step-navigation" aria-label="Setup stage navigation">
      <button type="button" onClick={() => selectStep(nextStep, activeStep)}>Skip for now</button>
      <Button type="button" size="sm" onClick={() => selectStep(nextStep)}>
        Continue <ArrowRight size={14} />
      </Button>
    </div>,
    portalTarget,
  );
};

export default AdminSetupWorkflowNavigator;
