import React from "react";
import { useLocation } from "react-router-dom";
import QmsCanonicalLegacyPage from "./QmsCanonicalLegacyPage";
import QmsPlannerPageV2 from "./planner/QmsPlannerPageV2";

/**
 * Keep the canonical QMS route stable while allowing the calendar to evolve as a
 * dedicated planning product. Non-calendar routes continue to use the established
 * canonical page; /quality/calendar/* is handled by the Quality Operations Planner.
 */
export default function QmsCanonicalPage(): React.ReactElement {
  const location = useLocation();
  const isPlannerRoute = /\/quality\/calendar(?:\/|$)/i.test(location.pathname)
    || /\/qms\/calendar(?:\/|$)/i.test(location.pathname);

  return isPlannerRoute ? <QmsPlannerPageV2 /> : <QmsCanonicalLegacyPage />;
}
