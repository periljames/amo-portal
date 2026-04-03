import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import QMSLayout from "../components/QMS/QMSLayout";
import { getContext } from "../services/auth";
import { qmsListAudits, qmsUpdateAudit } from "../services/qms";
import { getDueMessage } from "./qualityAudits/dueStatus";

const QMSEventsPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const navigate = useNavigate();
  const ctx = getContext();
  const amoCode = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";
  const [tick, setTick] = useState(Date.now());
  const queryClient = useQueryClient();

  useEffect(() => {
    const id = window.setInterval(() => setTick(Date.now()), 60_000);
    return () => window.clearInterval(id);
  }, []);

  const auditsQuery = useQuery({
    queryKey: ["qms-events-audits", amoCode, department],
    queryFn: () => qmsListAudits({ domain: "AMO" }),
    refetchInterval: 60_000,
  });

  const moveAudit = useMutation({
    mutationFn: ({ id, planned_start, planned_end }: { id: string; planned_start: string; planned_end: string | null }) => qmsUpdateAudit(id, { planned_start, planned_end }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["qms-events-audits", amoCode, department] });
    },
  });

  const audits = (auditsQuery.data ?? []).filter((a) => a.planned_start).sort((a, b) => (a.planned_start || "").localeCompare(b.planned_start || ""));
  const nearest = audits[0];
  const dueBanner = getDueMessage(new Date(tick), null, nearest?.planned_start, nearest?.planned_end);

  return (
    <QMSLayout amoCode={amoCode} department={department} title="QMS Events" subtitle="Audit schedule timeline from real audit dates.">
      {dueBanner && nearest ? <div className="qms-card" style={{ marginBottom: 12 }}><strong>{dueBanner.label}</strong> · {nearest.audit_ref}</div> : null}
      <div className="qms-card">
        <table className="table">
          <thead><tr><th>Audit</th><th>Start</th><th>End</th><th>Open</th><th>Reschedule</th></tr></thead>
          <tbody>
            {audits.map((a) => (
              <tr key={a.id}>
                <td>{a.audit_ref} · {a.title}</td>
                <td>{a.planned_start}</td>
                <td>{a.planned_end || "—"}</td>
                <td><button type="button" className="secondary-chip-btn" onClick={() => navigate(`/maintenance/${amoCode}/${department}/qms/audits/${a.id}`)}>Open</button></td>
                <td>
                  <button type="button" className="secondary-chip-btn" onClick={() => {
                    if (!a.planned_start) return;
                    const d = new Date(a.planned_start);
                    d.setDate(d.getDate() + 1);
                    const next = d.toISOString().slice(0, 10);
                    moveAudit.mutate({ id: a.id, planned_start: next, planned_end: a.planned_end });
                  }}>+1 day</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </QMSLayout>
  );
};

export default QMSEventsPage;
