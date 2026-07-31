import React from "react";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import { Link } from "react-router-dom";

import type { QmsOperationalActionItem } from "../../../types/qms";
import {
  normaliseActionQueue,
  qmsAgeLabel,
  qmsOwnerStatusLabel,
  safeQmsInternalLink,
} from "../qmsOverviewModel";

type Props = {
  amoCode: string;
  items: QmsOperationalActionItem[];
  fallbackRoute: string;
};

const QmsActionQueue: React.FC<Props> = ({ amoCode, items, fallbackRoute }) => {
  const rows = normaliseActionQueue(items);

  return (
    <section className="qms-overview-section qms-overview-section--priority" aria-labelledby="qms-action-queue-title">
      <header className="qms-overview-section__header">
        <div>
          <span>Ranked by consequence and lateness</span>
          <h2 id="qms-action-queue-title">Needs action</h2>
        </div>
        <Link to={fallbackRoute}>Open work queue <ArrowRight size={14} /></Link>
      </header>

      {rows.length ? (
        <div className="qms-action-table" role="table" aria-label="Ranked QMS action queue">
          <div className="qms-action-table__head" role="row">
            <span role="columnheader">Exposure</span>
            <span role="columnheader">Count</span>
            <span role="columnheader">Oldest</span>
            <span role="columnheader">Owner</span>
            <span role="columnheader">Next action</span>
          </div>
          {rows.map((item) => (
            <Link
              key={item.id}
              className={`qms-action-table__row qms-tone--${item.tone}`}
              role="row"
              to={safeQmsInternalLink(item.route, fallbackRoute, amoCode)}
            >
              <span className="qms-action-table__exposure" role="cell">
                <strong>{item.label}</strong>
                <small>{item.regulatory_consequence?.replaceAll("_", " ") || "Operational quality exposure"}</small>
              </span>
              <strong className="qms-action-table__count" role="cell">{item.count.toLocaleString()}</strong>
              <span role="cell">{qmsAgeLabel(item.oldest_age_days)}</span>
              <span role="cell">{qmsOwnerStatusLabel(item.owner_status)}</span>
              <span className="qms-action-table__next" role="cell">{item.next_action}<ArrowRight size={14} /></span>
            </Link>
          ))}
        </div>
      ) : (
        <div className="qms-overview-empty">
          <CheckCircle2 size={20} aria-hidden="true" />
          <div><strong>No ranked exceptions</strong><p>The operational contract returned no overdue or priority action.</p></div>
        </div>
      )}
    </section>
  );
};

export default QmsActionQueue;
