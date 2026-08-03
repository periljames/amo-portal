import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CheckSquare2,
  ClipboardList,
  Clock3,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  UserCheck,
} from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";

import DepartmentLayout from "../components/Layout/DepartmentLayout";
import PageHeader from "../components/shared/PageHeader";
import {
  getDepartmentHome,
  type DepartmentHomeActivity,
  type DepartmentHomeAlert,
  type DepartmentHomeQuickAction,
  type DepartmentHomeResponse,
  type DepartmentHomeTask,
} from "../services/departmentHome";
import { DEPARTMENT_LABELS, type DepartmentId } from "../utils/departmentAccess";
import "../styles/department-home.css";

type LoadState = "loading" | "ready" | "error";

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "No due date";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function humanise(value: string): string {
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function departmentTitle(value: string): string {
  return DEPARTMENT_LABELS[value as DepartmentId] || humanise(value);
}

function EmptyState({ message }: { message: string }): React.ReactElement {
  return (
    <div className="department-home__empty">
      <CheckSquare2 size={22} aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}

function Panel({
  title,
  subtitle,
  wide = false,
  children,
}: {
  title: string;
  subtitle?: string;
  wide?: boolean;
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <section className={`department-home__panel${wide ? " department-home__panel--wide" : ""}`}>
      <header className="department-home__panel-header">
        <div>
          <h2>{title}</h2>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
      </header>
      <div className="department-home__panel-body">{children}</div>
    </section>
  );
}

function TaskList({
  items,
  empty,
  onNavigate,
}: {
  items: DepartmentHomeTask[];
  empty: string;
  onNavigate: (path: string) => void;
}): React.ReactElement {
  if (!items.length) return <EmptyState message={empty} />;
  return (
    <div className="department-home__list">
      {items.map((item) => (
        <button key={item.id} type="button" onClick={() => onNavigate(item.route)}>
          <span>
            <strong>{item.title}</strong>
            <small>{item.description || humanise(item.entity_type || "Assigned work")}</small>
            <span className="department-home__task-meta">
              <i data-priority={item.priority} aria-hidden="true" />
              Priority {item.priority} · {formatTimestamp(item.due_at)}
            </span>
          </span>
          <ArrowRight size={14} aria-hidden="true" />
        </button>
      ))}
    </div>
  );
}

function AlertList({
  items,
  onNavigate,
}: {
  items: DepartmentHomeAlert[];
  onNavigate: (path: string) => void;
}): React.ReactElement {
  if (!items.length) return <EmptyState message="No urgent departmental alerts are currently assigned to you." />;
  return (
    <div className="department-home__alerts">
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          className={`department-home__alert department-home__alert--${item.tone}`}
          onClick={() => onNavigate(item.route)}
        >
          <ShieldAlert size={16} aria-hidden="true" />
          <span>
            <strong>{item.title}</strong>
            <small>{item.message}</small>
          </span>
          <ArrowRight size={14} aria-hidden="true" />
        </button>
      ))}
    </div>
  );
}

function QuickActions({
  items,
  onNavigate,
}: {
  items: DepartmentHomeQuickAction[];
  onNavigate: (path: string) => void;
}): React.ReactElement {
  if (!items.length) return <EmptyState message="No additional quick actions are available for this role." />;
  return (
    <div className="department-home__quick-actions">
      {items.map((item) => (
        <button key={item.id} type="button" onClick={() => onNavigate(item.route)}>
          <span>
            <strong>{item.label}</strong>
            <small>{item.description}</small>
          </span>
          <ArrowRight size={14} aria-hidden="true" />
        </button>
      ))}
    </div>
  );
}

function ActivityList({ items }: { items: DepartmentHomeActivity[] }): React.ReactElement {
  if (!items.length) return <EmptyState message="No recent activity is available for this workspace." />;
  return (
    <div className="department-home__activity">
      {items.map((item) => (
        <div key={item.id} className="department-home__activity-item">
          <i aria-hidden="true" />
          <span>
            <strong>{humanise(item.action)}</strong>
            <small>{humanise(item.entity_type)} · {formatTimestamp(item.occurred_at)}</small>
          </span>
        </div>
      ))}
    </div>
  );
}

const DepartmentHomePage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string; section?: string }>();
  const navigate = useNavigate();
  const amoCode = params.amoCode || "UNKNOWN";
  const department = params.department || "planning";
  const section = params.section || "home";
  const controllerRef = useRef<AbortController | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [home, setHome] = useState<DepartmentHomeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setState("loading");
    setError(null);
    try {
      const response = await getDepartmentHome(amoCode, department, controller.signal);
      if (controller.signal.aborted) return;
      if (response.contract !== "department-home.v1") throw new Error("Unsupported department home response.");
      setHome(response);
      setState("ready");
    } catch (loadError) {
      if (controller.signal.aborted) return;
      setError(loadError instanceof Error ? loadError.message : "Department home could not be loaded.");
      setState("error");
    }
  }, [amoCode, department]);

  useEffect(() => {
    void load();
    return () => controllerRef.current?.abort();
  }, [load]);

  const title = useMemo(() => departmentTitle(department), [department]);
  const sectionLabel = useMemo(() => humanise(section), [section]);
  const go = useCallback((path: string) => {
    if (path) navigate(path);
  }, [navigate]);

  return (
    <DepartmentLayout amoCode={amoCode} activeDepartment={department} showPollingErrorBanner={Boolean(home && state === "error")}>
      <div className="department-home">
        <PageHeader
          compact
          eyebrow="Department workspace"
          title={`${title} ${sectionLabel.toLowerCase()}`}
          subtitle={`Live assigned work, approvals, obligations and recent activity for ${home?.amo.name || amoCode}.`}
          breadcrumbs={[{ label: title, to: `/maintenance/${encodeURIComponent(amoCode)}/${department}` }, { label: sectionLabel }]}
          meta={home ? <span className="department-home__live-badge">Live tenant data</span> : undefined}
          actions={
            <div className="department-home__actions">
              <button className="department-home__button" type="button" onClick={() => void load()} disabled={state === "loading"}>
                <RefreshCw size={14} className={state === "loading" ? "department-home__spin" : ""} aria-hidden="true" />
                Refresh
              </button>
            </div>
          }
        />

        {state === "loading" && !home ? (
          <div className="department-home__status" role="status" aria-live="polite">
            <RefreshCw size={16} className="department-home__spin" aria-hidden="true" /> Loading departmental workspace…
          </div>
        ) : null}

        {error ? (
          <div className="department-home__error" role="alert">
            <AlertTriangle size={18} aria-hidden="true" />
            <div>
              <strong>{home ? "Live refresh failed" : "Department home unavailable"}</strong>
              <p>{error}</p>
            </div>
            <button className="department-home__button" type="button" onClick={() => void load()}>Retry</button>
          </div>
        ) : null}

        {home ? (
          <>
            <section className="department-home__metrics" aria-label="Department metrics">
              <div className="department-home__metric">
                <ClipboardList size={20} aria-hidden="true" />
                <span><strong>{home.summary.assigned_open}</strong><small>Assigned open work</small></span>
              </div>
              <div className="department-home__metric">
                <UserCheck size={20} aria-hidden="true" />
                <span><strong>{home.summary.approvals_open}</strong><small>Awaiting your approval</small></span>
              </div>
              <div className="department-home__metric department-home__metric--danger">
                <AlertTriangle size={20} aria-hidden="true" />
                <span><strong>{home.summary.overdue}</strong><small>Overdue assignments</small></span>
              </div>
              <div className="department-home__metric department-home__metric--warning">
                <CalendarClock size={20} aria-hidden="true" />
                <span><strong>{home.summary.due_soon}</strong><small>Due within seven days</small></span>
              </div>
              <div className="department-home__metric">
                <Sparkles size={20} aria-hidden="true" />
                <span><strong>{home.summary.high_priority}</strong><small>High-priority work</small></span>
              </div>
            </section>

            <div className="department-home__grid">
              <Panel title="Urgent alerts" subtitle="Current assigned exposure">
                <AlertList items={home.alerts} onNavigate={go} />
              </Panel>
              <Panel title="My assigned work" subtitle="Open and in-progress tasks" wide>
                <TaskList items={home.assigned_work} empty="No open work is currently assigned to you." onNavigate={go} />
              </Panel>
              <Panel title="Approvals" subtitle="Items awaiting your decision">
                <TaskList items={home.approvals} empty="No approvals are currently waiting for you." onNavigate={go} />
              </Panel>
              <Panel title="Upcoming schedule" subtitle="Dated work within the next 30 days" wide>
                <TaskList items={home.schedule} empty="No dated obligations are currently scheduled." onNavigate={go} />
              </Panel>
              <Panel title="Quick actions" subtitle="Permission-filtered workspace shortcuts">
                <QuickActions items={home.quick_actions} onNavigate={go} />
              </Panel>
              <Panel title="Recent activity" subtitle="Your latest governed actions" wide>
                <ActivityList items={home.recent_activity} />
              </Panel>
              <Panel title="Department news" subtitle="Organisation and department communications">
                {home.news.length ? (
                  <div className="department-home__list">
                    {home.news.map((item) => (
                      <div key={item.id} className="department-home__activity-item">
                        <Clock3 size={14} aria-hidden="true" />
                        <span><strong>{item.title}</strong><small>{item.message}</small></span>
                      </div>
                    ))}
                  </div>
                ) : <EmptyState message="Department news is not configured yet. No example content is shown." />}
              </Panel>
            </div>
          </>
        ) : null}
      </div>
    </DepartmentLayout>
  );
};

export default DepartmentHomePage;
