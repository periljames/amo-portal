import React, { useMemo } from "react";
import { useLocation } from "react-router-dom";

import QmsAuditProgrammeSchedulePanel from "./QmsAuditProgrammeSchedulePanel";

type ProgrammeScheduleRoute = { amoCode: string; programmeId: string; itemId: string };

function extractRoute(pathname: string): ProgrammeScheduleRoute | null {
  const match = pathname.match(
    /\/maintenance\/([^/]+)\/(?:quality|qms)\/audits\/program\/([^/]+)\/items\/([^/]+)\/schedule\/?$/i,
  );
  if (!match) return null;
  return {
    amoCode: decodeURIComponent(match[1]),
    programmeId: decodeURIComponent(match[2]),
    itemId: decodeURIComponent(match[3]),
  };
}

/**
 * Refresh-safe deep-link wrapper for programme-item scheduling.
 * Rendered inside QualityAuditsSectionLayout via QmsCanonicalPage.
 */
const QmsAuditProgrammeSchedulePage: React.FC = () => {
  const location = useLocation();
  const route = useMemo(() => extractRoute(location.pathname), [location.pathname]);

  if (!route) {
    return (
      <section className="qms-audit-programme">
        <div className="qms-audit-programme__error" role="alert">
          Invalid audit programme scheduling route.
        </div>
      </section>
    );
  }

  return (
    <QmsAuditProgrammeSchedulePanel
      amoCode={route.amoCode}
      programmeId={route.programmeId}
      itemId={route.itemId}
      variant="page"
    />
  );
};

export default QmsAuditProgrammeSchedulePage;
