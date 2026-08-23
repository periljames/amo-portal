import React from "react";
import { ArrowRight, CalendarClock } from "lucide-react";
import { Link } from "react-router-dom";

import type { QmsOperationalObligation } from "../../../types/qms";
import {
  normaliseQmsCalendarEntries,
  parseQmsDate,
  qmsDateLabel,
  qmsModuleLabel,
  qmsRelativeDateLabel,
  safeQmsInternalLink,
} from "../qmsOverviewModel";

type Props = {
  amoCode: string;
  items: QmsOperationalObligation[];
  fallbackRoute: string;
  asOf?: string | null;
};

const QmsUpcomingObligations: React.FC<Props> = ({ amoCode, items, fallbackRoute, asOf }) => {
  const referenceNow = parseQmsDate(asOf) || new Date();
  const rows = normaliseQmsCalendarEntries(items, referenceNow, 10);

  return (
    <section className="qms-overview-section" aria-labelledby="qms-upcoming-title">
      <header className="qms-overview-section__header">
        <div>
          <span>Next 30 days</span>
          <h2 id="qms-upcoming-title">Upcoming obligations</h2>
        </div>
        <Link to={fallbackRoute}>Open calendar <ArrowRight size={14} /></Link>
      </header>

      {rows.length ? (
        <ol className="qms-obligation-list">
          {rows.map((item) => (
            <li key={item.id}>
              <Link to={safeQmsInternalLink(item.link, fallbackRoute, amoCode)}>
                <time dateTime={item.date || undefined}>
                  <strong>{qmsDateLabel(item.date)}</strong>
                  <small>{qmsRelativeDateLabel(item.date, referenceNow)}</small>
                </time>
                <span className="qms-obligation-list__body">
                  <strong>{item.title}</strong>
                  <small>{item.subtitle || `${qmsModuleLabel(item.module)} · ${qmsModuleLabel(item.event_type)}`}</small>
                </span>
                <span className={`qms-obligation-list__state qms-obligation-list__state--${item.due_state || "upcoming"}`}>
                  {item.due_state?.replaceAll("_", " ") || "upcoming"}
                </span>
                <ArrowRight size={14} aria-hidden="true" />
              </Link>
            </li>
          ))}
        </ol>
      ) : (
        <div className="qms-overview-empty">
          <CalendarClock size={20} aria-hidden="true" />
          <div><strong>No upcoming obligations returned</strong><p>No audit, CAR, training, document-review, management-review, or regulatory date was returned for the next 30 days.</p></div>
        </div>
      )}
    </section>
  );
};

export default QmsUpcomingObligations;