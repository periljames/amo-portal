import React from "react";
import { ArrowRight, Inbox } from "lucide-react";
import { Link } from "react-router-dom";

import type { QmsOperationalWorkItem } from "../../../types/qms";
import { normaliseMyWork, qmsTimestampLabel, safeQmsInternalLink } from "../qmsOverviewModel";

type Props = {
  amoCode: string;
  items: QmsOperationalWorkItem[];
  fallbackRoute: string;
};

function severityClass(value: string | null | undefined): string {
  const severity = String(value || "").toUpperCase();
  if (["CRITICAL", "MAJOR", "DANGER", "ERROR"].includes(severity)) return "danger";
  if (["WARNING", "WARN", "MEDIUM"].includes(severity)) return "warning";
  return "neutral";
}

const QmsMyWork: React.FC<Props> = ({ amoCode, items, fallbackRoute }) => {
  const rows = normaliseMyWork(items);
  return (
    <section className="qms-overview-section" aria-labelledby="qms-my-work-title">
      <header className="qms-overview-section__header">
        <div>
          <span>Assigned to the logged-in user</span>
          <h2 id="qms-my-work-title">My work</h2>
        </div>
        <Link to={fallbackRoute}>Open all <ArrowRight size={14} /></Link>
      </header>

      {rows.length ? (
        <div className="qms-work-list">
          {rows.map((item) => (
            <Link key={item.id} to={safeQmsInternalLink(item.route, fallbackRoute, amoCode)} className={`qms-work-row qms-tone--${severityClass(item.severity)}`}>
              <span className="qms-work-row__marker" aria-hidden="true" />
              <span className="qms-work-row__body">
                <strong>{item.title}</strong>
                <small>{qmsTimestampLabel(item.created_at)}{item.severity ? ` · ${item.severity}` : ""}</small>
              </span>
              <ArrowRight size={14} aria-hidden="true" />
            </Link>
          ))}
        </div>
      ) : (
        <div className="qms-overview-empty">
          <Inbox size={20} aria-hidden="true" />
          <div><strong>No assigned QMS work</strong><p>No unread approval, review, verification, or preparation task was returned.</p></div>
        </div>
      )}
    </section>
  );
};

export default QmsMyWork;
