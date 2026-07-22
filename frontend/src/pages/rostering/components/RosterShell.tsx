import type { ReactNode } from "react";
import { NavLink, useParams } from "react-router-dom";
import {
  BarChart3,
  CalendarDays,
  ClipboardCheck,
  Gauge,
  GraduationCap,
  Settings2,
  UsersRound,
} from "lucide-react";
import { motion, useReducedMotion } from "framer-motion";

import DepartmentLayout from "../../../components/Layout/DepartmentLayout";
import "../../../styles/rostering-workforce.css";

type Props = {
  title: string;
  eyebrow: string;
  description: string;
  actions?: ReactNode;
  children: ReactNode;
  context?: ReactNode;
};

const NAV = [
  { suffix: "dashboard", label: "Command", icon: Gauge },
  { suffix: "calendar", label: "Planner", icon: CalendarDays },
  { suffix: "planning-board", label: "Capacity", icon: UsersRound },
  { suffix: "my-roster", label: "My duty", icon: ClipboardCheck },
  { suffix: "training-impact", label: "Compliance", icon: GraduationCap },
  { suffix: "reports", label: "Reports", icon: BarChart3 },
  { suffix: "settings", label: "Setup", icon: Settings2 },
] as const;

export function RosterShell({ title, eyebrow, description, actions, children, context }: Props) {
  const { amoCode = "UNKNOWN" } = useParams();
  const reduceMotion = useReducedMotion();
  const root = `/maintenance/${encodeURIComponent(amoCode)}/rostering`;

  return (
    <DepartmentLayout amoCode={amoCode || "UNKNOWN"} activeDepartment="rostering">
      <div className="wr-page">
        <header className="wr-header">
          <div className="wr-header__copy">
            <span className="wr-eyebrow">{eyebrow}</span>
            <h1>{title}</h1>
            <p>{description}</p>
          </div>
          {actions ? <div className="wr-header__actions">{actions}</div> : null}
        </header>

        <nav className="wr-tabs" aria-label="Duty rostering sections">
          {NAV.map(({ suffix, label, icon: Icon }) => (
            <NavLink
              key={suffix}
              to={`${root}/${suffix}`}
              className={({ isActive }) => `wr-tab${isActive ? " wr-tab--active" : ""}`}
            >
              <Icon aria-hidden="true" size={16} strokeWidth={1.9} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>

        {context ? <div className="wr-context">{context}</div> : null}

        <motion.main
          className="wr-main"
          initial={reduceMotion ? false : { opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: reduceMotion ? 0 : 0.18, ease: "easeOut" }}
        >
          {children}
        </motion.main>
      </div>
    </DepartmentLayout>
  );
}

export function RosterLoading({ label = "Loading duty data…" }: { label?: string }) {
  return (
    <div className="wr-state" role="status" aria-live="polite">
      <span className="wr-spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function RosterError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="wr-state wr-state--error" role="alert">
      <div>
        <strong>Could not load this workspace</strong>
        <p>{message}</p>
      </div>
      {onRetry ? <button className="wr-button wr-button--secondary" type="button" onClick={onRetry}>Retry</button> : null}
    </div>
  );
}

export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return (
    <div className="wr-empty">
      <strong>{title}</strong>
      <p>{description}</p>
      {action ? <div>{action}</div> : null}
    </div>
  );
}

export function MetricCard({ label, value, detail, tone = "neutral" }: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  tone?: "neutral" | "good" | "warning" | "danger" | "info";
}) {
  return (
    <article className={`wr-metric wr-tone-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {detail ? <small>{detail}</small> : null}
    </article>
  );
}

export function StatusPill({ value, tone }: { value: string; tone?: string }) {
  const normalized = value.toLowerCase().replace(/_/g, "-");
  return <span className={`wr-pill wr-pill--${tone || normalized}`}>{value.replace(/_/g, " ")}</span>;
}
