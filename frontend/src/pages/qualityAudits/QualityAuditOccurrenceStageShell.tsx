import React from "react";

import QMSLayout from "../../components/QMS/QMSLayout";

type Props = { amoCode: string };

/**
 * Lightweight route shell for the canonical six-stage audit occurrence.
 *
 * The actual stage workspace is mounted by QualityEnhancementsHost, which is a
 * router sibling so it can preserve realtime, focus and lifecycle coordination.
 * Keeping this route shell intentionally empty prevents the legacy
 * QualityAuditRunHubPage from mounting its competing cockpit and duplicate data
 * queries on /setup, /prepare, /live, /closing, /follow-up and /archive.
 */
const QualityAuditOccurrenceStageShell: React.FC<Props> = ({ amoCode }) => (
  <QMSLayout
    amoCode={amoCode}
    department="quality"
    title="Audit occurrence"
    subtitle="Governed six-stage audit workspace"
    hideBackButton
    customHeader={<></>}
  >
    <div className="qms-canonical-occurrence-route-shell" aria-hidden="true" />
  </QMSLayout>
);

export default QualityAuditOccurrenceStageShell;
