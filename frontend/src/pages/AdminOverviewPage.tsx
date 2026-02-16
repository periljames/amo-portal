// src/pages/AdminOverviewPage.tsx
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import { Badge, Button, PageHeader, Panel, StatusPill } from "../components/UI/Admin";
import { usePortalRuntimeMode } from "../hooks/usePortalRuntimeMode";
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

const DEFAULT_POLL_INTERVAL_MS = 60_000;
const SUPERUSER_POLL_INTERVAL_MS = 5 * 60_000;
const MAX_RETRIES = 3;

const STATUS_LABELS: Record<
  "healthy" | "degraded" | "down" | "paused" | "unknown",
  string
> = {
  healthy: "Healthy",
  degraded: "Degraded",
  down: "Down",
  paused: "Paused",
  unknown: "Unknown",
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
  const { isGoLive } = usePortalRuntimeMode();
  const ctx = getContext();

  const isSuperuser = !!currentUser?.is_superuser;
  const isAmoAdmin = !!currentUser?.is_amo_admin;
  const canAccessAdmin = isSuperuser || isAmoAdmin;

  const [summary, setSummary] = useState<OverviewSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);
  const [activityExpanded, setActivityExpanded] = useState(false);
  const summaryRef = useRef<OverviewSummary | null>(null);

  const pollingTimerRef = useRef<number | null>(null);
  const pollingRetriesRef = useRef(0);
  const pollingStoppedRef = useRef(false);
  const pollingInFlightRef = useRef(false);
  const pollingRunnerRef = useRef<((reason: RefreshReason) => void) | undefined>(undefined);
  const pollIntervalMs = isSuperuser
    ? SUPERUSER_POLL_INTERVAL_MS
    : DEFAULT_POLL_INTERVAL_MS;

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
        `${message} Retrying in ${Math.round(delay / 1000)}s.`
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
      const isInitial = summaryRef.current === null;
      if (isInitial) {
        setLoading(true);
      } else {
        setRefreshing(true);
      }

      try {
        const data = await fetchOverviewSummary();
        setSummary(data);
        summaryRef.current = data;
        setRefreshError(null);
        pollingRetriesRef.current = 0;
        pollingStoppedRef.current = false;
        if (!pollingStoppedRef.current) {
          pollingTimerRef.current = window.setTimeout(() => {
            pollingRunnerRef.current?.("interval");
          }, pollIntervalMs);
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
    [handlePollingFailure, pollIntervalMs]
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

  const rawStatus = summary?.system.status || (refreshError ? "down" : "degraded");
  const statusTone: "healthy" | "degraded" | "down" | "unknown" =
    rawStatus === "healthy" || rawStatus === "degraded" || rawStatus === "down"
      ? rawStatus
      : "unknown";
  const statusLabel = STATUS_LABELS[statusTone];
  const lastUpdatedLabel = summary?.system.last_checked_at
    ? formatRelativeTime(summary.system.last_checked_at)
    : "Unavailable";
  const refreshStateLabel = loading
    ? "Loading…"
    : refreshing
      ? "Refreshing…"
      : refreshError || summary?.system.refresh_paused
        ? "Refresh paused"
        : "Auto-refreshing";
  const showRetry =
    statusTone !== "healthy" || !!refreshError || summary?.system.refresh_paused;

  const issues = useMemo(() => {
    const list = summary?.issues ?? [];
    return list.slice(0, 6);
  }, [summary?.issues]);

  const resolveIssueRoute = (issue: OverviewIssue) => {
    if (!amoCode) return issue.route;
    return `/maintenance/${amoCode}${issue.route}`;
  };

  const activityItems = summary?.recent_activity ?? [];
  const activityList = activityExpanded
    ? activityItems
    : activityItems.slice(0, 5);
  const attentionItems = issues.slice(0, 3);

  return (
    <DepartmentLayout
      amoCode={amoCode ?? "UNKNOWN"}
      activeDepartment="admin-overview"
      showPollingErrorBanner={false}
    >
      <div className="admin-page admin-overview">
        <PageHeader
          title="Overview"
          subtitle="System status and the next actions that need attention."
          actions={
            <div className="admin-overview__header-actions">
              <StatusPill status={statusTone} label={`System ${statusLabel}`} />
              <button
                type="button"
                className="admin-icon-btn"
                onClick={handleRetry}
                disabled={refreshing}
                aria-label="Retry refresh"
                title={showRetry ? "Retry refresh" : "Refresh status"}
              >
                ↻
              </button>
              <a className="admin-link" href="#system-status">
                Details
              </a>
            </div>
          }
        />

        <div className="admin-overview__grid admin-overview__grid--summary">
          <Panel
            title="Flight deck · Go Live"
            subtitle="Garmin-style runtime confirmation"
            actions={<Badge tone={isGoLive ? "success" : "warning"}>{isGoLive ? "LIVE" : "DEMO"}</Badge>}
          >
            <div className="go-live-radar">
              <div className={`go-live-radar__scope ${isGoLive ? "is-live" : "is-demo"}`} aria-hidden="true">
                <span className="go-live-radar__ring" />
                <span className="go-live-radar__ring go-live-radar__ring--inner" />
                <span className="go-live-radar__sweep" />
              </div>
              <div className="go-live-radar__stats">
                <div>
                  <p>Runtime mode</p>
                  <strong>{isGoLive ? "LIVE / PRODUCTION" : "DEMO / SANDBOX"}</strong>
                </div>
                <div>
                  <p>Data pipeline</p>
                  <strong>{isGoLive ? "Direct DB/API" : "Mock fallback allowed"}</strong>
                </div>
                <div>
                  <p>Last backend check</p>
                  <strong>{lastUpdatedLabel}</strong>
                </div>
                <div>
                  <p>Control</p>
                  <Button type="button" variant="secondary" onClick={() => navigate(`/maintenance/${amoCode ?? "UNKNOWN"}/admin-users`)}>
                    Open Go Live master
                  </Button>
                </div>
              </div>
            </div>
          </Panel>

          <Panel
            title="Needs attention"
            actions={
              <span className="admin-muted">
                {loading ? "Loading…" : `${issues.length} items`}
              </span>
            }
          >
            {attentionItems.length === 0 ? (
              <span className="admin-muted">
                {statusTone === "down"
                  ? "Backend unavailable—cannot compute issues."
                  : "No urgent actions right now."}
              </span>
            ) : (
              <ul className="admin-list admin-overview__attention-list">
                {attentionItems.map((issue) => (
                  <li key={issue.key}>
                    <div className="admin-list__row admin-overview__queue-row">
                      <div className="admin-list__row-main admin-overview__queue-main">
                        <span className={`severity-dot severity-dot--${issue.severity}`} />
                        <span className="admin-overview__queue-label">{issue.label}</span>
                      </div>
                      <div className="admin-list__row-meta admin-overview__queue-actions">
                        <Badge
                          tone={
                            issue.severity === "critical"
                              ? "danger"
                              : issue.severity === "warning"
                                ? "warning"
                                : "info"
                          }
                          size="sm"
                        >
                          {issue.count ?? "—"}
                        </Badge>
                        <button
                          type="button"
                          className="admin-link-btn"
                          onClick={() => navigate(resolveIssueRoute(issue))}
                        >
                          Go to module
                        </button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel
            title="Recent activity"
            actions={
              summary?.recent_activity_available && activityItems.length > 5 ? (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setActivityExpanded((prev) => !prev)}
                >
                  {activityExpanded ? "Collapse" : "View all"}
                </Button>
              ) : null
            }
            compact
          >
            {!summary?.recent_activity_available ? (
              <span className="admin-muted">Audit feed unavailable.</span>
            ) : activityList.length ? (
              <ul className="admin-list">
                {activityList.map((event, index) => (
                  <li key={`${event.action}-${index}`}>
                    <div className="admin-list__row admin-overview__activity-row">
                      <div>
                        <strong>{event.action}</strong>
                        <div className="admin-muted">
                          {event.entity_type} • {formatRelativeTime(event.occurred_at || null)}
                        </div>
                      </div>
                      <span className="admin-muted">{event.actor_user_id || "System"}</span>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <span className="admin-muted">No recent activity recorded.</span>
            )}
          </Panel>

          <Panel title="System status" compact>
            <dl className="admin-overview__status-list" id="system-status">
              <div>
                <dt>Status</dt>
                <dd>{statusLabel}</dd>
              </div>
              <div>
                <dt>Last check</dt>
                <dd>{lastUpdatedLabel}</dd>
              </div>
              <div>
                <dt>Refresh</dt>
                <dd>{refreshStateLabel}</dd>
              </div>
              <div>
                <dt>Queue</dt>
                <dd>{loading ? "—" : `${issues.length} items`}</dd>
              </div>
            </dl>
          </Panel>
        </div>
      </div>
    </DepartmentLayout>
  );
};

export default AdminOverviewPage;
