// src/pages/AdminOverviewPage.tsx
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { getCachedUser, getContext } from "../services/auth";
import {
  fetchOverviewSummary,
  type OverviewIssue,
  type OverviewSummary,
} from "../services/adminOverview";

type UrlParams = {
  amoCode?: string;
};

type RefreshReason = "initial" | "retry" | "manual" | "interval";

const POLL_INTERVAL_MS = 60_000;
const MAX_RETRIES = 3;

const STATUS_LABELS: Record<"healthy" | "degraded" | "down", string> = {
  healthy: "Healthy",
  degraded: "Degraded",
  down: "Down",
};

const formatRelativeTime = (value?: string | null): string => {
  if (!value) return "Unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unavailable";
  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
};

const AdminOverviewPage: React.FC = () => {
  const { amoCode } = useParams<UrlParams>();
  const navigate = useNavigate();

  const currentUser = useMemo(() => getCachedUser(), []);
  const ctx = getContext();

  const isSuperuser = !!currentUser?.is_superuser;
  const isAmoAdmin = !!currentUser?.is_amo_admin;
  const canAccessAdmin = isSuperuser || isAmoAdmin;

  const [summary, setSummary] = useState<OverviewSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [lastSuccessAt, setLastSuccessAt] = useState<string | null>(null);

  const pollingTimerRef = useRef<number | null>(null);
  const pollingRetriesRef = useRef(0);
  const pollingStoppedRef = useRef(false);
  const pollingInFlightRef = useRef(false);
  const pollingRunnerRef = useRef<(reason: RefreshReason) => void>();

  useEffect(() => {
    if (!currentUser) return;
    if (canAccessAdmin) return;

    const dept = ctx.department;
    if (amoCode && dept) {
      navigate(`/maintenance/${amoCode}/${dept}`, { replace: true });
      return;
    }

    if (amoCode) {
      navigate(`/maintenance/${amoCode}/login`, { replace: true });
      return;
    }

    navigate("/login", { replace: true });
  }, [currentUser, canAccessAdmin, amoCode, ctx.department, navigate]);

  if (currentUser && !canAccessAdmin) {
    return null;
  }

  const clearPollingTimer = () => {
    if (pollingTimerRef.current) {
      window.clearTimeout(pollingTimerRef.current);
      pollingTimerRef.current = null;
    }
  };

  const handlePollingFailure = useCallback((message: string) => {
    const attempt = pollingRetriesRef.current;
    if (attempt < MAX_RETRIES) {
      const delay = Math.min(30_000, 3_000 * Math.pow(2, attempt));
      pollingRetriesRef.current += 1;
      setRefreshError(
        `Refresh failed. Retrying in ${Math.round(delay / 1000)}s.`
      );
      pollingTimerRef.current = window.setTimeout(() => {
        pollingRunnerRef.current?.("retry");
      }, delay);
      return;
    }
    pollingStoppedRef.current = true;
    setRefreshError("Refresh paused after repeated errors.");
  }, []);

  const runPolling = useCallback(
    async (reason: RefreshReason) => {
      if (pollingStoppedRef.current && reason !== "manual") return;
      if (pollingInFlightRef.current) return;
      pollingInFlightRef.current = true;
      clearPollingTimer();
      const isInitial = lastSuccessAt === null;
      if (isInitial) {
        setLoading(true);
      } else {
        setRefreshing(true);
      }

      try {
        const data = await fetchOverviewSummary();
        setSummary(data);
        setRefreshError(null);
        pollingRetriesRef.current = 0;
        pollingStoppedRef.current = false;
        setLastSuccessAt(data.system.last_checked_at);
        if (!pollingStoppedRef.current) {
          pollingTimerRef.current = window.setTimeout(() => {
            pollingRunnerRef.current?.("interval");
          }, POLL_INTERVAL_MS);
        }
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Unable to refresh overview.";
        handlePollingFailure(message);
      } finally {
        pollingInFlightRef.current = false;
        setLoading(false);
        setRefreshing(false);
      }
    },
    [handlePollingFailure, lastSuccessAt]
  );

  pollingRunnerRef.current = runPolling;

  useEffect(() => {
    if (!canAccessAdmin) return;
    runPolling("initial");
    return () => {
      clearPollingTimer();
    };
  }, [canAccessAdmin, runPolling]);

  const handleRetry = () => {
    pollingStoppedRef.current = false;
    pollingRetriesRef.current = 0;
    runPolling("manual");
  };

  const status = summary?.system.status || (refreshError ? "down" : "degraded");
  const statusLabel = STATUS_LABELS[status];
  const lastUpdatedLabel = summary?.system.last_checked_at
    ? formatRelativeTime(summary.system.last_checked_at)
    : "Unavailable";

  const issues = useMemo(() => {
    const list = summary?.issues ?? [];
    return list.slice(0, 6);
  }, [summary?.issues]);

  const resolveIssueRoute = (issue: OverviewIssue) => {
    if (!amoCode) return issue.route;
    return `/maintenance/${amoCode}${issue.route}`;
  };

  return (
    <DepartmentLayout
      amoCode={amoCode ?? "UNKNOWN"}
      activeDepartment="admin-overview"
      showPollingErrorBanner={false}
    >
      <header className="page-header admin-overview__header">
        <div className="admin-overview__header-row">
          <div>
            <h1 className="page-header__title">Overview</h1>
            <p className="admin-overview__subtitle">
              Status and next steps for the AMO admin console.
            </p>
          </div>
          <div className="admin-overview__status">
            <span className={`status-pill status-pill--${status}`}>{statusLabel}</span>
            <span className="admin-overview__updated">
              Last updated: {lastUpdatedLabel}
            </span>
          </div>
        </div>
        <div className="admin-overview__actions">
          {refreshError && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleRetry}
              disabled={refreshing}
            >
              Retry
            </button>
          )}
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => setDetailsOpen((prev) => !prev)}
          >
            {detailsOpen ? "Hide details" : "Details"}
          </button>
        </div>
        {detailsOpen && (
          <div className="admin-overview__details">
            <p>
              <strong>Status:</strong> {statusLabel}
            </p>
            <p>
              <strong>Last success:</strong> {lastSuccessAt ? formatRelativeTime(lastSuccessAt) : "Unavailable"}
            </p>
            {summary?.system.errors?.length ? (
              <ul>
                {summary.system.errors.map((err) => (
                  <li key={err}>{err}</li>
                ))}
              </ul>
            ) : (
              <p>No errors reported.</p>
            )}
          </div>
        )}
      </header>

      <section className="page-section admin-overview__grid">
        <div className="admin-overview__panel">
          <div className="admin-overview__panel-header">
            <h2>Needs attention</h2>
            {loading ? <span>Loading…</span> : <span>{issues.length} items</span>}
          </div>
          {issues.length === 0 ? (
            <p className="page-section__body">No urgent actions right now.</p>
          ) : (
            <ul className="admin-overview__issue-list">
              {issues.map((issue) => (
                <li key={issue.key}>
                  <div className="admin-overview__issue-main">
                    <span
                      className={`severity-dot severity-dot--${issue.severity}`}
                    />
                    <div>
                      <p>{issue.label}</p>
                      <span className="admin-overview__issue-count">
                        {issue.count ?? "—"}
                      </span>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => navigate(resolveIssueRoute(issue))}
                  >
                    Review
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="admin-overview__panel admin-overview__panel--compact">
          <div className="admin-overview__panel-header">
            <h2>Recent activity</h2>
          </div>
          {!summary?.recent_activity_available ? (
            <p className="page-section__body">Audit feed unavailable.</p>
          ) : summary?.recent_activity.length ? (
            <ul className="admin-overview__activity-list">
              {summary.recent_activity.slice(0, 5).map((event, index) => (
                <li key={`${event.action}-${index}`}>
                  <div>
                    <strong>{event.action}</strong>
                    <p>
                      {event.entity_type} • {formatRelativeTime(event.occurred_at || null)}
                    </p>
                  </div>
                  <span className="text-muted">{event.actor_user_id || "System"}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="page-section__body">No recent activity recorded.</p>
          )}
        </div>
      </section>
    </DepartmentLayout>
  );
};

export default AdminOverviewPage;
