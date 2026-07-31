import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { platformConsoleApi, type PlatformConsoleBootstrap } from "../../services/platformConsole";
import { platformApi, type PlatformCommandJob } from "../../services/platformControl";
import "../../styles/platform-dashboard.css";
import "../../styles/platform-dashboard-tuning.css";
import { DataTable, ErrorState, PlatformShell, StatusBadge } from "./components/PlatformShared";
import { usePlatformData } from "./components/usePlatformData";

const compactNumber = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });
const integerNumber = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });

function money(cents?: number, currency = "USD") {
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    }).format((cents ?? 0) / 100);
  } catch {
    return `$${integerNumber.format((cents ?? 0) / 100)}`;
  }
}

function percentage(value?: number) {
  return `${Math.round((value ?? 0) * 10_000) / 100}%`;
}

function readableDate(value?: string | null) {
  if (!value) return "No snapshot yet";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function relativeTime(value?: string | null) {
  if (!value) return "Not run";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return readableDate(value);
  const seconds = Math.max(0, Math.round((Date.now() - parsed.getTime()) / 1000));
  if (seconds < 60) return "Just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function latencyState(value?: number | null) {
  if (value === undefined || value === null) return "neutral";
  if (value <= 500) return "good";
  if (value <= 1_000) return "watch";
  return "slow";
}

function bitrate(bytesPerSecond?: number | null) {
  if (bytesPerSecond === undefined || bytesPerSecond === null || !Number.isFinite(bytesPerSecond)) return "Warming up";
  const bits = Math.max(0, bytesPerSecond) * 8;
  if (bits >= 1_000_000_000) return `${(bits / 1_000_000_000).toFixed(bits >= 10_000_000_000 ? 1 : 2)} Gb/s`;
  if (bits >= 1_000_000) return `${(bits / 1_000_000).toFixed(bits >= 10_000_000 ? 1 : 2)} Mb/s`;
  if (bits >= 1_000) return `${(bits / 1_000).toFixed(bits >= 10_000 ? 1 : 2)} Kb/s`;
  return `${integerNumber.format(bits)} b/s`;
}

function byteSize(bytes?: number | null) {
  if (bytes === undefined || bytes === null || !Number.isFinite(bytes)) return "—";
  const value = Math.max(0, bytes);
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(2)} GB`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} MB`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)} KB`;
  return `${integerNumber.format(value)} B`;
}

type DashboardSnapshot = PlatformConsoleBootstrap & {
  platform_status?: string;
  active_tenants?: number;
  inactive_tenants?: number;
  locked_tenants?: number;
  trialing_tenants?: number;
  platform_mrr?: number;
  platform_arr?: number;
  currency?: string;
  total_users?: number;
  api_requests_last_60m?: number;
  api_error_rate_last_60m?: number;
  p95_latency_ms?: number | null;
  p99_latency_ms?: number | null;
  active_support_tickets?: number;
  open_support_tickets?: number;
  critical_security_alerts?: number;
  overdue_invoices?: number;
  queue_depth?: number;
  configured_providers?: number;
  provider_count?: number;
  pending_fiscalizations?: number;
  email_status?: string;
  email_latency_ms?: number | null;
  last_health_probe_at?: string | null;
  data_mode?: string;
};

type PlatformAlert = {
  id: string;
  severity?: string;
  title?: string;
  category?: string;
  created_at?: string;
};

type MetricTrendPoint = {
  at: string;
  requests?: number;
  requests_per_minute?: number;
  errors?: number;
  error_rate?: number;
  avg_latency_ms?: number | null;
  p95_latency_ms?: number | null;
  p99_latency_ms?: number | null;
};

type BandwidthTrendPoint = {
  at: string;
  ingress_bytes_per_second?: number | null;
  egress_bytes_per_second?: number | null;
  total_bytes_per_second?: number | null;
};

type BandwidthSummary = {
  available?: boolean;
  warming_up?: boolean;
  scope?: string;
  source?: string;
  interface_count?: number;
  current_ingress_bytes_per_second?: number | null;
  current_egress_bytes_per_second?: number | null;
  current_total_bytes_per_second?: number | null;
  peak_total_bytes_per_second?: number | null;
  average_total_bytes_per_second?: number | null;
  transfer_bytes_window?: number;
  window_minutes?: number;
  sample_count?: number;
  sample_interval_seconds?: number | null;
  series?: BandwidthTrendPoint[];
  note?: string;
};

type MetricsTelemetry = {
  window_minutes?: number;
  requests_last_60m?: number | null;
  requests_in_window?: number;
  requests_per_minute?: number;
  current_requests_per_minute?: number;
  peak_requests_per_minute?: number;
  error_rate?: number;
  p95_latency_ms?: number | null;
  p99_latency_ms?: number | null;
  trend_series?: MetricTrendPoint[];
  bandwidth?: BandwidthSummary;
  metric_coverage?: {
    persisted_route_rows?: number;
    live_route_rows?: number;
    points?: number;
    oldest_at?: string | null;
    newest_at?: string | null;
  };
};

type SimpleTrendPoint = { at: string; value: number | null };
type TrendTone = "blue" | "green" | "amber" | "red" | "purple" | "cyan";
type TrendPreference = "higher" | "lower" | "neutral";
type TrendWindow = 15 | 60;

type HealthRowProps = {
  label: string;
  value: React.ReactNode;
  detail: string;
  state?: "good" | "watch" | "slow" | "neutral";
};

function HealthRow({ label, value, detail, state = "neutral" }: HealthRowProps) {
  return (
    <div className="platform-health-row" data-state={state}>
      <span className="platform-health-row__indicator" />
      <div>
        <strong>{label}</strong>
        <small>{detail}</small>
      </div>
      <b>{value}</b>
    </div>
  );
}

function filterTrendWindow(points: SimpleTrendPoint[], minutes: TrendWindow) {
  const cutoff = Date.now() - minutes * 60_000;
  return points.filter((point) => {
    const value = new Date(point.at).getTime();
    return Number.isNaN(value) || value >= cutoff;
  });
}

function appendTrend(points: SimpleTrendPoint[], point: SimpleTrendPoint) {
  const last = points[points.length - 1];
  if (last?.at === point.at) return points;
  return [...points, point].slice(-240);
}

function finiteTrend(points: SimpleTrendPoint[]) {
  return points
    .map((point, index) => ({ ...point, index }))
    .filter((point): point is SimpleTrendPoint & { value: number; index: number } => typeof point.value === "number" && Number.isFinite(point.value));
}

function Sparkline({ points, label }: { points: SimpleTrendPoint[]; label: string }) {
  const finite = finiteTrend(points);
  if (finite.length < 2) {
    return <div className="platform-sparkline platform-sparkline--empty" aria-label={`${label}: waiting for more samples`}><span>Collecting live samples</span></div>;
  }

  const values = finite.map((point) => point.value);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const range = maximum - minimum || Math.max(1, Math.abs(maximum) * 0.08);
  const width = 180;
  const height = 46;
  const top = 4;
  const bottom = height - 4;
  const xStep = width / Math.max(1, finite.length - 1);
  const coordinates = finite.map((point, index) => {
    const x = index * xStep;
    const y = bottom - ((point.value - minimum) / range) * (bottom - top);
    return { x, y, point };
  });
  const line = coordinates.map(({ x, y }, index) => `${index ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
  const area = `${line} L${width},${height} L0,${height} Z`;
  const last = coordinates[coordinates.length - 1];

  return (
    <svg className="platform-sparkline" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${label} live trend from ${minimum} to ${maximum}`} preserveAspectRatio="none">
      <title>{`${label}: ${finite.length} real samples. Latest ${last.point.value}.`}</title>
      <path className="platform-sparkline__area" d={area} />
      <path className="platform-sparkline__line" d={line} />
      <circle className="platform-sparkline__point" cx={last.x} cy={last.y} r="2.8" />
    </svg>
  );
}

function trendChange(points: SimpleTrendPoint[]) {
  const finite = finiteTrend(points);
  if (finite.length < 2) return null;
  const first = finite[0].value;
  const last = finite[finite.length - 1].value;
  const difference = last - first;
  const percent = first === 0 ? null : (difference / Math.abs(first)) * 100;
  return { difference, percent };
}

function TrendMetricCard({
  label,
  value,
  caption,
  mark,
  tone,
  points,
  preference = "neutral",
  window,
}: {
  label: string;
  value: React.ReactNode;
  caption: React.ReactNode;
  mark: string;
  tone: TrendTone;
  points: SimpleTrendPoint[];
  preference?: TrendPreference;
  window: TrendWindow;
}) {
  const visible = filterTrendWindow(points, window);
  const change = trendChange(visible);
  const direction = !change || Math.abs(change.difference) < Number.EPSILON ? "flat" : change.difference > 0 ? "up" : "down";
  const healthy = direction === "flat" || preference === "neutral" || (preference === "higher" ? direction === "up" : direction === "down");
  const changeLabel = !change
    ? "Live"
    : change.percent === null
      ? change.difference === 0 ? "Flat" : "New"
      : `${change.percent > 0 ? "+" : ""}${change.percent.toFixed(Math.abs(change.percent) >= 10 ? 0 : 1)}%`;

  return (
    <article className={`platform-trend-card platform-trend-card--${tone}`} data-direction={direction} data-healthy={healthy ? "true" : "false"}>
      <header>
        <span>{label}</span>
        <b>{mark}</b>
      </header>
      <div className="platform-trend-card__value">{value}</div>
      <Sparkline points={visible} label={label} />
      <footer>
        <span>{caption}</span>
        <strong>{changeLabel}</strong>
      </footer>
    </article>
  );
}

export default function PlatformDashboardPage() {
  const snapshot = usePlatformData<DashboardSnapshot>(
    () => platformConsoleApi.bootstrap() as Promise<DashboardSnapshot>,
    [],
    { pollMs: 15_000 },
  );
  const telemetry = usePlatformData<MetricsTelemetry>(
    () => platformApi.metricsSummary() as Promise<MetricsTelemetry>,
    [],
    { pollMs: 10_000 },
  );
  const jobs = usePlatformData(() => platformApi.recentJobs(), [], { pollMs: 20_000 });
  const alerts = usePlatformData(() => platformApi.recentAlerts(), [], { pollMs: 20_000 });
  const [probing, setProbing] = useState(false);
  const [probeError, setProbeError] = useState<string | null>(null);
  const [trendWindow, setTrendWindow] = useState<TrendWindow>(60);
  const [sessionTrends, setSessionTrends] = useState<Record<string, SimpleTrendPoint[]>>({});
  const lastSnapshotAt = useRef<string | null>(null);

  const data = snapshot.data ?? {};
  const metrics = telemetry.data ?? {};
  const bandwidth = metrics.bandwidth ?? {};
  const recentJobs = (jobs.data?.items ?? []) as PlatformCommandJob[];
  const recentAlerts = (alerts.data?.items ?? []) as PlatformAlert[];
  const apiErrorRate = Number(metrics.error_rate ?? data.api_error_rate_last_60m ?? 0);
  const apiSuccessRate = Math.max(0, 1 - apiErrorRate);
  const platformStatus = String(data.platform_status ?? "UNKNOWN").toUpperCase();
  const openSupport = Number(data.open_support_tickets ?? data.active_support_tickets ?? 0);
  const providerCount = Number(data.provider_count ?? 0);
  const configuredProviders = Number(data.configured_providers ?? 0);
  const trafficTrend = metrics.trend_series ?? [];
  const networkTrend = bandwidth.series ?? [];

  const attentionCount = useMemo(
    () => Number(data.critical_security_alerts ?? 0)
      + openSupport
      + Number(data.overdue_invoices ?? 0)
      + Number(data.pending_fiscalizations ?? 0),
    [data.critical_security_alerts, data.overdue_invoices, data.pending_fiscalizations, openSupport],
  );

  useEffect(() => {
    const at = data.generated_at;
    if (!at || at === lastSnapshotAt.current) return;
    lastSnapshotAt.current = at;
    const values: Record<string, number> = {
      tenants: Number(data.active_tenants ?? 0),
      mrr: Number(data.platform_mrr ?? 0),
      users: Number(data.total_users ?? 0),
      attention: attentionCount,
    };
    setSessionTrends((current) => {
      const next = { ...current };
      Object.entries(values).forEach(([key, value]) => {
        next[key] = appendTrend(current[key] ?? [], { at, value });
      });
      return next;
    });
  }, [attentionCount, data.active_tenants, data.generated_at, data.platform_mrr, data.total_users]);

  const requestTrend = useMemo<SimpleTrendPoint[]>(
    () => trafficTrend.map((point) => ({ at: point.at, value: Number(point.requests_per_minute ?? point.requests ?? 0) })),
    [trafficTrend],
  );
  const errorTrend = useMemo<SimpleTrendPoint[]>(
    () => trafficTrend.map((point) => ({ at: point.at, value: Number(point.error_rate ?? 0) * 100 })),
    [trafficTrend],
  );
  const latencyTrend = useMemo<SimpleTrendPoint[]>(
    () => trafficTrend.map((point) => ({ at: point.at, value: point.p95_latency_ms ?? null })),
    [trafficTrend],
  );
  const bandwidthTrend = useMemo<SimpleTrendPoint[]>(
    () => networkTrend.map((point) => ({ at: point.at, value: point.total_bytes_per_second ?? null })),
    [networkTrend],
  );

  const runProbe = async () => {
    setProbing(true);
    setProbeError(null);
    try {
      await platformApi.runDiagnostics();
      snapshot.reload();
      telemetry.reload();
      jobs.reload();
      alerts.reload();
    } catch (error) {
      setProbeError(error instanceof Error ? error.message : String(error));
    } finally {
      setProbing(false);
    }
  };

  const statusTitle = platformStatus === "HEALTHY"
    ? "Platform operating normally"
    : platformStatus === "UNKNOWN"
      ? "Health snapshot required"
      : `Platform status: ${platformStatus}`;

  const currentIngress = Number(bandwidth.current_ingress_bytes_per_second ?? 0);
  const currentEgress = Number(bandwidth.current_egress_bytes_per_second ?? 0);
  const flowMaximum = Math.max(1, currentIngress, currentEgress);
  const currentRequestRate = Number(metrics.current_requests_per_minute ?? metrics.requests_per_minute ?? 0);
  const averageRequestRate = Number(metrics.requests_per_minute ?? 0);

  return (
    <PlatformShell
      title="Platform Control"
      subtitle="Live operating view for tenant health, revenue, throughput, bandwidth, providers, support, security and privileged platform work."
      actions={(
        <button className="platform-btn primary" disabled={probing} onClick={runProbe}>
          {probing ? "Running probe…" : "Run health probe"}
        </button>
      )}
    >
      <div className="platform-dashboard">
        {snapshot.error ? <ErrorState error={snapshot.error} retry={snapshot.reload} /> : null}
        {telemetry.error ? <ErrorState error={telemetry.error} retry={telemetry.reload} /> : null}
        {probeError ? <ErrorState error={probeError} retry={runProbe} /> : null}

        <section className="platform-dashboard-status" data-status={platformStatus.toLowerCase()}>
          <div className="platform-dashboard-status__main">
            <span className="platform-dashboard-status__pulse" />
            <div>
              <span className="platform-eyebrow">Live control plane</span>
              <h2>{statusTitle}</h2>
              <p>Real platform telemetry only. Route trends merge persisted one-minute rollups with current in-memory traffic; bandwidth is measured from the API host interfaces.</p>
            </div>
          </div>
          <div className="platform-dashboard-status__meta">
            <StatusBadge value={data.platform_status} />
            <span><small>Last probe</small><strong>{relativeTime(data.last_health_probe_at)}</strong></span>
            <span><small>Snapshot</small><strong>{readableDate(data.generated_at)}</strong></span>
            <span><small>Trend points</small><strong>{metrics.metric_coverage?.points ?? 0}</strong></span>
            <span><small>Network source</small><strong>{bandwidth.available ? `${bandwidth.interface_count ?? 0} interfaces` : "Unavailable"}</strong></span>
          </div>
        </section>

        <section className="platform-dashboard-metric-section" aria-labelledby="headline-metrics-title">
          <header className="platform-dashboard-section-header">
            <div>
              <span>Live trend cards</span>
              <h2 id="headline-metrics-title">Platform overview</h2>
              <p>Sparklines use real samples only. Tenant, revenue, user and attention cards build from this console session; traffic metrics include persisted route rollups.</p>
            </div>
            <div className="platform-trend-window" role="group" aria-label="Trend time window">
              <button type="button" className={trendWindow === 15 ? "active" : undefined} onClick={() => setTrendWindow(15)}>15 min</button>
              <button type="button" className={trendWindow === 60 ? "active" : undefined} onClick={() => setTrendWindow(60)}>60 min</button>
            </div>
          </header>

          <div className="platform-dashboard-metrics">
            <TrendMetricCard
              label="Active tenants"
              value={integerNumber.format(Number(data.active_tenants ?? 0))}
              caption={`${data.locked_tenants ?? 0} locked · ${data.trialing_tenants ?? 0} trialing`}
              tone="blue"
              mark="TEN"
              points={sessionTrends.tenants ?? []}
              preference="higher"
              window={trendWindow}
            />
            <TrendMetricCard
              label="Platform MRR"
              value={money(data.platform_mrr, data.currency)}
              caption={`ARR ${money(data.platform_arr, data.currency)}`}
              tone="green"
              mark="REV"
              points={sessionTrends.mrr ?? []}
              preference="higher"
              window={trendWindow}
            />
            <TrendMetricCard
              label="Global users"
              value={compactNumber.format(Number(data.total_users ?? 0))}
              caption="Across active tenant accounts"
              tone="purple"
              mark="USR"
              points={sessionTrends.users ?? []}
              preference="higher"
              window={trendWindow}
            />
            <TrendMetricCard
              label="Requests / minute"
              value={compactNumber.format(currentRequestRate)}
              caption={`${compactNumber.format(Number(metrics.requests_in_window ?? data.api_requests_last_60m ?? 0))} total · ${compactNumber.format(averageRequestRate)} avg`}
              tone="blue"
              mark="RPM"
              points={requestTrend}
              window={trendWindow}
            />
            <TrendMetricCard
              label="API error rate"
              value={percentage(apiErrorRate)}
              caption={`${percentage(apiSuccessRate)} successful`}
              tone={apiErrorRate > 0.05 ? "red" : "green"}
              mark="ERR"
              points={errorTrend}
              preference="lower"
              window={trendWindow}
            />
            <TrendMetricCard
              label="P95 latency"
              value={metrics.p95_latency_ms === null || metrics.p95_latency_ms === undefined ? "—" : `${integerNumber.format(metrics.p95_latency_ms)} ms`}
              caption={`P99 ${metrics.p99_latency_ms === null || metrics.p99_latency_ms === undefined ? "—" : `${integerNumber.format(metrics.p99_latency_ms)} ms`}`}
              tone={Number(metrics.p95_latency_ms ?? 0) > 1_000 ? "red" : "amber"}
              mark="LAT"
              points={latencyTrend}
              preference="lower"
              window={trendWindow}
            />
            <TrendMetricCard
              label="Host bandwidth"
              value={bitrate(bandwidth.current_total_bytes_per_second)}
              caption={`${bitrate(bandwidth.current_ingress_bytes_per_second)} in · ${bitrate(bandwidth.current_egress_bytes_per_second)} out`}
              tone="cyan"
              mark="NET"
              points={bandwidthTrend}
              window={trendWindow}
            />
            <TrendMetricCard
              label="Attention queue"
              value={integerNumber.format(attentionCount)}
              caption={`${openSupport} support · ${data.critical_security_alerts ?? 0} security · ${data.overdue_invoices ?? 0} overdue`}
              tone={attentionCount > 0 ? "red" : "green"}
              mark="ACT"
              points={sessionTrends.attention ?? []}
              preference="lower"
              window={trendWindow}
            />
          </div>
        </section>

        <section className="platform-dashboard-core">
          <article className="platform-dashboard-panel platform-dashboard-panel--operations">
            <header className="platform-dashboard-panel__header">
              <div><span>Runtime</span><h2>Operations health</h2></div>
              <Link to="/platform/analytics">Open analytics <span>→</span></Link>
            </header>
            <div className="platform-health-list">
              <HealthRow label="API success rate" value={percentage(apiSuccessRate)} detail={`${compactNumber.format(Number(metrics.requests_in_window ?? data.api_requests_last_60m ?? 0))} requests observed during the last ${metrics.window_minutes ?? 60} minutes`} state={apiErrorRate <= 0.01 ? "good" : apiErrorRate <= 0.05 ? "watch" : "slow"} />
              <HealthRow label="Current request rate" value={`${compactNumber.format(currentRequestRate)} / min`} detail={`${compactNumber.format(averageRequestRate)} average · ${compactNumber.format(Number(metrics.peak_requests_per_minute ?? 0))} peak in the current window`} state={currentRequestRate > 0 ? "good" : "neutral"} />
              <HealthRow label="P95 response latency" value={metrics.p95_latency_ms === null || metrics.p95_latency_ms === undefined ? "—" : `${integerNumber.format(metrics.p95_latency_ms)} ms`} detail="Weighted high-percentile response time across measured routes" state={latencyState(metrics.p95_latency_ms)} />
              <HealthRow label="Host network throughput" value={bitrate(bandwidth.current_total_bytes_per_second)} detail="Inbound plus outbound traffic across non-loopback API host interfaces" state={bandwidth.available ? "good" : "neutral"} />
              <HealthRow label="Durable job queue" value={integerNumber.format(Number(data.queue_depth ?? 0))} detail="Queued platform and integration work awaiting execution" state={Number(data.queue_depth ?? 0) === 0 ? "good" : Number(data.queue_depth ?? 0) < 10 ? "watch" : "slow"} />
            </div>
          </article>

          <article className="platform-dashboard-panel platform-dashboard-panel--network">
            <header className="platform-dashboard-panel__header">
              <div><span>Network</span><h2>Bandwidth & transfer</h2></div>
              <StatusBadge value={bandwidth.available ? bandwidth.warming_up ? "WARMING" : "LIVE" : "UNAVAILABLE"} />
            </header>
            <div className="platform-network-primary">
              <span>Current host throughput</span>
              <strong>{bitrate(bandwidth.current_total_bytes_per_second)}</strong>
              <small>{bandwidth.source ?? "No host counter source detected"}</small>
            </div>
            <div className="platform-network-flow" aria-label="Inbound and outbound bandwidth">
              <div>
                <span>Inbound</span><b>{bitrate(bandwidth.current_ingress_bytes_per_second)}</b>
                <i><em style={{ width: `${Math.min(100, (currentIngress / flowMaximum) * 100)}%` }} /></i>
              </div>
              <div>
                <span>Outbound</span><b>{bitrate(bandwidth.current_egress_bytes_per_second)}</b>
                <i><em style={{ width: `${Math.min(100, (currentEgress / flowMaximum) * 100)}%` }} /></i>
              </div>
            </div>
            <dl className="platform-network-stats">
              <div><dt>Peak</dt><dd>{bitrate(bandwidth.peak_total_bytes_per_second)}</dd></div>
              <div><dt>Average</dt><dd>{bitrate(bandwidth.average_total_bytes_per_second)}</dd></div>
              <div><dt>Transferred</dt><dd>{byteSize(bandwidth.transfer_bytes_window)}</dd></div>
              <div><dt>Samples</dt><dd>{bandwidth.sample_count ?? 0}</dd></div>
            </dl>
            <p className="platform-network-note">{bandwidth.note ?? "Bandwidth telemetry is collected from the API host interfaces."}</p>
          </article>

          <article className="platform-dashboard-panel platform-dashboard-panel--providers">
            <header className="platform-dashboard-panel__header">
              <div><span>Services</span><h2>Provider readiness</h2></div>
              <Link to="/platform/integrations">Manage <span>→</span></Link>
            </header>
            <dl className="platform-readiness-list">
              <div><dt>Email delivery</dt><dd><StatusBadge value={data.email_status ?? "NOT CONFIGURED"} /></dd></div>
              <div><dt>Email latency</dt><dd>{data.email_latency_ms === null || data.email_latency_ms === undefined ? "No test" : `${integerNumber.format(data.email_latency_ms)} ms`}</dd></div>
              <div><dt>Configured providers</dt><dd>{configuredProviders} / {providerCount || "—"}</dd></div>
              <div><dt>Pending fiscalization</dt><dd>{integerNumber.format(Number(data.pending_fiscalizations ?? 0))}</dd></div>
            </dl>
            <div className="platform-provider-progress" aria-label="Configured provider ratio">
              <span style={{ width: providerCount ? `${Math.min(100, (configuredProviders / providerCount) * 100)}%` : "0%" }} />
            </div>
          </article>

          <article className="platform-dashboard-panel platform-dashboard-panel--actions">
            <header className="platform-dashboard-panel__header"><div><span>Command</span><h2>Action centre</h2></div></header>
            <nav className="platform-action-list" aria-label="Platform action centre">
              <Link to="/platform/tenants"><span>Tenant lifecycle</span><strong>{data.active_tenants ?? 0} active</strong><i>→</i></Link>
              <Link to="/platform/users"><span>User and session controls</span><strong>{data.total_users ?? 0} users</strong><i>→</i></Link>
              <Link to="/platform/integrations?tab=support"><span>Support operations</span><strong>{openSupport} open</strong><i>→</i></Link>
              <Link to="/platform/security"><span>Security attention</span><strong>{data.critical_security_alerts ?? 0} critical</strong><i>→</i></Link>
              <Link to="/platform/infrastructure"><span>Workers and diagnostics</span><strong>{data.queue_depth ?? 0} queued</strong><i>→</i></Link>
            </nav>
          </article>
        </section>

        <section className="platform-dashboard-lower">
          <article className="platform-dashboard-panel platform-dashboard-panel--jobs">
            <header className="platform-dashboard-panel__header">
              <div><span>Privileged operations</span><h2>Latest command jobs</h2></div>
              <button className="platform-btn compact" onClick={jobs.reload}>Refresh</button>
            </header>
            {jobs.error ? <ErrorState error={jobs.error} retry={jobs.reload} /> : recentJobs.length ? (
              <DataTable>
                <thead><tr><th>Command</th><th>Status</th><th>Risk</th><th>Created</th><th>Finished</th></tr></thead>
                <tbody>
                  {recentJobs.slice(0, 8).map((job) => (
                    <tr key={job.id}>
                      <td><strong>{job.command_name}</strong>{job.reason ? <small className="platform-table-subtext">{job.reason}</small> : null}</td>
                      <td><StatusBadge value={job.status} /></td>
                      <td><StatusBadge value={job.risk_level} /></td>
                      <td>{readableDate(job.created_at)}</td>
                      <td>{job.finished_at ? readableDate(job.finished_at) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </DataTable>
            ) : (
              <div className="platform-dashboard-empty"><span>✓</span><div><strong>No command jobs recorded</strong><small>Privileged operations will appear here with their status, risk and timestamps.</small></div></div>
            )}
          </article>

          <article className="platform-dashboard-panel platform-dashboard-panel--alerts">
            <header className="platform-dashboard-panel__header">
              <div><span>Attention</span><h2>Recent alerts</h2></div>
              <Link to="/platform/security">View all <span>→</span></Link>
            </header>
            {alerts.error ? <ErrorState error={alerts.error} retry={alerts.reload} /> : recentAlerts.length ? (
              <div className="platform-alert-list">
                {recentAlerts.slice(0, 6).map((alert) => (
                  <Link to="/platform/security" key={alert.id}>
                    <StatusBadge value={alert.severity} />
                    <span><strong>{alert.title ?? "Platform alert"}</strong><small>{alert.category ?? "Platform"} · {readableDate(alert.created_at)}</small></span>
                    <i>→</i>
                  </Link>
                ))}
              </div>
            ) : (
              <div className="platform-dashboard-empty platform-dashboard-empty--healthy"><span>✓</span><div><strong>No active platform alerts</strong><small>Security, health, billing and integration alerts will appear here.</small></div></div>
            )}
          </article>
        </section>
      </div>
    </PlatformShell>
  );
}
