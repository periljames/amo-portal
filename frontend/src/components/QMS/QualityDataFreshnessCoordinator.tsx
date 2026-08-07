import React, { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { apiRequest, qmsPath } from "../../services/apiClient";


const ACTIVE_REFRESH_INTERVAL_MS = 45_000;
const FOCUS_REFRESH_THRESHOLD_MS = 15_000;
const MUTATION_REFRESH_DELAYS_MS = [1_200, 4_500] as const;
const MUTATION_ACTION_PATTERN = /\b(save|create|update|submit|approve|issue|run|schedule|reschedule|delete|restore|close|reopen|verify|complete|publish|assign)\b/i;

function isQualityPath(pathname: string): boolean {
  return /^\/maintenance\/[^/]+\/quality(?:\/|$)/i.test(pathname);
}

function qualityAmoCode(pathname: string): string | null {
  const match = pathname.match(/^\/maintenance\/([^/]+)\/quality(?:\/|$)/i);
  return match ? decodeURIComponent(match[1]) : null;
}

function isQualityQueryKey(queryKey: readonly unknown[]): boolean {
  const marker = queryKey.map((part) => String(part)).join(":").toLowerCase();
  return [
    "qms",
    "quality",
    "audit",
    "finding",
    "car",
    "evidence",
    "management-review",
    "training-competence",
  ].some((value) => marker.includes(value));
}

function canonicalRefreshButton(): HTMLButtonElement | null {
  const candidates = Array.from(document.querySelectorAll<HTMLButtonElement>(
    ".qms-ops-header-actions button, .qms-ops-page .page-header__actions button",
  ));
  return candidates.find((button) => /^refresh$/i.test(button.textContent?.trim() || "") || /refresh/i.test(button.getAttribute("aria-label") || "")) || null;
}

function createScheduleButton(): HTMLButtonElement | null {
  return Array.from(document.querySelectorAll<HTMLButtonElement>(
    ".qms-page-grid button, .audit-shell-content button",
  )).find((button) => /^create schedule$/i.test(button.textContent?.trim() || "")) || null;
}

const QualityDataFreshnessCoordinator: React.FC = () => {
  const location = useLocation();
  const queryClient = useQueryClient();
  const lastRefreshAt = useRef(0);
  const pendingTimers = useRef<number[]>([]);
  const qualityActive = isQualityPath(location.pathname);

  useEffect(() => {
    return () => {
      pendingTimers.current.forEach((timer) => window.clearTimeout(timer));
      pendingTimers.current = [];
    };
  }, []);

  useEffect(() => {
    if (!qualityActive) return;
    const params = new URLSearchParams(location.search);
    const createIntent = params.get("create") === "1";
    const plannerRoute = /\/quality\/audits\/(?:plan|schedule)\/?$/i.test(location.pathname);
    if (!createIntent || !plannerRoute) return;

    let attempts = 0;
    const interval = window.setInterval(() => {
      attempts += 1;
      const button = createScheduleButton();
      if (button && !button.disabled) {
        button.click();
        params.delete("create");
        const suffix = params.toString();
        window.history.replaceState(window.history.state, "", `${location.pathname}${suffix ? `?${suffix}` : ""}`);
        window.clearInterval(interval);
      } else if (attempts >= 30) {
        window.clearInterval(interval);
      }
    }, 150);

    return () => window.clearInterval(interval);
  }, [location.pathname, location.search, qualityActive]);

  useEffect(() => {
    if (!qualityActive) return;

    const refresh = (force = false, includeAllActive = false) => {
      const now = Date.now();
      if (!force && now - lastRefreshAt.current < FOCUS_REFRESH_THRESHOLD_MS) return;
      lastRefreshAt.current = now;

      if (includeAllActive) {
        // Explicit user/system refreshes must bypass stale-time heuristics and
        // immediately execute every mounted query, including legacy keys that do
        // not contain a predictable QMS marker.
        void queryClient.refetchQueries({ type: "active" });
      } else {
        void queryClient.invalidateQueries({
          predicate: (query) => isQualityQueryKey(query.queryKey),
          refetchType: "active",
        });
      }

      window.requestAnimationFrame(() => {
        const button = canonicalRefreshButton();
        if (!button || button.disabled || button.getAttribute("aria-busy") === "true") return;
        button.click();
      });
    };

    const scheduleRefresh = (delay: number, force = true) => {
      const timer = window.setTimeout(() => {
        pendingTimers.current = pendingTimers.current.filter((candidate) => candidate !== timer);
        refresh(force);
      }, delay);
      pendingTimers.current.push(timer);
    };

    const onFocus = () => refresh(false);
    const onOnline = () => refresh(true);
    const onVisibility = () => {
      if (document.visibilityState === "visible") refresh(false);
    };
    const onExplicitRefresh = () => {
      refresh(true, true);
      const amoCode = qualityAmoCode(location.pathname);
      if (!amoCode) return;
      // A bounded authoritative probe guarantees that an explicit refresh always
      // reaches the tenant backend even when the current legacy page is not backed
      // by a mounted React Query observer. The page queries are still revalidated
      // above, and probe failure does not interrupt the workspace.
      void apiRequest<Record<string, unknown>>(qmsPath(amoCode, "/dashboard-lite"), {
        timeoutMs: 8_000,
        cacheTtlMs: 0,
      }).catch(() => undefined);
    };
    const onClick = (event: MouseEvent) => {
      const element = event.target instanceof Element ? event.target.closest<HTMLButtonElement>("button") : null;
      if (!element) return;
      if (!element.closest(".qms-shell, .qms-ops-page, .audit-shell-content, .quality-context-bar")) return;
      const label = [element.textContent, element.getAttribute("aria-label"), element.title].filter(Boolean).join(" ");
      if (!MUTATION_ACTION_PATTERN.test(label)) return;
      MUTATION_REFRESH_DELAYS_MS.forEach((delay) => scheduleRefresh(delay));
    };

    const initialTimer = window.setTimeout(() => refresh(true), 900);
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible" && navigator.onLine) refresh(true);
    }, ACTIVE_REFRESH_INTERVAL_MS);

    window.addEventListener("focus", onFocus);
    window.addEventListener("online", onOnline);
    window.addEventListener("amo:qms:refresh", onExplicitRefresh as EventListener);
    document.addEventListener("visibilitychange", onVisibility);
    document.addEventListener("click", onClick, true);

    return () => {
      window.clearTimeout(initialTimer);
      window.clearInterval(interval);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("online", onOnline);
      window.removeEventListener("amo:qms:refresh", onExplicitRefresh as EventListener);
      document.removeEventListener("visibilitychange", onVisibility);
      document.removeEventListener("click", onClick, true);
    };
  }, [location.pathname, location.search, qualityActive, queryClient]);

  return null;
};

export default QualityDataFreshnessCoordinator;
