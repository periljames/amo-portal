import React, { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarPlus2, ShieldAlert } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { hasQmsRolePermission } from "../../app/routeGuards";
import { listAuditProgrammes, type AuditProgramme, type AuditProgrammeItem } from "../../services/qmsAuditProgramme";
import QmsAuditProgrammePage from "./QmsAuditProgrammePage";

const SCHEDULABLE_RECURRENCES = new Set(["ONE_TIME", "MONTHLY", "QUARTERLY", "SEMI_ANNUAL", "ANNUAL"]);

type QueueItem = { programme: AuditProgramme; item: AuditProgrammeItem };

const QmsAuditProgrammeWorkspacePage: React.FC = () => {
  const { amoCode = "UNKNOWN" } = useParams<{ amoCode?: string }>();
  const year = new Date().getFullYear();
  const canManage = hasQmsRolePermission("qms.audit.manage");
  const programmesQuery = useQuery({
    queryKey: ["qms-audit-programmes", amoCode, year],
    queryFn: ({ signal }) => listAuditProgrammes(amoCode, year, signal),
    staleTime: 5_000,
  });

  const queue = useMemo<QueueItem[]>(() => {
    const programmes = programmesQuery.data?.items || [];
    return programmes.flatMap((programme) => {
      if (!["APPROVED", "ACTIVE"].includes(programme.status)) return [];
      return (programme.items || [])
        .filter((item) => item.state === "PLANNED")
        .map((item) => ({ programme, item }));
    });
  }, [programmesQuery.data?.items]);

  return (
    <>
      {canManage && queue.length ? (
        <section className="qms-audit-programme qms-audit-programme__governance" aria-label="Programme scheduling queue">
          <div>
            <strong><CalendarPlus2 size={15} /> Programme scheduling queue</strong>
            <p>Approved surveillance requirements remain Planned until an authoritative Quality Planner schedule passes personnel/location conflict checks and is committed.</p>
          </div>
          <div className="qms-audit-programme__actions">
            {queue.slice(0, 8).map(({ programme, item }) => (
              SCHEDULABLE_RECURRENCES.has(item.recurrence) ? (
                <Link
                  key={item.id}
                  to={`/maintenance/${encodeURIComponent(amoCode)}/quality/audits/program/${encodeURIComponent(programme.id)}/items/${encodeURIComponent(item.id)}/schedule`}
                  title={`${programme.programme_ref} · ${item.title}`}
                >
                  <CalendarPlus2 size={13} /> {item.title}
                </Link>
              ) : (
                <span key={item.id} title={`${programme.programme_ref} · ${item.title}`}>
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
