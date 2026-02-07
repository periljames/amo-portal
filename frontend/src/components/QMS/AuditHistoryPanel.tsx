import React, { useEffect, useState } from "react";
import { listAuditEvents, type AuditEvent } from "../../services/audit";

type LoadState = "idle" | "loading" | "ready" | "error";

type AuditHistoryPanelProps = {
  title?: string;
  entityType?: string;
  entityId?: string;
  limit?: number;
};

const AuditHistoryPanel: React.FC<AuditHistoryPanelProps> = ({
  title = "History",
  entityType,
  entityId,
  limit = 8,
}) => {
  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);

  const load = async () => {
    setState("loading");
    setError(null);
    try {
      const data = await listAuditEvents({ entityType, entityId, limit });
      setEvents(data);
      setState("ready");
    } catch (err: any) {
      setError(err?.message || "Failed to load history.");
      setState("error");
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entityType, entityId]);

  const formatDate = (value: string) => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString();
  };

  return (
    <div className="qms-card">
      <div className="qms-card__header">
        <div>
          <h3 className="qms-card__title">{title}</h3>
          <p className="qms-card__subtitle">
            Append-only timeline for compliance evidence.
          </p>
        </div>
        <button type="button" className="secondary-chip-btn" onClick={load}>
          Refresh
        </button>
      </div>
      {state === "loading" && <p>Loading audit history…</p>}
      {state === "error" && <p className="text-muted">{error}</p>}
      {state === "ready" && (
        <div className="qms-list">
          {events.map((event) => (
            <div key={event.id} className="qms-list__item">
              <div>
                <strong>{event.action}</strong>
                <span className="qms-list__meta">
                  {event.entity_type} · {formatDate(event.occurred_at || event.created_at)}
                </span>
              </div>
              <span className="qms-pill">{event.actor_user_id || "system"}</span>
            </div>
          ))}
          {events.length === 0 && <p className="text-muted">No audit events yet.</p>}
        </div>
      )}
    </div>
  );
};

export default AuditHistoryPanel;
