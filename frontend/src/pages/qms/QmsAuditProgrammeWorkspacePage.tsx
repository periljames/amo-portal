import React from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CalendarPlus2, ShieldAlert } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { hasQmsRolePermission } from "../../app/routeGuards";
import { listAuditProgrammeSchedulingQueue } from "../../services/qmsAuditProgramme";
import QmsAuditProgrammePage from "./QmsAuditProgrammePage";

const SCHEDULABLE_RECURRENCES = new Set(["ONE_TIME", "MONTHLY", "QUARTERLY", "SEMI_ANNUAL", "ANNUAL"]);

const QmsAuditProgrammeWorkspacePage: React.FC = () => {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode?: string }>();
  const canManage = hasQmsRolePermission("qms.audit.manage");
  const queueQuery = useQuery({
    queryKey: ["qms-audit-programme-scheduling-queue", amoCode],
    queryFn: ({ signal }) => listAuditProgrammeSchedulingQueue(amoCode, signal),
    enabled: canManage,
    staleTime: 5_000,
  });
  const queue = queueQuery.data?.items || [];

  return (
    <>
      {canManage && queueQuery.error ? (
        <section className="qms-audit-programme qms-audit-programme__error" role="alert">
          <AlertTriangle size={16} /> Programme scheduling queue unavailable: {queueQuery.error instanceof Error ? queueQuery.error.message : "request failed"}
        </section>
      ) : null}
      {canManage && queue.length ? (
        <section className="qms-audit-programme qms-audit-programme__governance" aria-label="Programme scheduling queue">
          <div>
            <strong><CalendarPlus2 size={15} /> Programme scheduling queue</strong>
            <p>Approved surveillance requirements remain Planned until an authoritative Quality Planner schedule passes personnel/location conflict checks and is committed.</p>
          </div>
          <div className="qms-audit-programme__actions">
            {queue.slice(0, 8).map((item) => (
              SCHEDULABLE_RECURRENCES.has(item.recurrence) ? (
                <Link
                  key={item.programme_item_id}
                  to={`/maintenance/${encodeURIComponent(amoCode)}/quality/audits/program/${encodeURIComponent(item.programme_id)}/items/${encodeURIComponent(item.programme_item_id)}/schedule`}
                  title={`${item.programme_ref} · ${item.title}`}
                >
                  <CalendarPlus2 size={13} /> {item.title}
                </Link>
              ) : (
                <span key={item.programme_item_id} title={`${item.programme_ref} · ${item.title}`}>
                  <ShieldAlert size={13} /> {item.title} · amend cadence
                </span>
              )
            ))}
          </div>
        </section>
      ) : null}
      <QmsAuditProgrammePage />
    </>
  );
};

export default QmsAuditProgrammeWorkspacePage;
