import React from "react";
import { ArrowDownRight, ArrowRight, ArrowUpRight, Minus, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";

import type { QmsOperationalKpi } from "../../../types/qms";
import {
  qmsDirectionLabel,
  qmsMetricLabel,
  safeQmsInternalLink,
} from "../qmsOverviewModel";

type Props = {
  amoCode: string;
  items: QmsOperationalKpi[];
  fallbackRoute: string;
};

function DirectionIcon({ direction }: { direction: QmsOperationalKpi["direction"] }): React.ReactElement {
  if (direction === "improving") return <ArrowUpRight size={15} aria-hidden="true" />;
  if (direction === "deteriorating") return <ArrowDownRight size={15} aria-hidden="true" />;
  return <Minus size={15} aria-hidden="true" />;
}

function directionTone(direction: QmsOperationalKpi["direction"]): string {
  if (direction === "improving") return "positive";
  if (direction === "deteriorating") return "danger";
  return "neutral";
}

const QmsPerformanceSummary: React.FC<Props> = ({ amoCode, items, fallbackRoute }) => {
  const rows = items.slice(0, 5);

  return (
    <section className="qms-overview-section" aria-labelledby="qms-performance-title">
      <header className="qms-overview-section__header">
        <div>
          <span>Current · target · previous period</span>
          <h2 id="qms-performance-title">Quality performance</h2>
        </div>
        <Link to={fallbackRoute}>Open reports <ArrowRight size={14} /></Link>
      </header>

      {rows.length ? (
        <div className="qms-performance-grid">
          {rows.map((item) => (
            <Link key={item.id} to={safeQmsInternalLink(item.route, fallbackRoute, amoCode)} className="qms-performance-card">
              <span className="qms-performance-card__label">{item.label}</span>
              <strong>{qmsMetricLabel(item.current, item.unit)}</strong>
              <dl>
                <div><dt>Target</dt><dd>{qmsMetricLabel(item.target, item.unit)}</dd></div>
                <div><dt>Previous</dt><dd>{qmsMetricLabel(item.previous, item.unit)}</dd></div>
              </dl>
              <span className={`qms-performance-card__direction qms-tone--${directionTone(item.direction)}`}>
                <DirectionIcon direction={item.direction} />
                {qmsDirectionLabel(item.direction)}
              </span>
              {item.data_status === "not_available" ? <small>Source history is not yet sufficient for this KPI.</small> : null}
            </Link>
          ))}
        </div>
      ) : (
        <div className="qms-overview-empty">
          <TrendingUp size={20} aria-hidden="true" />
          <div><strong>Performance data unavailable</strong><p>The server did not return governed QMS indicators for this tenant.</p></div>
        </div>
      )}
    </section>
  );
};

export default QmsPerformanceSummary;
