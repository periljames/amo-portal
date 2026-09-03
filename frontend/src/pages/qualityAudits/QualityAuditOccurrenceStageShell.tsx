import React from "react";

import QMSLayout from "../../components/QMS/QMSLayout";
import { AUDIT_OCCURRENCE_MOUNT_ID } from "../../features/qms/auditSession/OccurrenceToolbarPortal";

type Props = { amoCode: string };

/**
 * Lightweight route shell for the canonical six-stage audit occurrence.
 *
 * The actual stage workspace is mounted by QualityEnhancementsHost, which is a
 * router sibling so it can preserve realtime, focus and lifecycle coordination.
 * Keeping this route shell intentionally empty prevents a second page tree and
 * duplicate data queries on /setup, /prepare, /live, /closing, /follow-up and
 * /archive.
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
    <div id={AUDIT_OCCURRENCE_MOUNT_ID} className="qms-audit-occurrence-mount" />
  </QMSLayout>
);

export default QualityAuditOccurrenceStageShell;
