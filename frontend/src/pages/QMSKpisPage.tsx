import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import QMSLayout from "../components/QMS/QMSLayout";
import DashboardCockpit from "../dashboards/DashboardCockpit";
import { getContext } from "../services/auth";
import {
  qmsListAudits,
  qmsListCars,
  qmsListDocuments,
  type QMSAuditOut,
  type QMSDocumentOut,
  type CAROut,
} from "../services/qms";
import { listTrainingEvents } from "../services/training";
import type { TrainingEventRead } from "../types/training";
import { isUiShellV2Enabled } from "../utils/featureFlags";

type LoadState = "idle" | "loading" | "ready" | "error";

const QMSKpisPage: React.FC = () => {
  const params = useParams<{ amoCode?: string; department?: string }>();
  const navigate = useNavigate();
  const ctx = getContext();
  const amoSlug = params.amoCode ?? ctx.amoCode ?? "UNKNOWN";
  const department = params.department ?? ctx.department ?? "quality";
  const uiShellV2 = isUiShellV2Enabled();

  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [audits, setAudits] = useState<QMSAuditOut[]>([]);
  const [documents, setDocuments] = useState<QMSDocumentOut[]>([]);
  const [cars, setCars] = useState<CAROut[]>([]);
  const [events, setEvents] = useState<TrainingEventRead[]>([]);

  const load = async () => {
    setState("loading");
    setError(null);
    try {
      const [auditData, docData, carData, eventData] = await Promise.all([
        qmsListAudits({ domain: "AMO" }),
        qmsListDocuments({ domain: "AMO" }),
        qmsListCars(),
        listTrainingEvents(),
      ]);
      setAudits(auditData);
      setDocuments(docData);
      setCars(carData);
      setEvents(eventData);
      setState("ready");
    } catch (e: any) {
      setError(e?.message || "Failed to load KPI metrics.");
      setState("error");
    }
  };

  useEffect(() => {
    if (!uiShellV2) {
      load();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uiShellV2]);

  const kpis = useMemo(() => {
    const totalAudits = audits.length;
    const closedAudits = audits.filter((audit) => audit.status === "CLOSED").length;
    const auditClosureRate = totalAudits
      ? Math.round((closedAudits / totalAudits) * 100)
      : 0;

    const overdueCars = cars.filter((car) => {
      if (!car.due_date) return false;
      if (["CLOSED", "CANCELLED"].includes(car.status)) return false;
      return new Date(car.due_date) < new Date();
    }).length;

    const docCurrencyRate = documents.length
      ? Math.round(
          (documents.filter((doc) => doc.status === "ACTIVE").length / documents.length) * 100
        )
      : 0;

    const upcomingEvents = events.filter((event) => new Date(event.starts_on) > new Date())
      .length;

    return [
      {
        id: "audit-closure",
        label: "Audit closure rate",
        value: `${auditClosureRate}%`,
        description: "Closed audits vs total programme.",
        trend: auditClosureRate > 85 ? "On track" : "Needs attention",
      },
      {
        id: "doc-currency",
        label: "Document currency",
        value: `${docCurrencyRate}%`,
        description: "Active manuals and procedures.",
        trend: docCurrencyRate > 90 ? "Healthy" : "Review draft backlog",
      },
      {
        id: "car-overdue",
        label: "Overdue CARs",
        value: `${overdueCars}`,
        description: "Corrective actions past due date.",
        trend: overdueCars === 0 ? "On track" : "Escalate overdue items",
      },
      {
        id: "events",
        label: "Upcoming training events",
        value: `${upcomingEvents}`,
        description: "Scheduled sessions in the pipeline.",
        trend: upcomingEvents > 0 ? "Planned" : "Schedule sessions",
      },
    ];
  }, [audits, cars, documents, events]);

  return (
    <QMSLayout
      amoCode={amoSlug}
      department={department}
      title="KPIs & Management Review"
      subtitle="Quality performance indicators aligned with management review needs."
      actions={
        uiShellV2 ? null : (
          <button type="button" className="primary-chip-btn" onClick={load}>
            Refresh KPIs
          </button>
        )
      }
    >
      {uiShellV2 ? (
        <DashboardCockpit />
      ) : (
        <>
          <section className="qms-toolbar">
            <button type="button" className="secondary-chip-btn" onClick={() => navigate(-1)}>
              Back
            </button>
          </section>

          {state === "loading" && (
            <div className="card card--info">
              <p>Loading KPI dashboard…</p>
            </div>
          )}

          {state === "error" && (
            <div className="card card--error">
              <p>{error}</p>
              <button type="button" className="primary-chip-btn" onClick={load}>
                Retry
              </button>
            </div>
          )}

          {state === "ready" && (
            <section className="qms-grid">
              {kpis.map((kpi) => (
                <div key={kpi.id} className="qms-card">
                  <div className="qms-card__header">
                    <div>
                      <h3 className="qms-card__title">{kpi.label}</h3>
                      <p className="qms-card__subtitle">{kpi.description}</p>
                    </div>
                    <span className="qms-pill">{kpi.trend}</span>
                  </div>
                  <div className="qms-kpi__value qms-kpi__value--large">{kpi.value}</div>
                </div>
              ))}
            </section>
          )}
        </>
      )}
    </QMSLayout>
  );
};

export default QMSKpisPage;
