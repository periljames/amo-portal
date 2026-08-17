import React, { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { apiRequest, qmsPath } from "../../services/apiClient";
import { auditSessionStageFromPath } from "../../features/qms/auditSession/auditSessionRoutes";
import { replayOfflineMutations } from "../../services/offlinePersistence";
import { startQmsAuditRealtimeStream, type QmsAuditRealtimeEvent } from "../../services/qmsAuditRealtime";

const ACTIVE_REFRESH_INTERVAL_MS = 45_000;
const FOCUS_REFRESH_THRESHOLD_MS = 15_000;
const MUTATION_REFRESH_DELAYS_MS = [1_200, 4_500] as const;
const MUTATION_ACTION_PATTERN = /\b(save|create|update|submit|approve|issue|run|schedule|reschedule|delete|restore|close|reopen|verify|complete|publish|assign)\b/i;

function isQualityPath(pathname: string): boolean {
  return /^\/maintenance\/[^/]+\/(?:quality|qms)(?:\/|$)/i.test(pathname);
}

function qualityAmoCode(pathname: string): string | null {
  const match = pathname.match(/^\/maintenance\/([^/]+)\/(?:quality|qms)(?:\/|$)/i);
  return match ? decodeURIComponent(match[1]) : null;
}

function auditOccurrenceKey(pathname: string): string | null {
  const match = pathname.match(/^\/maintenance\/[^/]+\/(?:quality|qms)\/audits\/([^/]+)\/(?:setup|prepare|live|closing|follow-up|archive)\/?$/i);
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

function queryKeyContainsAny(queryKey: readonly unknown[], markers: Set<string>): boolean {
  if (!markers.size) return false;
  const serialised = queryKey.map((part) => String(part).toLowerCase()).join(":");
  return Array.from(markers).some((marker) => marker && serialised.includes(marker.toLowerCase()));
}

function realtimeAuditId(event: QmsAuditRealtimeEvent): string | null {
  if (!event.data || typeof event.data !== "object") return null;
  const payload = event.data as Record<string, unknown>;
  const metadata = payload.metadata && typeof payload.metadata === "object" ? payload.metadata as Record<string, unknown> : {};
  for (const value of [metadata.auditId, metadata.audit_id, payload.auditId, payload.audit_id]) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}

function isQualityRealtimeEvent(event: QmsAuditRealtimeEvent): boolean {
  if (event.event === "reset") return true;
  const payload = event.data && typeof event.data === "object" ? event.data as Record<string, unknown> : {};
  const type = String(payload.type || event.event || "").toLowerCase();
  const entityType = String(payload.entityType || "").toLowerCase();
  const metadata = payload.metadata && typeof payload.metadata === "object" ? payload.metadata as Record<string, unknown> : {};
  const module = String(metadata.module || "").toLowerCase();
  return module === "quality"
    || type.startsWith("qms.")
    || type.startsWith("quality.")
    || entityType.startsWith("qms.")
    || entityType.startsWith("quality.");
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
  const auditSessionStage = auditSessionStageFromPath(location.pathname);
  const auditOccurrenceActive = auditSessionStage !== null;
  const liveAuditActive = auditSessionStage === "live";
  const occurrenceKey = auditOccurrenceKey(location.pathname);

  const occurrenceMarkers = (eventAuditId?: string | null): Set<string> => {
    const markers = new Set<string>();
    if (occurrenceKey) markers.add(occurrenceKey);
    if (eventAuditId) markers.add(eventAuditId);
    if (!occurrenceKey) return markers;

    for (const query of queryClient.getQueryCache().getAll()) {
      const data = query.state.data;
      if (!data || typeof data !== "object") continue;
      const root = data as Record<string, unknown>;
      const candidate = root.audit && typeof root.audit === "object" ? root.audit as Record<string, unknown> : root;
      const id = typeof candidate.id === "string" ? candidate.id : typeof candidate.audit_id === "string" ? candidate.audit_id : null;
      const ref = typeof candidate.audit_ref === "string" ? candidate.audit_ref : null;
      if (id && (id === occurrenceKey || ref?.toLowerCase() === occurrenceKey.toLowerCase())) markers.add(id);
    }
    return markers;
  };

  const invalidateOccurrence = (markers: Set<string>) => {
    if (!markers.size) return Promise.resolve();
    return queryClient.invalidateQueries({
      predicate: (query) => isQualityQueryKey(query.queryKey) && queryKeyContainsAny(query.queryKey, markers),
      refetchType: "active",
    });
  };

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
    const plannerRoute = /\/(?:quality|qms)\/audits\/(?:plan|schedule)\/?$/i.test(location.pathname);
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
    if (!qualityActive || !auditOccurrenceActive) return;
    const stop = startQmsAuditRealtimeStream({
      onState: (state) => {
        document.documentElement.dataset.qmsRealtimeState = state;
      },
      onEvent: (event) => {
        if (!isQualityRealtimeEvent(event)) return;
        if (event.event === "reset") {
          // A reset means the server's replay window cannot prove which events
          // were missed. This is the one case where active queries are refetched.
          void queryClient.refetchQueries({ type: "active" });
        } else {
          const eventAuditId = realtimeAuditId(event);
          void invalidateOccurrence(occurrenceMarkers(eventAuditId));
        }
        window.dispatchEvent(new CustomEvent("amo:qms:realtime", { detail: event.data }));
      },
    });
    return () => {
      stop();
      delete document.documentElement.dataset.qmsRealtimeState;
    };
  }, [auditOccurrenceActive, occurrenceKey, qualityActive, queryClient]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!qualityActive) return;

    const refresh = (force = false, includeAllActive = false) => {
      const now = Date.now();
      if (!force && now - lastRefreshAt.current < FOCUS_REFRESH_THRESHOLD_MS) return;
      lastRefreshAt.current = now;

      if (auditOccurrenceActive) {
        void invalidateOccurrence(occurrenceMarkers());
      } else if (includeAllActive) {
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

    const replayAndRefresh = async () => {
      if (!liveAuditActive) {
        refresh(true);
        return;
      }
      try {
        await replayOfflineMutations();
        refresh(true);
      } catch (error) {
        console.warn("[qms-offline] replay did not complete", error);
        refresh(true);
      }
    };

    const scheduleRefresh = (delay: number, force = true) => {
      const timer = window.setTimeout(() => {
        pendingTimers.current = pendingTimers.current.filter((candidate) => candidate !== timer);
        refresh(force);
      }, delay);
      pendingTimers.current.push(timer);
    };

    const onFocus = () => refresh(false);
    const onOnline = () => { void replayAndRefresh(); };
    const onVisibility = () => {
      if (document.visibilityState === "visible") refresh(false);
    };
    const onExplicitRefresh = () => {
      refresh(true, !auditOccurrenceActive);
      const amoCode = qualityAmoCode(location.pathname);
      if (!amoCode || auditOccurrenceActive) return;
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

    const initialTimer = window.setTimeout(() => {
      if (navigator.onLine) void replayAndRefresh();
      else refresh(true);
    }, 900);
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
  }, [auditOccurrenceActive, liveAuditActive, location.pathname, location.search, occurrenceKey, qualityActive, queryClient]); // eslint-disable-line react-hooks/exhaustive-deps

  return null;
};

export default QualityDataFreshnessCoordinator;
